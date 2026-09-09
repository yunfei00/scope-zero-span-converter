from __future__ import annotations

import ast
import os
from pathlib import Path

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMainWindow

from scope_zero_span_converter.batch_worker import BatchWorkerTask
from scope_zero_span_converter.conversion_worker import FullConversionWorkerTask
from scope_zero_span_converter.dcm_analysis.widget import DcmAnalysisWidget
from scope_zero_span_converter.dcm_analysis.plots import MAX_DISPLAY_POINTS
from scope_zero_span_converter.dcm_extractor.widget import DcmParameterExtractorWidget
from scope_zero_span_converter.dcm_generator.widget import DcmSwGeneratorWidget
from scope_zero_span_converter.main_window import MainWindow
import scope_zero_span_converter.main_window as main_window_module
import scope_zero_span_converter.app as app_module
from scope_zero_span_converter.roi_worker import RoiConversionWorkerTask


def _qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _CapturingPool:
    def __init__(self):
        self.tasks = []

    def start(self, task):
        self.tasks.append(task)


def test_formal_main_window_has_no_versioned_gui_inheritance_or_imports():
    assert app_module.MainWindow is MainWindow
    modules = {base.__module__ for base in MainWindow.mro()}
    assert "scope_zero_span_converter.gui_v04" not in modules
    assert "scope_zero_span_converter.gui_v05" not in modules
    assert QMainWindow in MainWindow.mro()

    path = Path(main_window_module.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(name.endswith(("gui_v04", "gui_v05")) for name in imports)


def test_formal_main_window_composes_five_stable_workspaces():
    _qapp()
    window = MainWindow()

    assert window.tabs.count() == 5
    assert [window.tab_id_for_index(index) for index in range(5)] == [
        "waveform_research",
        "dcm_generator",
        "dcm_extractor",
        "dcm_analysis",
        "batch_conversion",
    ]
    assert isinstance(window.dcm_generator_tab, DcmSwGeneratorWidget)
    assert isinstance(window.dcm_extractor_tab, DcmParameterExtractorWidget)
    assert type(window.dcm_analysis_tab) is DcmAnalysisWidget
    assert window.dcm_zero_span_tab is window.dcm_analysis_tab


def test_formal_main_window_dispatches_all_conversion_workers(tmp_path):
    _qapp()
    window = MainWindow()
    pool = _CapturingPool()
    window._worker_pool = pool

    window.run_full_conversion()
    assert isinstance(pool.tasks[-1], FullConversionWorkerTask)
    assert window._conversion_task is pool.tasks[-1]
    assert window.convert_button.isEnabled() is False
    window._release_full_conversion_task()

    window.run_batch_conversion()
    assert isinstance(pool.tasks[-1], BatchWorkerTask)
    assert window._batch_task is pool.tasks[-1]
    assert window.cancel_batch_button.isEnabled() is True
    window.cancel_batch_conversion()
    assert pool.tasks[-1].cancel_requested is True
    window._release_batch_task()

    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text("{}", encoding="utf-8")
    points = 64
    window.waveform_time = np.arange(points, dtype=float) / 1e9
    window.waveform_voltage = np.cos(
        2.0 * np.pi * 200e6 * window.waveform_time
    )
    window.waveform_sample_rate = 1e9
    window.current_region = None
    window.metadata_edit.setText(str(metadata_path))
    window.ROI_BACKGROUND_THRESHOLD_POINTS = 32
    window._roi_generation = 17
    window._redraw_waveform_and_conversion = lambda: None

    window.update_region_conversion()

    assert isinstance(pool.tasks[-1], RoiConversionWorkerTask)
    assert window._roi_task is pool.tasks[-1]
    assert window._roi_active_request_id == 17


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
