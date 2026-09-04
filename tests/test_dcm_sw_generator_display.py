import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_sw_generator_widget_v2 import DcmSwGeneratorWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_dcm_generator_defaults_to_one_large_main_plot(qapp):
    del qapp
    widget = DcmSwGeneratorWidget()
    widget._generate_silent()

    assert widget.show_truth_components_check.isChecked() is False
    assert widget.current_waveform is not None
    assert len(widget.figure.axes) == 1


def test_truth_component_checkbox_toggles_second_plot(qapp):
    del qapp
    widget = DcmSwGeneratorWidget()
    widget._generate_silent()

    widget.show_truth_components_check.setChecked(True)
    assert len(widget.figure.axes) == 2

    widget.show_truth_components_check.setChecked(False)
    assert len(widget.figure.axes) == 1
