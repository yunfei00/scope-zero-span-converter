from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_parameter_extractor_widget_v3 import (
    DcmParameterExtractorWidget,
)
from scope_zero_span_converter.dcm_sw_generator import DcmSwParameters, generate_dcm_sw_waveform


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_fourth_stage_widget_runs_global_refinement_and_shows_metrics(qapp):
    del qapp
    waveform = generate_dcm_sw_waveform(
        DcmSwParameters(
            sample_rate_hz=600e6,
            noise_rms_v=0.015,
            random_seed=2026,
        )
    )

    widget = DcmParameterExtractorWidget()
    widget.set_waveform(waveform.time_s, waveform.voltage_v, source_name="synthetic-v4")

    assert widget.result is not None
    assert widget.ringing_result is not None
    assert widget.dcm_result is not None
    assert widget.global_result is None
    assert widget.global_refine_btn.isEnabled()

    widget.run_global_refinement()

    assert widget.global_result is not None
    assert widget.global_result.full_r_squared > 0.99

    names = [
        widget.result_table.item(row, 0).text()
        for row in range(widget.result_table.rowCount())
        if widget.result_table.item(row, 0) is not None
    ]
    assert "【联合】基线电压" in names
    assert "【联合】寄生振铃频率" in names
    assert "【联合】DCM 谐振频率" in names
    assert "【联合】精修前 RMSE" in names
    assert "【联合】精修后 RMSE" in names
    assert "【联合】RMSE 改善" in names

    main_labels = [line.get_label() for line in widget.figure.axes[0].lines]
    assert "全局联合精修重建波形" in main_labels

    widget.show_residual_check.setChecked(True)
    assert len(widget.figure.axes) == 2
    residual_labels = [line.get_label() for line in widget.figure.axes[1].lines]
    assert "联合精修最终残差" in residual_labels
