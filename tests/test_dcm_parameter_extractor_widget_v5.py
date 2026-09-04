from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_parameter_extractor_widget_v5 import (
    DcmParameterExtractorWidget,
)
from scope_zero_span_converter.dcm_sw_generator import DcmSwParameters, generate_dcm_sw_waveform


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_all_model_parameters_are_inline_editable(qapp):
    del qapp
    waveform = generate_dcm_sw_waveform(DcmSwParameters(noise_rms_v=0.01))
    widget = DcmParameterExtractorWidget()
    widget.set_waveform(waveform.time_s, waveform.voltage_v, source_name="synthetic-full-edit")

    expected = {
        "baseline_voltage_v",
        "on_high_voltage_v",
        "freewheel_low_voltage_v",
        "switching_start_s",
        "rise_time_s",
        "on_time_s",
        "fall_time_s",
        "freewheel_time_s",
        "rise_spike_amplitude_v",
        "rise_spike_phase_rad",
        "fall_spike_amplitude_v",
        "fall_spike_phase_rad",
        "ringing_frequency_hz",
        "ringing_decay_rate_per_s",
        "dcm_initial_amplitude_v",
        "dcm_phase_rad",
        "dcm_frequency_hz",
        "dcm_decay_rate_per_s",
    }
    assert expected == set(widget.parameter_controls)
    assert all(control.isEnabled() for control in widget.parameter_controls.values())
    assert widget.manual_fit_result is not None

    headers = [
        widget.result_table.horizontalHeaderItem(column).text()
        for column in range(widget.result_table.columnCount())
    ]
    assert "滑块 + 数值输入" in headers
    assert "自动置信度 / 当前拟合" in headers


def test_changing_multiple_parameters_updates_reconstruction(qapp):
    del qapp
    waveform = generate_dcm_sw_waveform(DcmSwParameters(noise_rms_v=0.01))
    widget = DcmParameterExtractorWidget()
    widget.set_waveform(waveform.time_s, waveform.voltage_v, source_name="synthetic-live-edit")

    assert widget.manual_fit_result is not None
    original = widget.manual_fit_result.reconstruction_v.copy()
    original_score = widget.manual_fit_result.overall_matching_score

    high_control = widget.parameter_controls["on_high_voltage_v"]
    high_control.setValue(high_control.value() - 0.8)
    widget._on_parameter_changed("on_high_voltage_v", high_control.value())
    widget._run_manual_model()

    assert widget.manual_fit_result is not None
    after_high = widget.manual_fit_result.reconstruction_v.copy()
    assert not np.allclose(after_high, original)

    on_control = widget.parameter_controls["on_time_s"]
    on_control.setValue(on_control.value() + 0.35)
    widget._on_parameter_changed("on_time_s", on_control.value())
    widget._run_manual_model()

    assert widget.manual_fit_result is not None
    assert not np.allclose(widget.manual_fit_result.reconstruction_v, after_high)
    assert widget.manual_fit_result.overall_matching_score != pytest.approx(original_score)

    labels = [line.get_label() for line in widget.figure.axes[0].lines]
    assert "当前可调参数重建波形" in labels
    assert "当前下降沿开始" in labels


def test_restore_all_auto_values(qapp):
    del qapp
    waveform = generate_dcm_sw_waveform(DcmSwParameters())
    widget = DcmParameterExtractorWidget()
    widget.set_waveform(waveform.time_s, waveform.voltage_v, source_name="synthetic-restore-all")

    auto_on_us = widget.result.on_time_s * 1e6
    widget.parameter_controls["on_time_s"].setValue(auto_on_us + 0.4)
    widget._on_parameter_changed("on_time_s", auto_on_us + 0.4)
    widget._run_manual_model()

    widget._restore_all_auto_values()
    assert widget.parameter_controls["on_time_s"].value() == pytest.approx(auto_on_us, abs=1e-6)
    assert widget.manual_parameters is not None
    assert widget.manual_parameters.on_time_s == pytest.approx(widget.result.on_time_s, abs=1e-12)
