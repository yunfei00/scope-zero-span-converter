from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_parameter_extractor_widget_v7 import (
    DcmParameterExtractorWidget,
)


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


def test_extractor_memory_input_tracks_quality_before_analysis(qapp):
    del qapp
    widget = DcmParameterExtractorWidget()

    # Quality validation happens before the actual DCM-event extraction. The
    # constant waveform may fail later as 'not a DCM event', but the input
    # sampling assumptions must already be recorded as PASS.
    t = np.arange(128, dtype=float) / 1e9
    v = np.zeros_like(t)
    widget.set_waveform(t, v, source_name="uniform-memory")

    assert widget.input_quality_report is not None
    assert widget.input_quality_report.fft_safe is True
    assert widget.input_quality_report.status == "pass"
