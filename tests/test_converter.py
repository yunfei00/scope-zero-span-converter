import json
from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from scope_zero_span_converter import __version__
from scope_zero_span_converter.config import AppConfig
from scope_zero_span_converter.converter import convert, save_result


def _make_200mhz_case(tmp_path):
    fs = 1e9
    duration = 10e-6
    t = np.arange(int(fs * duration)) / fs
    peak_v = 0.2
    waveform = peak_v * np.cos(2 * np.pi * 200e6 * t)

    waveform_path = tmp_path / "waveform.csv"
    pd.DataFrame({"time_s": t, "voltage_v": waveform}).to_csv(
        waveform_path,
        index=False,
    )

    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps({}), encoding="utf-8")

    config = AppConfig()
    config.signal.center_frequency_hz = 200e6
    config.signal.rbw_hz = 10e6
    config.signal.vbw_hz = 10e6
    config.conversion.use_metadata_parameters = False
    config.conversion.resample_to_fsw_axis = False
    config.conversion.impedance_ohm = 50.0
    config.scope.analog_bandwidth_hz = 350e6
    return waveform_path, metadata_path, config


def test_200mhz_cw_converts_to_stable_zerospan(tmp_path):
    waveform_path, metadata_path, config = _make_200mhz_case(tmp_path)

    result = convert(waveform_path, metadata_path, config)

    # 0.2 Vpeak -> 0.1414 Vrms -> 0.4 mW -> about -3.98 dBm.
    quarter = len(result.amplitude_dbm) // 4
    middle = result.amplitude_dbm[quarter:-quarter]
    assert np.median(middle) == pytest.approx(-3.9794, abs=0.5)
    assert np.std(middle) < 0.5
    assert result.parameter_sources["center_frequency_hz"] == "config"


@pytest.mark.parametrize("legacy_metadata_flag", [False, True])
@pytest.mark.parametrize("resample", [False, True])
def test_metadata_cannot_override_gui_config_parameters(tmp_path, legacy_metadata_flag, resample):
    waveform_path, metadata_path, config = _make_200mhz_case(tmp_path)
    config.signal.vbw_hz = 2e6
    config.conversion.vbw_enabled = True
    config.conversion.fsw_sweep_time_s = 5e-6  # Inside the 9.999 us scope record.
    config.conversion.fsw_trace_points = 501
    config.conversion.resample_to_fsw_axis = resample
    # Even an old in-memory caller cannot reactivate metadata precedence.
    config.conversion.use_metadata_parameters = legacy_metadata_flag
    baseline = convert(waveform_path, metadata_path, deepcopy(config))
    metadata_path.write_text(json.dumps({
        "metadata": {"instruments": {"spectrum_analyzer": {"configuration": {
            "center_frequency_hz": 100e6, "span_hz": 20e6,
            "rbw_hz": 1e6, "vbw_hz": 0.1e6,
        }}}},
        "spectra": {"ext": {"points": 9999, "metadata": {
            "center_frequency_hz": 100e6, "span_hz": 20e6,
            "sweep_time_s": 10e-3,
        }}},
    }), encoding="utf-8")

    result = convert(waveform_path, metadata_path, config)

    assert result.center_frequency_hz == config.signal.center_frequency_hz == 200e6
    assert result.rbw_hz == config.signal.rbw_hz == 10e6
    assert result.vbw_hz == config.signal.vbw_hz == 2e6
    assert result.fsw_sweep_time_s == config.conversion.fsw_sweep_time_s == 5e-6
    assert result.fsw_trace_points == config.conversion.fsw_trace_points == 501
    assert result.resampled_to_fsw_axis is resample
    assert len(result.time_s) == (501 if resample else result.input_points)
    if resample:
        assert result.time_s[-1] == config.conversion.fsw_sweep_time_s
    assert result.parameter_sources == {
        "center_frequency_hz": "config", "rbw_hz": "config",
        "vbw_hz": "config", "span_hz": "config",
    }
    # Compare actual computation, not just labels: metadata cannot change any samples.
    np.testing.assert_array_equal(result.time_s, baseline.time_s)
    np.testing.assert_array_equal(result.amplitude_dbm, baseline.amplitude_dbm)
    np.testing.assert_array_equal(result.envelope_v_rms, baseline.envelope_v_rms)


def test_metadata_is_not_a_fallback_for_unset_config_fsw_axis(tmp_path):
    waveform_path, metadata_path, config = _make_200mhz_case(tmp_path)
    config.conversion.resample_to_fsw_axis = True
    metadata_path.write_text(json.dumps({"spectra": {"ext": {
        "points": 501, "metadata": {"sweep_time_s": 5e-6},
    }}}), encoding="utf-8")

    result = convert(waveform_path, metadata_path, config)

    assert result.fsw_sweep_time_s is None
    assert result.fsw_trace_points is None
    assert result.resampled_to_fsw_axis is False
    assert len(result.time_s) == result.input_points == 10_000


def test_metadata_zero_span_cannot_mask_invalid_config_span(tmp_path):
    waveform_path, metadata_path, config = _make_200mhz_case(tmp_path)
    config.signal.span_hz = 1e6
    metadata_path.write_text(json.dumps({"spectra": {"ext": {
        "metadata": {"span_hz": 0.0},
    }}}), encoding="utf-8")

    with pytest.raises(ValueError, match="span_hz 必须为 0"):
        convert(waveform_path, metadata_path, config)


def test_saves_conversion_metadata_and_fsw_comparison(tmp_path):
    waveform_path, metadata_path, config = _make_200mhz_case(tmp_path)
    result = convert(waveform_path, metadata_path, config)

    reference_path = tmp_path / "fsw_reference.csv"
    pd.DataFrame(
        {
            "time_s": result.time_s,
            "amplitude_dbm": result.amplitude_dbm - 1.0,
        }
    ).to_csv(reference_path, index=False)

    output_dir = tmp_path / "output"
    config.output.directory = str(output_dir)
    config.output.save_plot = False
    config.output.show_plot = False
    config.output.save_conversion_metadata = True
    config.comparison.enabled = True
    config.comparison.save_aligned_csv = True

    save_result(
        result,
        waveform_path,
        config,
        metadata_path=metadata_path,
        reference_fsw_path=reference_path,
    )

    assert result.comparison is not None
    assert result.comparison.mae_db == pytest.approx(1.0, abs=1e-6)
    assert (output_dir / "zero_span_from_scope.csv").exists()
    assert (output_dir / "comparison_to_fsw.csv").exists()
    assert (output_dir / "conversion_metadata.json").exists()

    metadata = json.loads(
        (output_dir / "conversion_metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["software"]["version"] == __version__
    assert metadata["inputs"]["metadata_file"] == str(metadata_path)
    assert metadata["comparison"]["mae_db"] == pytest.approx(1.0, abs=1e-6)
