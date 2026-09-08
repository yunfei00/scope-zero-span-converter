from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_analysis.widget import DcmAnalysisWidget
from scope_zero_span_converter.dcm_analysis.zoom_interaction import ZoomInteractionMixin


def _qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_formal_widget_owns_zoom_runtime_methods():
    _qapp()
    widget = DcmAnalysisWidget()

    assert isinstance(widget, ZoomInteractionMixin)
    assert widget._on_zoom_rectangle.__func__.__module__ == (
        "scope_zero_span_converter.dcm_analysis.zoom_interaction"
    )
    assert widget._apply_zoom_ranges_if_ready.__func__.__module__ == (
        "scope_zero_span_converter.dcm_analysis.zoom_interaction"
    )
    assert widget._on_axis_display_changed.__func__.__module__ == (
        "scope_zero_span_converter.dcm_analysis.zoom_interaction"
    )
