from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_zero_span_widget_v3 import DcmZeroSpanWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _set_axis(widget: DcmZeroSpanWidget) -> None:
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
        widget.dcm_y_min.setValue(-5.0)
        widget.dcm_y_max.setValue(5.0)
        widget.dcm_y_step.setValue(2.0)
        widget.zero_y_min.setValue(-80.0)
        widget.zero_y_max.setValue(-40.0)
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


def test_data_above_maximum_does_not_expand_axes(qapp):
    del qapp
    widget = DcmZeroSpanWidget()
    _set_axis(widget)

    # 让 DCM 实际数据明显超过 +5 V。
    high = widget._parameter_controls["on_high_voltage_v"]
    high.setValue(100.0)
    widget._on_parameter_changed("on_high_voltage_v", high.value())
    widget._recompute()

    assert widget.current_waveform is not None
    assert float(np.max(widget.current_waveform.voltage_v)) > 5.0

    ax1, ax2 = widget.figure.axes
    assert np.allclose(ax1.get_ylim(), (-5.0, 5.0))
    assert np.allclose(ax2.get_ylim(), (-80.0, -40.0))
    assert not ax1.get_autoscaley_on()
    assert not ax2.get_autoscaley_on()
    assert np.all(ax1.get_yticks() >= -5.0 - 1e-12)
    assert np.all(ax1.get_yticks() <= 5.0 + 1e-12)
    assert np.all(ax2.get_yticks() >= -80.0 - 1e-12)
    assert np.all(ax2.get_yticks() <= -40.0 + 1e-12)


def test_zero_span_values_outside_window_are_clipped_without_rescaling(qapp):
    del qapp
    widget = DcmZeroSpanWidget()
    _set_axis(widget)

    # 大幅增加校准偏移，让实际 Zero Span 数据越过固定显示上限。
    widget.calibration_db.setValue(100.0)
    widget._on_profile_changed()
    widget._recompute()

    assert widget.current_zero_span is not None
    assert float(np.max(widget.current_zero_span.amplitude_dbm)) > -40.0

    ax1, ax2 = widget.figure.axes
    assert np.allclose(ax1.get_ylim(), (-5.0, 5.0))
    assert np.allclose(ax2.get_ylim(), (-80.0, -40.0))
    assert not ax2.get_autoscaley_on()
