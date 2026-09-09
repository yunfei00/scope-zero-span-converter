from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_analysis.widget import DcmAnalysisWidget
from scope_zero_span_converter.dcm_analysis_widget import (
    DcmAnalysisWidget as CompatibilityDcmAnalysisWidget,
)
from scope_zero_span_converter.gui_v05 import DcmAnalysisWidget as MainWindowDcmAnalysisWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_main_window_imports_formal_dcm_analysis_widget():
    assert MainWindowDcmAnalysisWidget is DcmAnalysisWidget
    assert CompatibilityDcmAnalysisWidget is DcmAnalysisWidget
    assert DcmAnalysisWidget.__module__ == "scope_zero_span_converter.dcm_analysis.widget"


def test_formal_widget_mro_excludes_versioned_legacy_gui_chain():
    mro_modules = [base.__module__ for base in DcmAnalysisWidget.mro()]

    assert "scope_zero_span_converter.dcm_analysis_widget" not in mro_modules
    assert not any(
        module.rsplit(".", 1)[-1].startswith("dcm_zero_span_widget_v")
        for module in mro_modules
    )


def test_formal_widget_owns_four_panel_layout_and_shared_axes(qapp):
    del qapp
    widget = DcmAnalysisWidget()

    assert widget.current_waveform is not None
    assert widget.current_zero_span is not None
    assert len(widget.figure.axes) == 4

    ax_time, ax_magnitude, ax_zero, ax_phase = widget.figure.axes
    assert "DCM SW 时域波形" in ax_time.get_title()
    assert "DCM 幅度频谱" in ax_magnitude.get_title()
    assert "Zero Span" in ax_zero.get_title()
    assert "DCM 相位频谱" in ax_phase.get_title()

    assert ax_time.get_shared_x_axes().joined(ax_time, ax_zero)
    assert ax_magnitude.get_shared_x_axes().joined(ax_magnitude, ax_phase)
    assert ax_time.get_xlim() == ax_zero.get_xlim()
    assert ax_magnitude.get_xlim() == ax_phase.get_xlim()


def test_frequency_zoom_still_moves_magnitude_and_phase_together(qapp):
    del qapp
    widget = DcmAnalysisWidget()

    target_x = (10.0, 80.0)
    target_y = (-160.0, 10.0)
    widget._zoom_state.push("frequency", (target_x, target_y))
    widget._redraw(zero_span_error=widget.current_zero_span_error)

    _ax_time, ax_magnitude, _ax_zero, ax_phase = widget.figure.axes
    assert ax_magnitude.get_xlim() == pytest.approx(target_x)
    assert ax_phase.get_xlim() == pytest.approx(target_x)
    assert ax_magnitude.get_ylim() == pytest.approx(target_y)


def test_time_zoom_still_moves_dcm_and_zero_span_together(qapp):
    del qapp
    widget = DcmAnalysisWidget()

    target_x = (2.0, 8.0)
    target_y = (-5.0, 20.0)
    widget._zoom_state.push("time", (target_x, target_y))
    widget._redraw(zero_span_error=widget.current_zero_span_error)

    ax_time, _ax_magnitude, ax_zero, _ax_phase = widget.figure.axes
    assert ax_time.get_xlim() == pytest.approx(target_x)
    assert ax_zero.get_xlim() == pytest.approx(target_x)
    assert ax_time.get_ylim() == pytest.approx(target_y)
