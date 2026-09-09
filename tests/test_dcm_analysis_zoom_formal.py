from __future__ import annotations

import os

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_analysis.plots import (
    MAX_DISPLAY_POINTS,
    display_indices_for_range,
)
from scope_zero_span_converter.dcm_analysis.spectrum import DcmSpectrum
from scope_zero_span_converter.dcm_analysis.widget import DcmAnalysisWidget
from scope_zero_span_converter.dcm_analysis.zoom_interaction import ZoomInteractionMixin


def _qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_formal_widget_owns_zoom_runtime_methods():
    _qapp()
    widget = DcmAnalysisWidget()

    assert isinstance(widget, ZoomInteractionMixin)
    assert widget._on_zoom_rectangle.__func__.__module__ == (
        "scope_zero_span_converter.dcm_analysis.zoom_interaction"
    )
    assert widget._apply_zoom_ranges_if_ready.__func__.__module__ == (
        "scope_zero_span_converter.dcm_analysis.zoom_interaction"
    )
    assert widget._on_axis_display_changed.__func__.__module__ == (
        "scope_zero_span_converter.dcm_analysis.zoom_interaction"
    )


def test_time_zoom_rebuilds_line_from_full_waveform_for_visible_range():
    _qapp()
    widget = DcmAnalysisWidget()
    waveform = widget.current_waveform
    assert waveform is not None

    ax_time = widget.figure.axes[0]
    initial_x = np.asarray(ax_time.lines[0].get_xdata(), dtype=float)
    assert len(initial_x) <= MAX_DISPLAY_POINTS

    x_range = (2.0, 3.0)
    y_range = (widget.dcm_y_min.value(), widget.dcm_y_max.value())
    widget._zoom_state.push("time", (x_range, y_range))
    widget._redraw(zero_span_error=widget.current_zero_span_error)

    time_us = np.asarray(waveform.time_s, dtype=float) * 1e6
    voltage = np.asarray(waveform.voltage_v, dtype=float)
    expected_indices = display_indices_for_range(time_us, voltage, x_range)
    actual_x = np.asarray(widget.figure.axes[0].lines[0].get_xdata(), dtype=float)

    assert np.array_equal(actual_x, time_us[expected_indices])
    assert widget.figure.axes[0].get_xlim() == x_range


def _install_large_spectrum(widget):
    points = MAX_DISPLAY_POINTS * 3
    frequency_hz = np.linspace(0.0, 500e6, points)
    amplitude = -90.0 + 15.0 * np.sin(np.linspace(0.0, 200.0, points))
    phase = np.linspace(-180.0, 180.0, points)
    spectrum = DcmSpectrum(
        frequency_hz=frequency_hz,
        amplitude_dbv=amplitude,
        phase_deg=phase,
        sample_interval_s=1e-9,
    )
    assert widget.current_waveform is not None
    widget._set_spectrum_cache(widget.current_waveform, spectrum)
    return spectrum


def test_frequency_rectangle_zoom_restores_shared_full_cache_bins():
    _qapp()
    widget = DcmAnalysisWidget()
    spectrum = _install_large_spectrum(widget)
    widget._redraw(zero_span_error=widget.current_zero_span_error)
    full_display_x = set(widget.figure.axes[1].lines[0].get_xdata())

    x_range = (100.0, 150.0)
    widget._zoom_state.push("frequency", (x_range, (-120.0, 0.0)))
    widget._redraw(zero_span_error=widget.current_zero_span_error)

    frequency_mhz = spectrum.frequency_hz / 1e6
    expected = display_indices_for_range(
        frequency_mhz,
        spectrum.amplitude_dbv,
        x_range,
    )
    magnitude_x = np.asarray(widget.figure.axes[1].lines[0].get_xdata())
    phase_x = np.asarray(widget.figure.axes[3].lines[0].get_xdata())
    assert np.array_equal(magnitude_x, frequency_mhz[expected])
    assert np.array_equal(phase_x, magnitude_x)
    assert len(magnitude_x) < MAX_DISPLAY_POINTS
    assert any(value not in full_display_x for value in magnitude_x)


def test_manual_frequency_range_restores_same_bins_for_magnitude_and_phase():
    _qapp()
    widget = DcmAnalysisWidget()
    spectrum = _install_large_spectrum(widget)
    controls = (widget.freq_x_min, widget.freq_x_max)
    for control in controls:
        control.blockSignals(True)
    try:
        widget.freq_x_min.setValue(220.0)
        widget.freq_x_max.setValue(260.0)
    finally:
        for control in controls:
            control.blockSignals(False)

    widget._on_frequency_axis_changed()

    frequency_mhz = spectrum.frequency_hz / 1e6
    expected = display_indices_for_range(
        frequency_mhz,
        spectrum.amplitude_dbv,
        (220.0, 260.0),
    )
    magnitude_x = np.asarray(widget.figure.axes[1].lines[0].get_xdata())
    phase_x = np.asarray(widget.figure.axes[3].lines[0].get_xdata())
    assert np.array_equal(magnitude_x, frequency_mhz[expected])
    assert np.array_equal(phase_x, magnitude_x)
