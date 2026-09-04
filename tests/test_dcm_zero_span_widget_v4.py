from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_zero_span_widget_v4 import DcmZeroSpanWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_four_panel_layout_keeps_original_time_plots_aligned_on_left(qapp):
    del qapp
    widget = DcmZeroSpanWidget()
    assert widget.current_waveform is not None
    assert widget.current_zero_span is not None
    assert len(widget.figure.axes) == 4

    ax_time, ax_freq, ax_zero, ax_reserved = widget.figure.axes
    assert ax_time.get_title() == "DCM SW 时域波形"
    assert "DCM 完整频域" in ax_freq.get_title()
    assert "Zero Span" in ax_zero.get_title()
    assert ax_reserved.get_title() == "预留分析区"

    # 左上/左下必须共享同一个绝对时间轴，并且视图范围完全一致。
    assert ax_time.get_shared_x_axes().joined(ax_time, ax_zero)
    assert np.allclose(ax_time.get_xlim(), ax_zero.get_xlim())
    expected = (
        widget.current_waveform.time_s[0] * 1e6,
        widget.current_waveform.time_s[-1] * 1e6,
    )
    assert np.allclose(ax_time.get_xlim(), expected)


def test_frequency_panel_contains_center_and_rbw_context(qapp):
    del qapp
    widget = DcmZeroSpanWidget()
    ax_freq = widget.figure.axes[1]

    labels = [line.get_label() for line in ax_freq.lines]
    assert "DCM FFT" in labels
    assert "Zero Span Center" in labels
    # axvspan 会形成 patch；默认 200 MHz / RBW 10 MHz 应在 Nyquist 内。
    assert len(ax_freq.patches) >= 1


def test_dcm_parameter_change_updates_time_zero_span_and_frequency(qapp):
    del qapp
    widget = DcmZeroSpanWidget()
    assert widget.current_waveform is not None
    assert widget.current_zero_span is not None
    assert len(widget.current_spectrum_amplitude_dbv) > 0

    before_time = widget.current_waveform.voltage_v.copy()
    before_zero = widget.current_zero_span.amplitude_dbm.copy()
    before_spectrum = widget.current_spectrum_amplitude_dbv.copy()

    control = widget._parameter_controls["on_high_voltage_v"]
    control.setValue(control.value() + 2.0)
    widget._on_parameter_changed("on_high_voltage_v", control.value())
    widget._recompute()

    assert widget.current_waveform is not None
    assert widget.current_zero_span is not None
    assert len(widget.current_spectrum_amplitude_dbv) == len(before_spectrum)
    assert not np.allclose(before_time, widget.current_waveform.voltage_v)
    assert not np.allclose(before_zero, widget.current_zero_span.amplitude_dbm)
    assert not np.allclose(before_spectrum, widget.current_spectrum_amplitude_dbv)
