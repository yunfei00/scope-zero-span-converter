from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.gui_v05 import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_waveform_research_status_exposes_sampling_quality(qapp, tmp_path):
    del qapp
    fs = 1e9
    t = np.arange(10_000, dtype=float) / fs
    v = 0.2 * np.cos(2.0 * np.pi * 200e6 * t)
    path = tmp_path / "waveform.csv"
    pd.DataFrame({"time_s": t, "voltage_v": v}).to_csv(path, index=False)

    window = MainWindow()
    window.waveform_edit.setText(str(path))
    window.load_waveform_from_ui()

    text = window.status_label.text()
    assert "数据质量" in text
    assert "PASS" in text
    assert "Nyquist=" in text
    assert "Fs=" in text
