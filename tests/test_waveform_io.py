from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scope_zero_span_converter.waveform_io import load_waveform_csv_checked


def test_checked_loader_sorts_reversed_rows_and_preserves_warning(tmp_path):
    t = np.arange(100, dtype=float) / 1e9
    v = np.sin(2.0 * np.pi * 50e6 * t)
    order = np.arange(len(t))
    order[[20, 21]] = order[[21, 20]]

    path = tmp_path / "reordered.csv"
    pd.DataFrame({"time_s": t[order], "voltage_v": v[order]}).to_csv(path, index=False)

    data = load_waveform_csv_checked(path, min_points=64, require_named_columns=True)

    assert data.quality.fft_safe is True
    assert data.quality.status == "warn"
    assert data.quality.nonmonotonic_steps > 0
    assert np.all(np.diff(data.time_s) > 0)
    assert data.rows_dropped == 0


def test_checked_loader_reports_dropped_invalid_rows(tmp_path):
    t = np.arange(100, dtype=float) / 1e9
    v = np.sin(2.0 * np.pi * 50e6 * t)
    frame = pd.DataFrame({"time_s": t, "voltage_v": v})
    # Put invalid rows at the tail so removing them does not create an internal gap.
    frame.loc[98, "time_s"] = np.nan
    frame.loc[99, "voltage_v"] = np.nan

    path = tmp_path / "invalid_tail.csv"
    frame.to_csv(path, index=False)
    data = load_waveform_csv_checked(path, min_points=64, require_named_columns=True)

    assert data.points == 98
    assert data.rows_total == 100
    assert data.rows_dropped == 2
    assert data.quality.fft_safe is True


def test_checked_loader_rejects_missing_named_columns_for_extractor(tmp_path):
    path = tmp_path / "unnamed.csv"
    pd.DataFrame({"a": [0.0, 1.0], "b": [0.0, 1.0]}).to_csv(path, index=False)

    with pytest.raises(ValueError, match="time_s"):
        load_waveform_csv_checked(path, min_points=2, require_named_columns=True)
