from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_analysis.widget import DcmAnalysisWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_axis_display_controls_exist_and_are_collapsed_by_default(qapp):
    del qapp
    widget = DcmAnalysisWidget()
    assert not widget.axis_display_toggle.isChecked()
    assert not widget.axis_display_panel.isVisible()
    for name in (
        "dcm_y_min",
        "dcm_y_max",
        "dcm_y_step",
        "zero_y_min",
        "zero_y_max",
        "zero_y_step",
    ):
        assert hasattr(widget, name)


def test_custom_y_ranges_and_grid_steps_apply_without_recomputing_data(qapp):
    del qapp
    widget = DcmAnalysisWidget()
    assert widget.current_waveform is not None
    assert widget.current_zero_span is not None

    before_scope = widget.current_waveform.voltage_v.copy()
    before_zero = widget.current_zero_span.amplitude_dbm.copy()

    for spin in (
        widget.dcm_y_min,
        widget.dcm_y_max,
        widget.dcm_y_step,
        widget.zero_y_min,
        widget.zero_y_max,
        widget.zero_y_step,
    ):
        spin.blockSignals(True)
    try:
        widget.dcm_y_min.setValue(-10.0)
        widget.dcm_y_max.setValue(20.0)
        widget.dcm_y_step.setValue(5.0)
        widget.zero_y_min.setValue(-100.0)
        widget.zero_y_max.setValue(20.0)
        widget.zero_y_step.setValue(10.0)
    finally:
        for spin in (
            widget.dcm_y_min,
            widget.dcm_y_max,
            widget.dcm_y_step,
            widget.zero_y_min,
            widget.zero_y_max,
            widget.zero_y_step,
        ):
            spin.blockSignals(False)

    widget._on_axis_display_changed()

    assert np.allclose(before_scope, widget.current_waveform.voltage_v)
    assert np.allclose(before_zero, widget.current_zero_span.amplitude_dbm)

    ax_dcm = widget.figure.axes[0]
    ax_zero_span = widget.figure.axes[2]
    assert np.allclose(ax_dcm.get_ylim(), (-10.0, 20.0))
    assert np.allclose(ax_zero_span.get_ylim(), (-100.0, 20.0))

    dcm_ticks = ax_dcm.get_yticks()
    zero_ticks = ax_zero_span.get_yticks()
    assert np.allclose(np.diff(dcm_ticks), 5.0)
    assert np.allclose(np.diff(zero_ticks), 10.0)
