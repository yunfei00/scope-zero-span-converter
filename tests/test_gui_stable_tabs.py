from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter import __version__
from scope_zero_span_converter.gui_v05 import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_main_window_uses_stable_tab_ids(qapp):
    del qapp
    window = MainWindow()

    expected = {
        "waveform_research": window.research_tab,
        "dcm_generator": window.dcm_generator_tab,
        "dcm_extractor": window.dcm_extractor_tab,
        "dcm_analysis": window.dcm_analysis_tab,
        "batch_conversion": window.batch_tab,
    }

    for tab_id, widget in expected.items():
        index = window.tabs.indexOf(widget)
        assert index >= 0
        assert window.tab_id_for_index(index) == tab_id
        assert window.index_for_tab_id(tab_id) == index

    assert window.tabs.tabText(window.tabs.indexOf(window.dcm_analysis_tab)) == "DCM 综合分析"
    assert __version__ in window.windowTitle()
