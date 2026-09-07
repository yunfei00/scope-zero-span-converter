from __future__ import annotations

import numpy as np
import pytest

from scope_zero_span_converter.dcm_analysis.peaks import find_spectrum_peaks
from scope_zero_span_converter.dcm_analysis.spectrum import compute_dcm_spectrum


def test_peaks_are_ranked_from_same_magnitude_phase_bins():
    fs = 1e9
    n = 10_000
    t = np.arange(n, dtype=float) / fs
    v = (
        np.sin(2.0 * np.pi * 50e6 * t)
        + 0.5 * np.sin(2.0 * np.pi * 120e6 * t)
    )
    spectrum = compute_dcm_spectrum(t, v)

    peaks = find_spectrum_peaks(spectrum, top_n=4, relative_floor_db=40.0)

    assert len(peaks) >= 2
    assert peaks[0].frequency_hz == pytest.approx(50e6, abs=fs / n)
    assert peaks[0].amplitude_dbv == pytest.approx(0.0, abs=0.1)
    assert peaks[0].phase_valid is True
    assert peaks[1].frequency_hz == pytest.approx(120e6, abs=fs / n)
    assert peaks[1].amplitude_dbv == pytest.approx(20.0 * np.log10(0.5), abs=0.1)

    for peak in peaks:
        assert spectrum.frequency_hz[peak.bin_index] == pytest.approx(peak.frequency_hz)
        assert spectrum.amplitude_dbv[peak.bin_index] == pytest.approx(peak.amplitude_dbv)
        if peak.phase_valid:
            assert spectrum.phase_deg[peak.bin_index] == pytest.approx(peak.phase_deg)


def test_peak_table_marks_phase_invalid_when_spectrum_policy_masks_it():
    fs = 1e9
    n = 10_000
    t = np.arange(n, dtype=float) / fs
    v = (
        np.sin(2.0 * np.pi * 50e6 * t)
        + 1e-4 * np.sin(2.0 * np.pi * 120e6 * t)
    )
    spectrum = compute_dcm_spectrum(t, v)

    peaks = find_spectrum_peaks(spectrum, top_n=10, relative_floor_db=100.0)
    weak = min(peaks, key=lambda item: abs(item.frequency_hz - 120e6))

    assert weak.frequency_hz == pytest.approx(120e6, abs=fs / n)
    assert weak.amplitude_dbv == pytest.approx(-80.0, abs=0.2)
    assert weak.phase_valid is False
    assert weak.phase_deg is None


def test_peak_options_validate_and_top_n_is_respected():
    fs = 1e9
    n = 4096
    t = np.arange(n, dtype=float) / fs
    v = np.sin(2.0 * np.pi * 125e6 * t)
    spectrum = compute_dcm_spectrum(t, v)

    assert len(find_spectrum_peaks(spectrum, top_n=1)) == 1
    assert find_spectrum_peaks(spectrum, top_n=0) == []

    with pytest.raises(ValueError, match="relative_floor_db"):
        find_spectrum_peaks(spectrum, relative_floor_db=0.0)
    with pytest.raises(ValueError, match="min_separation_bins"):
        find_spectrum_peaks(spectrum, min_separation_bins=0)
