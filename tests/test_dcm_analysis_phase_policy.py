from __future__ import annotations

import numpy as np
import pytest

from scope_zero_span_converter.dcm_analysis.spectrum import compute_dcm_spectrum


def test_default_phase_visibility_uses_peak_relative_dynamic_range():
    fs = 1e9
    n = 10_000
    t = np.arange(n, dtype=float) / fs
    # 1 Vpeak main tone -> about 0 dBV at the peak. Add a much weaker tone so
    # the result contains bins both above and below the 60 dB dynamic limit.
    v = np.sin(2.0 * np.pi * 50e6 * t) + 1e-4 * np.sin(2.0 * np.pi * 120e6 * t)

    result = compute_dcm_spectrum(t, v)

    assert result.phase_reference == "record_start"
    assert "记录起点" in result.phase_reference_description
    assert result.phase_dynamic_range_db == pytest.approx(60.0)
    assert result.phase_visibility_threshold_dbv == pytest.approx(-60.0, abs=0.1)

    visible = np.isfinite(result.phase_deg)
    assert np.any(visible)
    assert np.all(result.amplitude_dbv[visible] >= result.phase_visibility_threshold_dbv)
    assert np.all(
        np.isnan(result.phase_deg[result.amplitude_dbv < result.phase_visibility_threshold_dbv])
    )


def test_absolute_phase_floor_can_be_stricter_than_dynamic_range():
    fs = 1e9
    n = 4096
    t = np.arange(n, dtype=float) / fs
    v = np.sin(2.0 * np.pi * 125e6 * t)

    result = compute_dcm_spectrum(
        t,
        v,
        phase_visible_floor_dbv=-20.0,
        phase_dynamic_range_db=60.0,
    )

    assert result.phase_visibility_threshold_dbv == pytest.approx(-20.0, abs=0.1)
    assert np.all(
        np.isnan(result.phase_deg[result.amplitude_dbv < result.phase_visibility_threshold_dbv])
    )


def test_phase_dynamic_range_can_be_disabled_explicitly():
    fs = 1e9
    n = 4096
    t = np.arange(n, dtype=float) / fs
    v = np.sin(2.0 * np.pi * 125e6 * t)

    result = compute_dcm_spectrum(
        t,
        v,
        phase_visible_floor_dbv=-100.0,
        phase_dynamic_range_db=None,
    )

    assert result.phase_dynamic_range_db is None
    assert result.phase_visibility_threshold_dbv == pytest.approx(-100.0)


def test_invalid_phase_dynamic_range_is_rejected():
    fs = 1e9
    t = np.arange(1024, dtype=float) / fs
    v = np.sin(2.0 * np.pi * 50e6 * t)

    with pytest.raises(ValueError, match="phase_dynamic_range_db"):
        compute_dcm_spectrum(t, v, phase_dynamic_range_db=0.0)
