from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_analysis.widget import DcmAnalysisWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_frequency_has_no_auto_manual_switch_and_starts_with_auto_fit(qapp):
    del qapp
    widget = DcmAnalysisWidget()
    assert not hasattr(widget, "freq_auto_axis")

    ax_freq = widget.figure.axes[1]
    x_min, x_max = ax_freq.get_xlim()
    y_min, y_max = ax_freq.get_ylim()
    assert widget.freq_x_min.value() == pytest.approx(x_min)
    assert widget.freq_x_max.value() == pytest.approx(x_max)
    assert widget.freq_y_min.value() == pytest.approx(y_min)
    assert widget.freq_y_max.value() == pytest.approx(y_max)


def test_manual_frequency_input_changes_current_view_only(qapp):
    del qapp
    widget = DcmAnalysisWidget()

    spins = (
        widget.freq_x_min,
        widget.freq_x_max,
        widget.freq_x_step,
        widget.freq_y_min,
        widget.freq_y_max,
        widget.freq_y_step,
    )
    for spin in spins:
        spin.blockSignals(True)
    try:
        widget.freq_x_min.setValue(100.0)
        widget.freq_x_max.setValue(400.0)
        widget.freq_x_step.setValue(50.0)
        widget.freq_y_min.setValue(-140.0)
        widget.freq_y_max.setValue(0.0)
        widget.freq_y_step.setValue(20.0)
    finally:
        for spin in spins:
            spin.blockSignals(False)

    widget._on_frequency_axis_changed()

    ax_freq = widget.figure.axes[1]
    assert np.allclose(ax_freq.get_xlim(), (100.0, 400.0))
    assert np.allclose(ax_freq.get_ylim(), (-140.0, 0.0))
    assert np.allclose(ax_freq.get_xticks(), [100.0, 150.0, 200.0, 250.0, 300.0, 350.0, 400.0])
    assert np.allclose(ax_freq.get_yticks(), [-140.0, -120.0, -100.0, -80.0, -60.0, -40.0, -20.0, 0.0])


def test_next_dcm_recompute_returns_frequency_to_auto(qapp):
    del qapp
    widget = DcmAnalysisWidget()

    for spin in (
        widget.freq_x_min,
        widget.freq_x_max,
        widget.freq_x_step,
        widget.freq_y_min,
        widget.freq_y_max,
        widget.freq_y_step,
    ):
        spin.blockSignals(True)
    try:
        widget.freq_x_min.setValue(100.0)
        widget.freq_x_max.setValue(400.0)
        widget.freq_x_step.setValue(50.0)
        widget.freq_y_min.setValue(-140.0)
        widget.freq_y_max.setValue(0.0)
        widget.freq_y_step.setValue(20.0)
    finally:
        for spin in (
            widget.freq_x_min,
            widget.freq_x_max,
            widget.freq_x_step,
            widget.freq_y_min,
            widget.freq_y_max,
            widget.freq_y_step,
        ):
            spin.blockSignals(False)
    widget._on_frequency_axis_changed()
    assert np.allclose(widget.figure.axes[1].get_xlim(), (100.0, 400.0))

    # 改变采样率会改变 Nyquist；下一次正常重绘必须重新自动适配频域。
    sample_rate = widget._parameter_controls["sample_rate_hz"]
    sample_rate.setValue(1.0)
    widget._on_parameter_changed("sample_rate_hz", sample_rate.value())
    widget._recompute()

    ax_freq = widget.figure.axes[1]
    x_min, x_max = ax_freq.get_xlim()
    assert x_min <= 1e-9
    assert 499.0 <= x_max <= 501.0
    assert widget.freq_x_min.value() == pytest.approx(x_min)
    assert widget.freq_x_max.value() == pytest.approx(x_max)
    assert widget.freq_y_min.value() == pytest.approx(ax_freq.get_ylim()[0])
    assert widget.freq_y_max.value() == pytest.approx(ax_freq.get_ylim()[1])
