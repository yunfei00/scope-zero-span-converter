from __future__ import annotations

import os

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_analysis.plots import (
    MAX_DISPLAY_POINTS,
    display_indices_for_range,
)
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
