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


def _widget_for_default_waveform() -> DcmParameterExtractorWidget:
    waveform = generate_dcm_sw_waveform(DcmSwParameters(noise_rms_v=0.01))
    widget = DcmParameterExtractorWidget()
    widget.set_waveform(waveform.time_s, waveform.voltage_v, source_name="synthetic-unified")
    return widget


def test_main_editable_parameters_match_generator_model(qapp):
    del qapp
    widget = _widget_for_default_waveform()

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
        "fall_spike_amplitude_v",
        "spike_ringing_frequency_hz",
        "spike_decay_rate_per_s",
        "discontinuous_initial_amplitude_v",
        "discontinuous_resonance_frequency_hz",
        "discontinuous_decay_rate_per_s",
    }
    assert expected == set(widget.parameter_controls)
    assert all(control.isEnabled() for control in widget.parameter_controls.values())
    assert widget.current_parameters is not None
    assert widget.current_fit_result is not None

    # phase 仍可存在于自动拟合内部，但不再作为客户主参数。
    assert "rise_spike_phase_rad" not in widget.parameter_controls
    assert "fall_spike_phase_rad" not in widget.parameter_controls
    assert "dcm_phase_rad" not in widget.parameter_controls


def test_spike_frequency_and_decay_really_change_reconstruction(qapp):
    del qapp
    widget = _widget_for_default_waveform()
    assert widget.current_fit_result is not None

    original = widget.current_fit_result.reconstruction_v.copy()
    freq = widget.parameter_controls["spike_ringing_frequency_hz"]
    new_freq = freq.value() + 12.0
    freq.setValue(new_freq)
    widget._on_parameter_changed("spike_ringing_frequency_hz", new_freq)
    widget._run_current_model()
    assert widget.current_fit_result is not None
    after_frequency = widget.current_fit_result.reconstruction_v.copy()
    assert not np.allclose(after_frequency, original)

    decay = widget.parameter_controls["spike_decay_rate_per_s"]
    new_decay = decay.value() + 2.0
    decay.setValue(new_decay)
    widget._on_parameter_changed("spike_decay_rate_per_s", new_decay)
    widget._run_current_model()
    assert widget.current_fit_result is not None
    assert not np.allclose(widget.current_fit_result.reconstruction_v, after_frequency)


def test_dcm_frequency_and_decay_really_change_reconstruction(qapp):
    del qapp
    widget = _widget_for_default_waveform()
    assert widget.current_fit_result is not None

    original = widget.current_fit_result.reconstruction_v.copy()
    freq = widget.parameter_controls["discontinuous_resonance_frequency_hz"]
    new_freq = freq.value() + 1.2
    freq.setValue(new_freq)
    widget._on_parameter_changed("discontinuous_resonance_frequency_hz", new_freq)
    widget._run_current_model()
    assert widget.current_fit_result is not None
    after_frequency = widget.current_fit_result.reconstruction_v.copy()
    assert not np.allclose(after_frequency, original)

    decay = widget.parameter_controls["discontinuous_decay_rate_per_s"]
    new_decay = decay.value() + 0.4
    decay.setValue(new_decay)
    widget._on_parameter_changed("discontinuous_decay_rate_per_s", new_decay)
    widget._run_current_model()
    assert widget.current_fit_result is not None
    assert not np.allclose(widget.current_fit_result.reconstruction_v, after_frequency)


def test_frequency_dependency_is_explicit_when_spike_amplitudes_are_zero(qapp):
    del qapp
    widget = _widget_for_default_waveform()

    for key in ("rise_spike_amplitude_v", "fall_spike_amplitude_v"):
        control = widget.parameter_controls[key]
        control.setValue(0.0)
        widget._on_parameter_changed(key, 0.0)
    widget._run_current_model()

    text = widget._score_items["spike_ringing_frequency_hz"].text()
    assert "当前无效" in text
    assert "尖峰电压均为 0" in text

    # 重新给上升尖峰一个非零值后，频率马上恢复为有效模型参数。
    amp = widget.parameter_controls["rise_spike_amplitude_v"]
    amp.setValue(1.0)
    widget._on_parameter_changed("rise_spike_amplitude_v", 1.0)
    widget._run_current_model()
    assert "当前无效" not in widget._score_items["spike_ringing_frequency_hz"].text()

    before = widget.current_fit_result.reconstruction_v.copy()
    freq = widget.parameter_controls["spike_ringing_frequency_hz"]
    new_freq = freq.value() + 8.0
    freq.setValue(new_freq)
    widget._on_parameter_changed("spike_ringing_frequency_hz", new_freq)
    widget._run_current_model()
    assert widget.current_fit_result is not None
    assert not np.allclose(widget.current_fit_result.reconstruction_v, before)


def test_restore_all_auto_values(qapp):
    del qapp
    widget = _widget_for_default_waveform()
    auto_on_us = widget.result.on_time_s * 1e6

    widget.parameter_controls["on_time_s"].setValue(auto_on_us + 0.4)
    widget._on_parameter_changed("on_time_s", auto_on_us + 0.4)
    widget._run_current_model()

    widget._restore_all_auto_values()
    assert widget.parameter_controls["on_time_s"].value() == pytest.approx(auto_on_us, abs=1e-6)
    assert widget.current_parameters is not None
    assert widget.current_parameters.on_time_s == pytest.approx(widget.result.on_time_s, abs=1e-12)
