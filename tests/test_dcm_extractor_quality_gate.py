from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_extractor.widget import DcmParameterExtractorWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_extractor_memory_input_rejects_nonuniform_time_axis(qapp):
    del qapp
    widget = DcmParameterExtractorWidget()

    t = np.arange(128, dtype=float) / 1e9
    t[64:] += 1e-9  # one missing-sample-like 2 ns gap
    v = np.zeros_like(t)

    with pytest.raises(ValueError, match="时间轴不适合 FFT / Zero Span"):
        widget.set_waveform(t, v)


def test_extractor_memory_input_rejects_nonfinite_voltage(qapp):
    del qapp
    widget = DcmParameterExtractorWidget()
    t = np.arange(128, dtype=float) / 1e9
    v = np.zeros_like(t)
    v[17] = np.nan

    with pytest.raises(ValueError, match="NaN 或 Inf"):
        widget.set_waveform(t, v)


def test_extractor_memory_input_rejects_shape_mismatch(qapp):
    del qapp
    widget = DcmParameterExtractorWidget()
    t = np.arange(128, dtype=float) / 1e9
    v = np.zeros(127, dtype=float)

    with pytest.raises(ValueError, match="一维且点数一致"):
        widget.set_waveform(t, v)


def test_extractor_memory_input_tracks_quality_before_analysis(qapp, monkeypatch):
    del qapp
    widget = DcmParameterExtractorWidget()

    # This test only verifies the formal input gate. Do not continue into the
    # actual DCM-event extractor with a constant signal: the real GUI correctly
    # reports that failure through a modal QMessageBox, which would block a
    # headless CI runner forever waiting for a user click.
    downstream_calls: list[tuple[int, str]] = []

    def fake_run_extraction(self):
        downstream_calls.append((len(self.time_s), self.file_label.text()))

    monkeypatch.setattr(DcmParameterExtractorWidget, "run_extraction", fake_run_extraction)

    t = np.arange(128, dtype=float) / 1e9
    v = np.zeros_like(t)
    widget.set_waveform(t, v, source_name="uniform-memory")

    assert widget.input_quality_report is not None
    assert widget.input_quality_report.fft_safe is True
    assert widget.input_quality_report.status == "pass"
    assert downstream_calls
    assert downstream_calls[0][0] == len(t)
    assert "数据质量" in downstream_calls[0][1]
