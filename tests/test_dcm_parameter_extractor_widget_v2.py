from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_parameter_extractor_widget_v2 import (
    DcmParameterExtractorWidget,
)
from scope_zero_span_converter.dcm_sw_generator import DcmSwParameters, generate_dcm_sw_waveform


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_third_stage_widget_reports_dcm_and_final_residual(qapp):
    del qapp
    waveform = generate_dcm_sw_waveform(DcmSwParameters())

    widget = DcmParameterExtractorWidget()
    widget.set_waveform(waveform.time_s, waveform.voltage_v, source_name="synthetic-v3")

    assert widget.result is not None
    assert widget.ringing_result is not None
    assert widget.dcm_result is not None
    assert len(widget.figure.axes) == 1

    names = [
        widget.result_table.item(row, 0).text()
        for row in range(widget.result_table.rowCount())
        if widget.result_table.item(row, 0) is not None
    ]
    assert "【DCM】断续谐振初始振幅" in names
    assert "【DCM】断续谐振频率" in names
    assert "【DCM】断续谐振衰减速率" in names
    assert "【噪声】最终残差 robust RMS" in names

    widget.show_residual_check.setChecked(True)
    assert len(widget.figure.axes) == 2

    main_labels = [line.get_label() for line in widget.figure.axes[0].lines]
    residual_labels = [line.get_label() for line in widget.figure.axes[1].lines]
    assert "基础 + 尖峰/振铃 + DCM 完整拟合" in main_labels
    assert "DCM 断续谐振拟合分量" in residual_labels
    assert "最终残差 ≈ 噪声 + 模型误差" in residual_labels
