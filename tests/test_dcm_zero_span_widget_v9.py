from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_zero_span_widget_v9 import DcmZeroSpanWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _assert_frequency_controls_match_plot(widget: DcmZeroSpanWidget) -> None:
    ax_freq = widget.figure.axes[1]
    x_min, x_max = ax_freq.get_xlim()
    y_min, y_max = ax_freq.get_ylim()

    assert np.isclose(widget.freq_x_min.value(), x_min, rtol=0.0, atol=1e-6)
    assert np.isclose(widget.freq_x_max.value(), x_max, rtol=0.0, atol=1e-6)
    assert np.isclose(widget.freq_y_min.value(), y_min, rtol=0.0, atol=1e-6)
    assert np.isclose(widget.freq_y_max.value(), y_max, rtol=0.0, atol=1e-6)

    x_ticks = np.asarray(ax_freq.get_xticks(), dtype=float)
    y_ticks = np.asarray(ax_freq.get_yticks(), dtype=float)
    x_step = float(np.median(np.diff(x_ticks)))
    y_step = float(np.median(np.diff(y_ticks)))

    assert np.isclose(widget.freq_x_step.value(), x_step, rtol=0.0, atol=1e-6)
    assert np.isclose(widget.freq_y_step.value(), y_step, rtol=0.0, atol=1e-6)


def test_frequency_auto_axis_is_backfilled_on_startup(qapp):
    del qapp
    widget = DcmZeroSpanWidget()
    _assert_frequency_controls_match_plot(widget)


def test_frequency_auto_axis_is_backfilled_after_fft_update(qapp):
    del qapp
    widget = DcmZeroSpanWidget()

    sample_rate = widget._parameter_controls["sample_rate_hz"]
    sample_rate.setValue(1.0)
    widget._on_parameter_changed("sample_rate_hz", sample_rate.value())
    widget._recompute()

    ax_freq = widget.figure.axes[1]
    x_min, x_max = ax_freq.get_xlim()
    assert x_min <= 1e-9
    assert 499.0 <= x_max <= 501.0
    assert 499.0 <= widget.freq_x_max.value() <= 501.0
    _assert_frequency_controls_match_plot(widget)


def test_manual_input_current_frame_still_works_and_next_update_refills(qapp):
    del qapp
    widget = DcmZeroSpanWidget()

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

    # 下一次正常 DCM/FFT 更新恢复自动，并把新的自动坐标回填左侧。
    sample_rate = widget._parameter_controls["sample_rate_hz"]
    sample_rate.setValue(1.0)
    widget._on_parameter_changed("sample_rate_hz", sample_rate.value())
    widget._recompute()

    assert 499.0 <= widget.freq_x_max.value() <= 501.0
    _assert_frequency_controls_match_plot(widget)
