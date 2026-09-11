from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from scope_zero_span_converter.config import AppConfig
from scope_zero_span_converter.converter import (
    convert,
    load_waveform,
    resample_to_fsw_axis,
    save_result,
)


def _base_config(tmp_path) -> AppConfig:
    config = AppConfig()
    config.signal.center_frequency_hz = 200e6
    config.signal.rbw_hz = 10e6
    config.signal.vbw_hz = 10e6
    config.conversion.use_metadata_parameters = False
    config.conversion.impedance_ohm = 50.0
    config.scope.analog_bandwidth_hz = 350e6
    config.output.directory = str(tmp_path / "output")
    config.output.save_plot = False
    config.output.show_plot = False
    config.output.save_conversion_metadata = True
    return config


def _write_waveform(path, time_s):
    voltage_v = 0.2 * np.cos(2.0 * np.pi * 200e6 * time_s)
    pd.DataFrame({"time_s": time_s, "voltage_v": voltage_v}).to_csv(path, index=False)


def test_load_waveform_rejects_missing_sample_like_gap(tmp_path):
    t = np.arange(100, dtype=float) / 1e9
    t[50:] += 1e-9  # creates one 2 ns gap in an otherwise 1 ns record
    waveform_path = tmp_path / "gap.csv"
    _write_waveform(waveform_path, t)

    with pytest.raises(ValueError, match="时间轴不适合 FFT / Zero Span"):
        load_waveform(waveform_path)


def test_load_waveform_rejects_duplicate_timestamp(tmp_path):
    t = np.arange(100, dtype=float) / 1e9
    t[50] = t[49]
    waveform_path = tmp_path / "duplicate.csv"
    _write_waveform(waveform_path, t)

    with pytest.raises(ValueError, match="重复时间"):
        load_waveform(waveform_path)


def test_fsw_resample_rejects_sweep_one_full_dt_beyond_last_scope_sample():
    # Real Scope support is 0 ... 9 ns. A nominal N/Fs=10 ns duration would be
    # one full sample interval beyond the last measured point and must NOT be
    # treated as harmless tolerance; doing so would silently repeat the tail.
    t = np.arange(10, dtype=float) * 1e-9  # 0 ... 9 ns, dt = 1 ns
    power = np.linspace(1.0, 2.0, len(t))
    env = np.linspace(0.1, 0.2, len(t))

    with pytest.raises(ValueError, match="FSW Sweep Time 超出示波器实际记录时长"):
        resample_to_fsw_axis(t, power, env, 101, 10e-9)


def test_fsw_resample_accepts_only_floating_point_scale_endpoint_tolerance():
    t = np.arange(10, dtype=float) * 1e-9
    power = np.linspace(1.0, 2.0, len(t))
    env = np.linspace(0.1, 0.2, len(t))
    available = float(t[-1] - t[0])
    rounding_only = available + available * 5e-10

    out_t, out_power, out_env, resampled = resample_to_fsw_axis(
        t,
        power,
        env,
        19,
        rounding_only,
    )

    assert resampled is True
    assert len(out_t) == len(out_power) == len(out_env) == 19
    assert out_t[-1] == pytest.approx(rounding_only)
    # The tolerated excess is numerical-scale only, many orders smaller than dt.
    assert out_t[-1] - available < 1e-6 * (t[1] - t[0])


def test_fsw_resample_accepts_sweep_inside_scope_record():
    t = np.arange(10, dtype=float) * 1e-9  # 0 ... 9 ns
    power = np.linspace(1.0, 2.0, len(t))
    env = np.linspace(0.1, 0.2, len(t))

    out_t, out_power, out_env, resampled = resample_to_fsw_axis(
        t,
        power,
        env,
        19,
        9e-9,
    )

    assert resampled is True
    assert len(out_t) == len(out_power) == len(out_env) == 19
    assert out_t[-1] == pytest.approx(9e-9)


def test_conversion_metadata_contains_time_axis_quality(tmp_path):
    fs = 1e9
    t = np.arange(10_000, dtype=float) / fs
    waveform_path = tmp_path / "waveform.csv"
    metadata_path = tmp_path / "metadata.json"
    _write_waveform(waveform_path, t)
    metadata_path.write_text("{}", encoding="utf-8")

    config = _base_config(tmp_path)
    config.conversion.resample_to_fsw_axis = False

    result = convert(waveform_path, metadata_path, config)
    assert result.waveform_quality.fft_safe is True
    assert result.waveform_quality.sample_rate_hz == pytest.approx(fs, rel=1e-9)

    save_result(result, waveform_path, config, metadata_path=metadata_path)
    payload = json.loads(
        (tmp_path / "output" / "conversion_metadata.json").read_text(encoding="utf-8")
    )
    quality = payload["acquisition"]["time_axis_quality"]
    assert quality["fft_safe"] is True
    assert quality["status"] == "pass"
    assert quality["sample_rate_hz"] == pytest.approx(fs, rel=1e-9)


@pytest.mark.parametrize("metadata_sweep_s", [5e-6, 12e-6])
def test_convert_rejects_config_sweep_beyond_scope_duration(tmp_path, metadata_sweep_s):
    fs = 1e9
    t = np.arange(10_000, dtype=float) / fs
    waveform_path = tmp_path / "waveform.csv"
    metadata_path = tmp_path / "metadata.json"
    _write_waveform(waveform_path, t)

    # Metadata can request an in-range or out-of-range sweep; only config is effective.
    metadata_path.write_text(
        json.dumps(
            {
                "spectra": {
                    "ext": {
                        "points": 1001,
                        "metadata": {"sweep_time_s": metadata_sweep_s},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    config = _base_config(tmp_path)
    config.conversion.resample_to_fsw_axis = True
    config.conversion.fsw_sweep_time_s = 12e-6
    config.conversion.fsw_trace_points = 1001
    # Scope support ends at 9.999 us, not N/Fs. The config request must fail.
    assert t[-1] - t[0] == pytest.approx(9.999e-6)
    assert config.conversion.fsw_sweep_time_s > t[-1] - t[0]

    with pytest.raises(ValueError, match="FSW Sweep Time 超出示波器实际记录时长"):
        convert(waveform_path, metadata_path, config)
