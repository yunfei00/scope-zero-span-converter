from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_parameter_extractor_widget_v4 import (
    DcmParameterExtractorWidget,
)
from scope_zero_span_converter.dcm_sw_generator import DcmSwParameters, generate_dcm_sw_waveform


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_manual_on_time_control_updates_curve_and_match_score(qapp):
    del qapp
    waveform = generate_dcm_sw_waveform(DcmSwParameters(noise_rms_v=0.01))

    widget = DcmParameterExtractorWidget()
    widget.set_waveform(waveform.time_s, waveform.voltage_v, source_name="synthetic-manual")

    assert widget.result is not None
    assert widget.manual_on_time.isEnabled()
    assert widget.manual_result is not None
    assert "自动置信度" in widget.manual_auto_label.text()
    assert "当前人工匹配度" in widget.manual_match_label.text()

    original = widget.manual_result.reconstruction_v.copy()
    original_fall_start = widget.manual_result.fall_start_s

    widget.manual_on_time.setValue(widget.manual_on_time.value() + 0.45)
    widget._run_manual_tuning()

    assert widget.manual_result is not None
    assert widget.manual_result.fall_start_s > original_fall_start
    assert not np.allclose(widget.manual_result.reconstruction_v, original)
    assert "当前人工匹配度" in widget.manual_match_label.text()

    labels = [line.get_label() for line in widget.figure.axes[0].lines]
    assert "人工校正重建波形" in labels
    assert "人工下降沿开始" in labels


def test_restore_auto_on_time(qapp):
    del qapp
    waveform = generate_dcm_sw_waveform(DcmSwParameters())
    widget = DcmParameterExtractorWidget()
    widget.set_waveform(waveform.time_s, waveform.voltage_v, source_name="synthetic-reset")

    auto_us = widget.result.on_time_s * 1e6
    widget.manual_on_time.setValue(auto_us + 0.3)
    widget._run_manual_tuning()
    widget._restore_auto_on_time()

    assert widget.manual_on_time.value() == pytest.approx(auto_us, abs=1e-6)
    assert widget.manual_result is not None
    assert widget.manual_result.on_time_s == pytest.approx(widget.result.on_time_s, abs=1e-12)
