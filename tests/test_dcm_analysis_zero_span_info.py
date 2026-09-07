from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_analysis_widget import DcmAnalysisWidget
from scope_zero_span_converter.dcm_zero_span_link import ZeroSpanProfile


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_zero_span_info_card_reports_default_measurement_window(qapp):
    del qapp
    widget = DcmAnalysisWidget()

    assert widget.zero_span_info_label is not None
    text = widget.zero_span_info_label.text()

    assert "状态：有效" in text
    assert "Span=0 Hz" in text
    assert "Center=200 MHz" in text
    assert "RBW=10 MHz" in text
    assert "195~205 MHz" in text
    assert "Detector=RMS" in text


def test_zero_span_info_card_explains_invalid_center_bandwidth_combination(qapp):
    del qapp
    widget = DcmAnalysisWidget()
    widget.profile = ZeroSpanProfile(
        center_frequency_hz=1e9,
        rbw_hz=10e6,
        vbw_hz=10e6,
        vbw_enabled=True,
        impedance_ohm=50.0,
        calibration_db=0.0,
        scope_analog_bandwidth_hz=350e6,
    )
    widget._apply_profile_to_controls(widget.profile)
    widget._recompute()

    assert widget.zero_span_info_label is not None
    text = widget.zero_span_info_label.text()

    assert "状态：不可计算" in text
    assert "Center=1000 MHz" in text
    assert "995~1005 MHz" in text
    assert "原因：" in text
    assert "模拟带宽" in text
