import numpy as np
import pandas as pd
import pytest

from scope_zero_span_converter.comparison import (
    compare_zero_span,
    load_fsw_zero_span_csv,
)


def test_compare_zero_span_metrics():
    t = np.linspace(0.0, 1e-3, 101)
    reference = -30.0 + 2.0 * np.sin(2 * np.pi * 1000 * t)
    reconstructed = reference + 1.5

    result = compare_zero_span(t, reconstructed, t, reference)

    assert result.points == len(t)
    assert result.mae_db == pytest.approx(1.5, abs=1e-9)
    assert result.rmse_db == pytest.approx(1.5, abs=1e-9)
    assert result.bias_db == pytest.approx(1.5, abs=1e-9)
    assert result.max_abs_error_db == pytest.approx(1.5, abs=1e-9)
    assert result.correlation == pytest.approx(1.0, abs=1e-9)


def test_load_fsw_zero_span_csv(tmp_path):
    path = tmp_path / "fsw.csv"
    pd.DataFrame(
        {
            "time_s": [0.0, 1e-6, 2e-6],
            "amplitude_dbm": [-30.0, -29.0, -31.0],
        }
    ).to_csv(path, index=False)

    t, dbm = load_fsw_zero_span_csv(path)
    assert t.tolist() == [0.0, 1e-6, 2e-6]
    assert dbm.tolist() == [-30.0, -29.0, -31.0]
