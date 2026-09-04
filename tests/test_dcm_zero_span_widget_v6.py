from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_zero_span_widget_v6 import DcmZeroSpanWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _event(x: float, y: float):
    return SimpleNamespace(xdata=x, ydata=y)


def _inner_bounds(bounds: tuple[float, float], low_ratio=0.25, high_ratio=0.75):
    low, high = bounds
    span = high - low
    return low + span * low_ratio, low + span * high_ratio


def test_only_time_and_frequency_panels_have_rectangle_zoom(qapp):
    del qapp
    widget = DcmZeroSpanWidget()
    assert set(widget._zoom_selectors) == {"time", "frequency"}
    assert len(widget.figure.axes) == 4


def test_time_rectangle_zoom_keeps_zero_span_time_aligned_and_space_restores(qapp):
    del qapp
    widget = DcmZeroSpanWidget()

    ax_time, ax_freq, ax_zero, _ = widget.figure.axes
    base_time_xlim = tuple(ax_time.get_xlim())
    base_time_ylim = tuple(ax_time.get_ylim())
    base_zero_ylim = tuple(ax_zero.get_ylim())
    base_freq_xlim = tuple(ax_freq.get_xlim())

    zoom_x = _inner_bounds(base_time_xlim)
    zoom_y = _inner_bounds(base_time_ylim)
    widget._on_zoom_rectangle(
        "time",
        _event(zoom_x[0], zoom_y[0]),
        _event(zoom_x[1], zoom_y[1]),
    )

    ax_time, ax_freq, ax_zero, _ = widget.figure.axes
    assert np.allclose(ax_time.get_xlim(), zoom_x)
    assert np.allclose(ax_time.get_ylim(), zoom_y)
    assert np.allclose(ax_zero.get_xlim(), zoom_x)
    assert np.allclose(ax_zero.get_ylim(), base_zero_ylim)
    assert np.allclose(ax_freq.get_xlim(), base_freq_xlim)

    widget._on_zoom_key_press(SimpleNamespace(key="space"))

    ax_time, _, ax_zero, _ = widget.figure.axes
    assert np.allclose(ax_time.get_xlim(), base_time_xlim)
    assert np.allclose(ax_time.get_ylim(), base_time_ylim)
    assert np.allclose(ax_zero.get_xlim(), base_time_xlim)


def test_frequency_rectangle_zoom_is_independent_and_space_restores(qapp):
    del qapp
    widget = DcmZeroSpanWidget()

    ax_time, ax_freq, ax_zero, _ = widget.figure.axes
    base_time_xlim = tuple(ax_time.get_xlim())
    base_zero_xlim = tuple(ax_zero.get_xlim())
    base_freq_xlim = tuple(ax_freq.get_xlim())
    base_freq_ylim = tuple(ax_freq.get_ylim())
    base_controls = (
        widget.freq_x_min.value(),
        widget.freq_x_max.value(),
        widget.freq_y_min.value(),
        widget.freq_y_max.value(),
    )

    zoom_x = _inner_bounds(base_freq_xlim, 0.2, 0.6)
    zoom_y = _inner_bounds(base_freq_ylim, 0.3, 0.7)
    widget._on_zoom_rectangle(
        "frequency",
        _event(zoom_x[0], zoom_y[0]),
        _event(zoom_x[1], zoom_y[1]),
    )

    ax_time, ax_freq, ax_zero, _ = widget.figure.axes
    assert np.allclose(ax_freq.get_xlim(), zoom_x)
    assert np.allclose(ax_freq.get_ylim(), zoom_y)
    assert np.allclose(ax_time.get_xlim(), base_time_xlim)
    assert np.allclose(ax_zero.get_xlim(), base_zero_xlim)
    assert np.allclose(
        (
            widget.freq_x_min.value(),
            widget.freq_x_max.value(),
            widget.freq_y_min.value(),
            widget.freq_y_max.value(),
        ),
        base_controls,
    )

    widget._on_zoom_key_press(SimpleNamespace(key=" "))
    ax_freq = widget.figure.axes[1]
    assert np.allclose(ax_freq.get_xlim(), base_freq_xlim)
    assert np.allclose(ax_freq.get_ylim(), base_freq_ylim)


def test_zoom_window_survives_dcm_recompute_until_space(qapp):
    del qapp
    widget = DcmZeroSpanWidget()

    ax_time = widget.figure.axes[0]
    zoom_x = _inner_bounds(tuple(ax_time.get_xlim()), 0.35, 0.65)
    zoom_y = _inner_bounds(tuple(ax_time.get_ylim()), 0.25, 0.75)
    widget._on_zoom_rectangle(
        "time",
        _event(zoom_x[0], zoom_y[0]),
        _event(zoom_x[1], zoom_y[1]),
    )

    control = widget._parameter_controls["rise_spike_amplitude_v"]
    control.setValue(control.value() + 1.0)
    widget._on_parameter_changed("rise_spike_amplitude_v", control.value())
    widget._recompute()

    ax_time, _, ax_zero, _ = widget.figure.axes
    assert np.allclose(ax_time.get_xlim(), zoom_x)
    assert np.allclose(ax_time.get_ylim(), zoom_y)
    assert np.allclose(ax_zero.get_xlim(), zoom_x)

    widget._on_zoom_key_press(SimpleNamespace(key="space"))
    assert widget._zoom_ranges["time"] is None
