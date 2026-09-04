from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_zero_span_widget import DcmZeroSpanWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_zero_span_parameters_are_collapsed_by_default(qapp):
    del qapp
    widget = DcmZeroSpanWidget()
    assert not widget.zero_span_toggle.isChecked()
    assert not widget.zero_span_panel.isVisible()
    assert len(widget._parameter_controls) == 20


def test_dcm_slider_value_change_updates_both_waveforms(qapp):
    del qapp
    widget = DcmZeroSpanWidget()
    assert widget.current_waveform is not None
    assert widget.current_zero_span is not None

    before_scope = widget.current_waveform.voltage_v.copy()
    before_zero = widget.current_zero_span.amplitude_dbm.copy()

    control = widget._parameter_controls["on_high_voltage_v"]
    control.spin.setValue(control.value() + 2.0)
    widget._recompute()

    assert widget.current_waveform is not None
    assert widget.current_zero_span is not None
    assert not np.allclose(before_scope, widget.current_waveform.voltage_v)
    assert not np.allclose(before_zero, widget.current_zero_span.amplitude_dbm)


def test_conversion_parameter_change_only_recomputes_zero_span(qapp):
    del qapp
    widget = DcmZeroSpanWidget()
    before_scope = widget.current_waveform.voltage_v.copy()
    before_zero = widget.current_zero_span.amplitude_dbm.copy()

    widget.rbw_mhz.setValue(widget.rbw_mhz.value() * 0.8)
    widget._on_profile_changed()
    widget._recompute()

    assert np.allclose(before_scope, widget.current_waveform.voltage_v)
    assert not np.allclose(before_zero, widget.current_zero_span.amplitude_dbm)
