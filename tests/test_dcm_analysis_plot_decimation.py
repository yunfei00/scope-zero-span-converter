from __future__ import annotations

import numpy as np
from matplotlib.figure import Figure

from scope_zero_span_converter.dcm_analysis.plots import (
    MAX_DISPLAY_POINTS,
    display_indices_preserve_extrema,
    draw_magnitude_spectrum_panel,
    draw_phase_spectrum_panel,
)
from scope_zero_span_converter.dcm_analysis.spectrum import DcmSpectrum


def test_display_decimation_preserves_endpoints_and_single_sample_spike():
    values = np.zeros(200_000, dtype=float)
    values[123_457] = 99.0
    values[150_003] = -77.0

    indices = display_indices_preserve_extrema(values, max_points=2_000)

    assert len(indices) <= 2_000
    assert indices[0] == 0
    assert indices[-1] == len(values) - 1
    assert 123_457 in indices
    assert 150_003 in indices


def test_magnitude_and_phase_use_identical_reduced_frequency_samples():
    points = MAX_DISPLAY_POINTS * 3
    frequency_hz = np.linspace(0.0, 500e6, points)
    amplitude_dbv = -100.0 + 12.0 * np.sin(np.linspace(0.0, 80.0, points))
    amplitude_dbv[31_337] = 5.0
    phase_deg = np.linspace(-180.0, 180.0, points)
    spectrum = DcmSpectrum(
        frequency_hz=frequency_hz,
        amplitude_dbv=amplitude_dbv,
        phase_deg=phase_deg,
        sample_interval_s=1e-9,
        phase_visibility_threshold_dbv=-120.0,
    )

    figure = Figure()
    ax_mag = figure.add_subplot(211)
    ax_phase = figure.add_subplot(212)
    draw_magnitude_spectrum_panel(
        ax_mag,
        spectrum,
        center_frequency_hz=200e6,
        rbw_hz=10e6,
    )
    draw_phase_spectrum_panel(
        ax_phase,
        spectrum,
        center_frequency_hz=200e6,
        rbw_hz=10e6,
    )

    mag_x = np.asarray(ax_mag.lines[0].get_xdata(), dtype=float)
    phase_x = np.asarray(ax_phase.lines[0].get_xdata(), dtype=float)
    assert len(mag_x) <= MAX_DISPLAY_POINTS
    assert len(phase_x) <= MAX_DISPLAY_POINTS
    assert np.array_equal(mag_x, phase_x)
    assert "显示抽样" in ax_mag.get_title()
    assert "显示抽样" in ax_phase.get_title()

    spike_mhz = frequency_hz[31_337] / 1e6
    assert np.any(np.isclose(mag_x, spike_mhz, rtol=0.0, atol=1e-12))
