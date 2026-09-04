from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_parameter_extractor import (
    extract_dcm_basic_parameters,
    load_waveform_csv,
)
from scope_zero_span_converter.dcm_parameter_extractor_widget import DcmParameterExtractorWidget
from scope_zero_span_converter.dcm_sw_generator import DcmSwParameters, generate_dcm_sw_waveform


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_extracts_default_generated_waveform_without_truth_columns():
    parameters = DcmSwParameters()
    waveform = generate_dcm_sw_waveform(parameters)

    result = extract_dcm_basic_parameters(waveform.time_s, waveform.voltage_v)

    assert result.sample_rate_hz == pytest.approx(parameters.sample_rate_hz, rel=1e-6)
    assert result.baseline_voltage_v == pytest.approx(parameters.baseline_voltage_v, abs=0.03)
    assert result.on_high_voltage_v == pytest.approx(parameters.on_high_voltage_v, abs=0.03)
    assert result.freewheel_low_voltage_v == pytest.approx(
        parameters.freewheel_low_voltage_v, abs=0.03
    )
    assert result.switching_start_s == pytest.approx(parameters.switching_start_s, abs=2e-9)
    assert result.rise_time_s == pytest.approx(parameters.rise_time_s, abs=2e-9)
    assert result.on_time_s == pytest.approx(parameters.on_time_s, abs=5e-9)
    assert result.fall_time_s == pytest.approx(parameters.fall_time_s, abs=2e-9)
    assert result.freewheel_time_s == pytest.approx(parameters.freewheel_time_s, abs=30e-9)
    assert result.overall_confidence > 0.8
    assert len(result.fitted_ideal_voltage_v) == waveform.points
    assert np.all(np.isfinite(result.residual_v))


def test_extracts_varied_generated_waveform():
    parameters = DcmSwParameters(
        baseline_voltage_v=-0.12,
        on_high_voltage_v=24.0,
        freewheel_low_voltage_v=0.75,
        total_duration_s=24e-6,
        switching_start_s=2.5e-6,
        rise_time_s=100e-9,
        on_time_s=4.2e-6,
        fall_time_s=80e-9,
        freewheel_time_s=3.0e-6,
        rise_spike_amplitude_v=2.0,
        fall_spike_amplitude_v=-3.5,
        spike_ringing_frequency_hz=80e6,
        spike_decay_rate_per_s=10e6,
        discontinuous_initial_amplitude_v=1.8,
        discontinuous_resonance_frequency_hz=4e6,
        discontinuous_decay_rate_per_s=0.7e6,
        noise_rms_v=0.03,
        sample_rate_hz=2e9,
        random_seed=2026,
    )
    waveform = generate_dcm_sw_waveform(parameters)
    result = extract_dcm_basic_parameters(waveform.time_s, waveform.voltage_v)

    assert result.baseline_voltage_v == pytest.approx(parameters.baseline_voltage_v, abs=0.04)
    assert result.on_high_voltage_v == pytest.approx(parameters.on_high_voltage_v, abs=0.04)
    assert result.freewheel_low_voltage_v == pytest.approx(
        parameters.freewheel_low_voltage_v, abs=0.04
    )
    assert result.switching_start_s == pytest.approx(parameters.switching_start_s, abs=3e-9)
    assert result.rise_time_s == pytest.approx(parameters.rise_time_s, abs=3e-9)
    assert result.on_time_s == pytest.approx(parameters.on_time_s, abs=8e-9)
    assert result.fall_time_s == pytest.approx(parameters.fall_time_s, abs=3e-9)
    assert result.freewheel_time_s == pytest.approx(parameters.freewheel_time_s, abs=60e-9)


def test_ideal_zero_rise_and_fall_are_recognized_as_zero():
    parameters = DcmSwParameters(
        rise_time_s=0.0,
        fall_time_s=0.0,
        rise_spike_amplitude_v=0.0,
        fall_spike_amplitude_v=0.0,
        discontinuous_initial_amplitude_v=0.0,
        noise_rms_v=0.0,
    )
    waveform = generate_dcm_sw_waveform(parameters)
    result = extract_dcm_basic_parameters(waveform.time_s, waveform.voltage_v)

    assert result.rise_time_s == 0.0
    assert result.fall_time_s == 0.0
    assert result.on_time_s == pytest.approx(parameters.on_time_s, abs=2e-9)
    assert result.freewheel_time_s == pytest.approx(parameters.freewheel_time_s, abs=10e-9)


def test_csv_loader_ignores_synthetic_truth_columns(tmp_path):
    parameters = DcmSwParameters(noise_rms_v=0.0)
    waveform = generate_dcm_sw_waveform(parameters)
    csv_path = tmp_path / "waveform_with_truth.csv"
    pd.DataFrame(
        {
            "time_s": waveform.time_s,
            "voltage_v": waveform.voltage_v,
            "ideal_voltage_v": np.full(waveform.points, 9999.0),
            "fake_truth": np.full(waveform.points, -123.0),
        }
    ).to_csv(csv_path, index=False)

    time_s, voltage_v = load_waveform_csv(csv_path)
    result = extract_dcm_basic_parameters(time_s, voltage_v)

    # CSV 文本往返会产生机器精度级的浮点末位差异，应按数值等价比较。
    assert np.allclose(time_s, waveform.time_s, rtol=0.0, atol=1e-18)
    assert np.allclose(voltage_v, waveform.voltage_v, rtol=1e-14, atol=1e-14)
    assert result.on_high_voltage_v == pytest.approx(parameters.on_high_voltage_v, abs=0.02)


def test_extractor_widget_defaults_to_main_overlay_and_can_show_residual(qapp):
    del qapp
    parameters = DcmSwParameters(noise_rms_v=0.0)
    waveform = generate_dcm_sw_waveform(parameters)

    widget = DcmParameterExtractorWidget()
    widget.set_waveform(waveform.time_s, waveform.voltage_v, source_name="synthetic")

    assert widget.result is not None
    assert widget.ringing_result is not None
    assert widget.result_table.rowCount() >= 20
    assert len(widget.figure.axes) == 1

    table_names = {
        widget.result_table.item(row, 0).text()
        for row in range(widget.result_table.rowCount())
    }
    assert "【尖峰】上升沿初始尖峰电压" in table_names
    assert "【尖峰】下降沿初始尖峰电压" in table_names
    assert "【振铃】共享寄生振铃频率" in table_names
    assert "【振铃】共享衰减速率" in table_names

    widget.show_residual_check.setChecked(True)
    assert len(widget.figure.axes) == 2
    assert len(widget.figure.axes[1].lines) >= 4
