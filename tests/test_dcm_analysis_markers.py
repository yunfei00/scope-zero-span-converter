from __future__ import annotations

import numpy as np
import pytest

from scope_zero_span_converter.dcm_analysis.markers import spectrum_marker_at_frequency
from scope_zero_span_converter.dcm_analysis.spectrum import compute_dcm_spectrum


def test_spectrum_marker_uses_nearest_actual_fft_bin_for_magnitude_and_phase():
    fs = 1e9
    n = 10_000
    t = np.arange(n, dtype=float) / fs
    v = np.sin(2.0 * np.pi * 50e6 * t)
    spectrum = compute_dcm_spectrum(t, v)

    marker = spectrum_marker_at_frequency(spectrum, 50.03e6)

    assert marker.frequency_hz == pytest.approx(50e6, abs=fs / n)
    assert spectrum.frequency_hz[marker.bin_index] == pytest.approx(marker.frequency_hz)
    assert spectrum.amplitude_dbv[marker.bin_index] == pytest.approx(marker.amplitude_dbv)
    assert marker.phase_valid is True
    assert spectrum.phase_deg[marker.bin_index] == pytest.approx(marker.phase_deg)
    assert marker.frequency_error_hz == pytest.approx(marker.frequency_hz - 50.03e6)


def test_marker_preserves_invalid_phase_from_spectrum_policy():
    fs = 1e9
    n = 10_000
    t = np.arange(n, dtype=float) / fs
    v = (
        np.sin(2.0 * np.pi * 50e6 * t)
        + 1e-4 * np.sin(2.0 * np.pi * 120e6 * t)
    )
    spectrum = compute_dcm_spectrum(t, v)

    marker = spectrum_marker_at_frequency(spectrum, 120e6)

    assert marker.amplitude_dbv == pytest.approx(-80.0, abs=0.2)
    assert marker.phase_valid is False
    assert marker.phase_deg is None


def test_marker_rejects_frequency_outside_current_spectrum():
    fs = 1e9
    t = np.arange(4096, dtype=float) / fs
    v = np.sin(2.0 * np.pi * 100e6 * t)
    spectrum = compute_dcm_spectrum(t, v)

    with pytest.raises(ValueError, match="超出当前频谱范围"):
        spectrum_marker_at_frequency(spectrum, -1.0)
    with pytest.raises(ValueError, match="超出当前频谱范围"):
        spectrum_marker_at_frequency(spectrum, spectrum.frequency_hz[-1] + 1.0)
