from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_zero_span_widget_v5 import DcmZeroSpanWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _set_frequency_axis(widget: DcmZeroSpanWidget) -> None:
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
        widget.freq_x_min.setValue(0.0)
        widget.freq_x_max.setValue(500.0)
        widget.freq_x_step.setValue(100.0)
        widget.freq_y_min.setValue(-160.0)
        widget.freq_y_max.setValue(20.0)
        widget.freq_y_step.setValue(20.0)
    finally:
        for spin in spins:
            spin.blockSignals(False)
    widget._on_frequency_axis_changed()


def test_frequency_axis_controls_exist(qapp):
    del qapp
    widget = DcmZeroSpanWidget()
    for name in (
        "freq_x_min",
        "freq_x_max",
        "freq_x_step",
        "freq_y_min",
        "freq_y_max",
        "freq_y_step",
    ):
        assert hasattr(widget, name)
    assert "坐标轴" in widget.axis_display_toggle.text()


def test_frequency_x_y_range_and_steps_are_strictly_fixed(qapp):
    del qapp
    widget = DcmZeroSpanWidget()
    _set_frequency_axis(widget)

    assert len(widget.figure.axes) == 4
    ax_freq = widget.figure.axes[1]

    assert np.allclose(ax_freq.get_xlim(), (0.0, 500.0))
    assert np.allclose(ax_freq.get_ylim(), (-160.0, 20.0))
    assert not ax_freq.get_autoscalex_on()
    assert not ax_freq.get_autoscaley_on()

    assert np.allclose(ax_freq.get_xticks(), [0.0, 100.0, 200.0, 300.0, 400.0, 500.0])
    assert np.allclose(
        ax_freq.get_yticks(),
        [-160.0, -140.0, -120.0, -100.0, -80.0, -60.0, -40.0, -20.0, 0.0, 20.0],
    )


def test_frequency_axes_do_not_expand_after_dcm_recompute(qapp):
    del qapp
    widget = DcmZeroSpanWidget()
    _set_frequency_axis(widget)

    before_frequency = widget.current_spectrum_amplitude_dbv.copy()

    control = widget._parameter_controls["spike_ringing_frequency_hz"]
    control.setValue(400.0)
    widget._on_parameter_changed("spike_ringing_frequency_hz", control.value())
    widget._recompute()

    assert len(widget.current_spectrum_amplitude_dbv) == len(before_frequency)
    assert not np.allclose(before_frequency, widget.current_spectrum_amplitude_dbv)

    ax_freq = widget.figure.axes[1]
    assert np.allclose(ax_freq.get_xlim(), (0.0, 500.0))
    assert np.allclose(ax_freq.get_ylim(), (-160.0, 20.0))
    assert not ax_freq.get_autoscalex_on()
    assert not ax_freq.get_autoscaley_on()
