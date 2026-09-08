from __future__ import annotations

import os

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_analysis.plots import MAX_DISPLAY_POINTS
from scope_zero_span_converter.main_window import MainWindow


def _qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_formal_main_window_research_plot_reduces_display_only():
    _qapp()
    window = MainWindow()

    points = 120_000
    time_s = np.arange(points, dtype=float) * 1e-9
    voltage_v = np.sin(2.0 * np.pi * 5e6 * time_s)
    voltage_v[54_321] = 9.0

    window.waveform_time = time_s.copy()
    window.waveform_voltage = voltage_v.copy()
    window.waveform_sample_rate = 1e9
    window.current_region = None
    window.region_conversion = None
    window._zoom_to_region = False

    window._redraw_waveform_and_conversion()

    plotted_x = np.asarray(window.figure.axes[0].lines[0].get_xdata(), dtype=float)
    assert len(plotted_x) <= MAX_DISPLAY_POINTS
    assert len(window.waveform_time) == points
    assert len(window.waveform_voltage) == points
    assert window.waveform_voltage[54_321] == 9.0
    assert "显示抽样" in window.figure.axes[0].get_title()
