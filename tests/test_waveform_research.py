import json

import numpy as np
import pandas as pd
import pytest

from scope_zero_span_converter.config import AppConfig, config_from_dict
from scope_zero_span_converter.waveform_research import (
    convert_waveform_region,
    crop_waveform,
    save_waveform_region,
)


def _make_waveform():
    fs = 1e9
    duration = 10e-6
    t = np.arange(int(fs * duration)) / fs
    v = 0.2 * np.cos(2 * np.pi * 200e6 * t)
    return t, v


def test_crop_waveform_selects_requested_time_range():
    t, v = _make_waveform()
    region_t, region_v, region = crop_waveform(t, v, 2e-6, 4e-6)

    assert len(region_t) == len(region_v) == region.points
    assert region.start_time_s >= 2e-6
    assert region.end_time_s <= 4e-6
    assert region.duration_s == pytest.approx(2e-6, abs=2e-9)
    assert region.points > 1000


def test_save_waveform_region_writes_csv_and_sidecar(tmp_path):
    t, v = _make_waveform()
    region_t, region_v, region = crop_waveform(t, v, 1e-6, 3e-6)

    csv_path, metadata_path = save_waveform_region(
        tmp_path / "region.csv",
        region_t,
        region_v,
        region,
        source_waveform="waveform.csv",
        reset_time_to_zero=True,
        save_metadata=True,
    )

    assert csv_path.exists()
    assert metadata_path is not None and metadata_path.exists()

    saved = pd.read_csv(csv_path)
    assert list(saved.columns) == ["time_s", "voltage_v"]
    assert saved["time_s"].iloc[0] == pytest.approx(0.0, abs=1e-15)

    sidecar = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert sidecar["selection"]["points"] == region.points
    assert sidecar["saved_time_axis"] == "relative_zero"


def test_region_conversion_preserves_current_200mhz_baseline(tmp_path):
    t, v = _make_waveform()
    region_t, region_v, _ = crop_waveform(t, v, 2e-6, 8e-6)

    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text("{}", encoding="utf-8")

    config = AppConfig()
    config.conversion.use_metadata_parameters = False
    config.conversion.resample_to_fsw_axis = True  # 研究模式应主动忽略此项
    config.signal.center_frequency_hz = 200e6
    config.signal.rbw_hz = 10e6
    config.signal.vbw_hz = 10e6
    config.scope.analog_bandwidth_hz = 350e6

    result = convert_waveform_region(region_t, region_v, metadata_path, config)

    quarter = len(result.amplitude_dbm) // 4
    middle = result.amplitude_dbm[quarter:-quarter]
    assert np.median(middle) == pytest.approx(-3.9794, abs=0.5)
    assert result.resampled_to_fsw_axis is False
    assert result.input_points == len(region_t)


def test_old_json_without_waveform_research_remains_compatible():
    config = config_from_dict(
        {
            "schema_version": 1,
            "signal": {
                "center_frequency_hz": 200e6,
                "span_hz": 0.0,
                "rbw_hz": 10e6,
                "vbw_hz": 10e6,
            },
        }
    )
    assert config.waveform_research.extraction_mode == "manual"
    assert config.waveform_research.auto_update_conversion is True
