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


def test_time_marker_ab_readout_and_delta(qapp):
    del qapp
    widget = DcmAnalysisWidget()
    waveform = widget.current_waveform
    assert waveform is not None
    assert widget.time_marker_a_enable is not None
    assert widget.time_marker_b_enable is not None
    assert widget.time_marker_a_time_us is not None
    assert widget.time_marker_b_time_us is not None
    assert widget.time_marker_info_label is not None

    index_a = max(1, len(waveform.time_s) // 4)
    index_b = max(index_a + 1, 3 * len(waveform.time_s) // 4)
    target_a_us = float(waveform.time_s[index_a]) * 1e6
    target_b_us = float(waveform.time_s[index_b]) * 1e6

    widget.time_marker_a_time_us.setValue(target_a_us)
    widget.time_marker_b_time_us.setValue(target_b_us)
    widget.time_marker_a_enable.setChecked(True)
    widget.time_marker_b_enable.setChecked(True)

    marker_a, marker_b = widget._current_time_markers()
    assert marker_a is not None and marker_b is not None
    assert marker_a.time_s == pytest.approx(waveform.time_s[index_a], abs=1e-15)
    assert marker_b.time_s == pytest.approx(waveform.time_s[index_b], abs=1e-15)

    text = widget.time_marker_info_label.text()
    assert "A:" in text
    assert "B:" in text
    assert "ΔT=" in text
    assert "ΔV=" in text


def test_time_markers_overlay_both_left_panels_without_expanding_axes(qapp):
    del qapp
    widget = DcmAnalysisWidget()
    waveform = widget.current_waveform
    assert waveform is not None

    target_a_us = float(waveform.time_s[len(waveform.time_s) // 3]) * 1e6
    target_b_us = float(waveform.time_s[2 * len(waveform.time_s) // 3]) * 1e6
    widget.time_marker_a_time_us.setValue(target_a_us)
    widget.time_marker_b_time_us.setValue(target_b_us)
    widget.time_marker_a_enable.setChecked(True)
    widget.time_marker_b_enable.setChecked(True)

    ax_time = widget.figure.axes[0]
    ax_zero = widget.figure.axes[2]
    time_xlim = ax_time.get_xlim()
    time_ylim = ax_time.get_ylim()
    zero_xlim = ax_zero.get_xlim()
    zero_ylim = ax_zero.get_ylim()

    widget._redraw(zero_span_error=widget.current_zero_span_error)

    ax_time = widget.figure.axes[0]
    ax_zero = widget.figure.axes[2]
    assert np.allclose(ax_time.get_xlim(), time_xlim)
    assert np.allclose(ax_time.get_ylim(), time_ylim)
    assert np.allclose(ax_zero.get_xlim(), zero_xlim)
    assert np.allclose(ax_zero.get_ylim(), zero_ylim)

    # DCM panel: 2 waveform traces + 2 vertical marker lines + 2 marker points.
    assert len(ax_time.lines) >= 6
    # Zero Span panel: waveform plus two matching vertical marker lines.
    assert len(ax_zero.lines) >= 3


def test_time_marker_voltage_refreshes_after_dcm_parameter_change(qapp):
    del qapp
    widget = DcmAnalysisWidget()
    waveform = widget.current_waveform
    assert waveform is not None

    high_region_time_s = 0.5 * (
        waveform.events.rise_end_s + waveform.events.high_end_s
    )
    high_region_index = int(np.argmin(np.abs(waveform.time_s - high_region_time_s)))
    marker_time_us = float(waveform.time_s[high_region_index]) * 1e6
    widget.time_marker_a_time_us.setValue(marker_time_us)
    widget.time_marker_a_enable.setChecked(True)
    before, _ = widget._current_time_markers()
    assert before is not None

    control = widget._parameter_controls["on_high_voltage_v"]
    control.setValue(control.value() + 2.0)
    widget._on_parameter_changed("on_high_voltage_v", control.value())
    widget._recompute()

    after, _ = widget._current_time_markers()
    assert after is not None
    assert after.time_s == pytest.approx(before.time_s, abs=1e-15)
    assert after.voltage_v != pytest.approx(before.voltage_v)
