from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_zero_span_widget_v7 import DcmZeroSpanWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_frequency_axis_is_automatic_by_default_and_tracks_sample_rate(qapp):
    del qapp
    widget = DcmZeroSpanWidget()

    assert widget.freq_auto_axis.isChecked()
    ax_freq = widget.figure.axes[1]
    initial_xlim = ax_freq.get_xlim()
    assert initial_xlim[0] == pytest.approx(0.0)
    assert initial_xlim[1] == pytest.approx(1000.0, rel=1e-3)

    # 采样率从 2 GSa/s 改为 1 GSa/s，完整单边频域 Nyquist 自动变成 500 MHz。
    widget._on_parameter_changed("sample_rate_hz", 1.0)
    widget._recompute()

    assert widget.freq_auto_axis.isChecked()
    ax_freq = widget.figure.axes[1]
    assert ax_freq.get_xlim()[0] == pytest.approx(0.0)
    assert ax_freq.get_xlim()[1] == pytest.approx(500.0, rel=1e-3)


def test_manual_frequency_axis_input_disables_auto_and_stays_fixed(qapp):
    del qapp
    widget = DcmZeroSpanWidget()
    assert widget.freq_auto_axis.isChecked()

    # 任一手动坐标输入都应自动切换为手动模式。
    widget.freq_x_max.setValue(300.0)
    assert not widget.freq_auto_axis.isChecked()

    widget.freq_x_min.setValue(0.0)
    widget.freq_x_step.setValue(50.0)
    widget.freq_y_min.setValue(-180.0)
    widget.freq_y_max.setValue(20.0)
    widget.freq_y_step.setValue(20.0)

    ax_freq = widget.figure.axes[1]
    assert np.allclose(ax_freq.get_xlim(), (0.0, 300.0))
    assert np.allclose(ax_freq.get_ylim(), (-180.0, 20.0))
    assert np.allclose(ax_freq.get_xticks(), [0, 50, 100, 150, 200, 250, 300])

    # 手动模式下即使 DCM/FFT 重新计算，用户坐标也不能被自动改写。
    widget._on_parameter_changed("sample_rate_hz", 1.0)
    widget._recompute()
    ax_freq = widget.figure.axes[1]
    assert not widget.freq_auto_axis.isChecked()
    assert np.allclose(ax_freq.get_xlim(), (0.0, 300.0))
    assert np.allclose(ax_freq.get_ylim(), (-180.0, 20.0))


def test_reenable_auto_frequency_axis_restores_data_driven_range(qapp):
    del qapp
    widget = DcmZeroSpanWidget()

    widget.freq_x_max.setValue(300.0)
    assert not widget.freq_auto_axis.isChecked()

    widget.freq_auto_axis.setChecked(True)
    assert widget.freq_auto_axis.isChecked()

    ax_freq = widget.figure.axes[1]
    assert ax_freq.get_xlim()[0] == pytest.approx(0.0)
    assert ax_freq.get_xlim()[1] == pytest.approx(1000.0, rel=1e-3)
