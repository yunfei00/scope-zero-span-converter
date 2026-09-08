from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_analysis.frequency_axis import FrequencyAxisMixin
from scope_zero_span_converter.dcm_analysis.widget import DcmAnalysisWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_formal_widget_uses_formal_frequency_axis_behavior(qapp):
    del qapp
    widget = DcmAnalysisWidget()
    assert isinstance(widget, FrequencyAxisMixin)
    assert widget._apply_frequency_auto_axis.__func__.__module__ == (
        "scope_zero_span_converter.dcm_analysis.frequency_axis"
    )
    assert widget._on_frequency_axis_changed.__func__.__module__ == (
        "scope_zero_span_converter.dcm_analysis.frequency_axis"
    )


def test_manual_frequency_axis_is_display_only_and_clears_frequency_zoom(qapp):
    del qapp
    widget = DcmAnalysisWidget()
    waveform = widget.current_waveform
    zero_span = widget.current_zero_span
    spectrum = widget._spectrum_cache
    assert waveform is not None
    assert zero_span is not None
    assert spectrum is not None

    widget._zoom_state.push("frequency", ((10.0, 80.0), (-120.0, 0.0)))
    assert widget._zoom_state.current("frequency") is not None

    controls = (
        widget.freq_x_min,
        widget.freq_x_max,
        widget.freq_x_step,
        widget.freq_y_min,
        widget.freq_y_max,
        widget.freq_y_step,
    )
    for control in controls:
        control.blockSignals(True)
    try:
        widget.freq_x_min.setValue(20.0)
        widget.freq_x_max.setValue(120.0)
        widget.freq_x_step.setValue(10.0)
        widget.freq_y_min.setValue(-100.0)
        widget.freq_y_max.setValue(5.0)
        widget.freq_y_step.setValue(10.0)
    finally:
        for control in controls:
            control.blockSignals(False)

    widget._on_frequency_axis_changed()

    assert widget._zoom_state.current("frequency") is None
    assert widget.current_waveform is waveform
    assert widget.current_zero_span is zero_span
    assert widget._spectrum_cache is spectrum

    _ax_time, ax_magnitude, _ax_zero, _ax_phase = widget.figure.axes
    assert ax_magnitude.get_xlim() == pytest.approx((20.0, 120.0))
    assert ax_magnitude.get_ylim() == pytest.approx((-100.0, 5.0))


def test_normal_redraw_auto_fits_and_writes_back_frequency_axis_controls(qapp):
    del qapp
    widget = DcmAnalysisWidget()
    widget._redraw(zero_span_error=widget.current_zero_span_error)

    _ax_time, ax_magnitude, _ax_zero, ax_phase = widget.figure.axes
    x_min, x_max = ax_magnitude.get_xlim()
    y_min, y_max = ax_magnitude.get_ylim()

    assert widget.freq_x_min.value() == pytest.approx(x_min)
    assert widget.freq_x_max.value() == pytest.approx(x_max)
    assert widget.freq_y_min.value() == pytest.approx(y_min)
    assert widget.freq_y_max.value() == pytest.approx(y_max)
    assert widget.freq_x_step.value() > 0
    assert widget.freq_y_step.value() > 0
    assert ax_phase.get_xlim() == pytest.approx((x_min, x_max))
