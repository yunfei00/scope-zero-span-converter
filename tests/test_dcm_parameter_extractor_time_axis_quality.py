from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scope_zero_span_converter.dcm_parameter_extractor import load_waveform_csv


def _write_waveform(path, time_s: np.ndarray) -> None:
    pd.DataFrame(
        {
            "time_s": time_s,
            "voltage_v": np.zeros_like(time_s),
        }
    ).to_csv(path, index=False)


def test_dcm_loader_uses_unified_one_percent_uniformity_limit(tmp_path):
    # 1 ns nominal interval; introduce one 1.02 ns interval. The old DCM-only
    # 5% rule accepted this, while the shared WaveformQualityReport correctly
    # rejects it because the common FFT / Zero Span limit is 1%.
    time_s = np.arange(128, dtype=float) * 1e-9
    time_s[64:] += 0.02e-9
    path = tmp_path / "two_percent_gap.csv"
    _write_waveform(path, time_s)

    with pytest.raises(ValueError, match="采样间隔最大偏差"):
        load_waveform_csv(path)


def test_dcm_loader_accepts_sub_percent_csv_rounding_jitter(tmp_path):
    # Small timestamp formatting/jitter remains acceptable under the shared
    # quality policy and still satisfies the extractor's strict ordering rule.
    time_s = np.arange(128, dtype=float) * 1e-9
    time_s[64:] += 0.005e-9
    path = tmp_path / "half_percent_gap.csv"
    _write_waveform(path, time_s)

    loaded_time, loaded_voltage = load_waveform_csv(path)

    assert len(loaded_time) == 128
    assert len(loaded_voltage) == 128
    assert np.all(np.diff(loaded_time) > 0)
