from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from scope_zero_span_converter.gui_v05 import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_main_window_exposes_privacy_safe_diagnostic_export(qapp):
    del qapp
    window = MainWindow()

    assert window.export_diagnostics_btn.text() == "导出诊断包"
    tooltip = window.export_diagnostics_btn.toolTip()
    assert "不包含客户波形" in tooltip
    assert "参数文件" in tooltip


def test_failed_waveform_load_does_not_append_quality_for_previous_waveform(
    qapp,
    tmp_path,
    monkeypatch,
):
    del qapp
    fs = 1e9
    t = np.arange(10_000, dtype=float) / fs
    v = 0.2 * np.cos(2.0 * np.pi * 200e6 * t)
    valid = tmp_path / "valid.csv"
    pd.DataFrame({"time_s": t, "voltage_v": v}).to_csv(valid, index=False)

    window = MainWindow()
    window.waveform_edit.setText(str(valid))
    window.load_waveform_from_ui()
    valid_time = window.waveform_time
    status_before = window.status_label.text()
    assert "数据质量" in status_before

    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.Ok)
    window.waveform_edit.setText(str(tmp_path / "does-not-exist.csv"))
    window.load_waveform_from_ui()

    assert window.waveform_time is valid_time
    assert window.status_label.text() == status_before
