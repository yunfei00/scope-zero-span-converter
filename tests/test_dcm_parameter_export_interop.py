from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import asdict

import numpy as np
import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_parameter_extractor_widget_v7 import (
    DcmParameterExtractorWidget,
)
from scope_zero_span_converter.dcm_sw_generator import (
    DcmSwParameters,
    generate_dcm_sw_waveform,
    parameters_from_dict,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_generator_loads_parameter_extraction_result_json_shape():
    expected = DcmSwParameters(
        baseline_voltage_v=0.2,
        on_high_voltage_v=11.7,
        freewheel_low_voltage_v=0.9,
        time_origin_s=5e-6,
        total_duration_s=12e-6,
        switching_start_s=6.8e-6,
        on_time_s=3.2e-6,
        freewheel_time_s=2.2e-6,
        rise_time_s=35e-9,
        fall_time_s=48e-9,
        rise_spike_amplitude_v=2.6,
        fall_spike_amplitude_v=-3.5,
        spike_ringing_frequency_hz=72e6,
        spike_decay_rate_per_s=9e6,
        discontinuous_initial_amplitude_v=2.1,
        discontinuous_resonance_frequency_hz=6.2e6,
        discontinuous_decay_rate_per_s=1.1e6,
        noise_rms_v=0.018,
        sample_rate_hz=2e9,
        random_seed=0,
    )
    raw = {
        "algorithm": "dcm_parameter_identification_v5_generator_unified",
        "source_model": "single_event_dcm_sw_v2_signed_spikes",
        "basic": {"algorithm": "ignored-analysis-data"},
        "current_generator_parameters": asdict(expected),
    }

    loaded = parameters_from_dict(raw)
    assert asdict(loaded) == asdict(expected)

    waveform = generate_dcm_sw_waveform(loaded)
    assert waveform.time_s[0] == pytest.approx(5e-6, abs=1e-18)
    assert waveform.time_s[-1] == pytest.approx(17e-6, abs=1e-12)


def test_generator_uses_current_fit_parameters_as_fallback():
    expected = DcmSwParameters(random_seed=7)
    raw = {
        "algorithm": "dcm_parameter_identification_v5_generator_unified",
        "current_generator_fit": {
            "algorithm": "dcm_generator_unified_fit_v1",
            "parameters": asdict(expected),
        },
    }
    loaded = parameters_from_dict(raw)
    assert asdict(loaded) == asdict(expected)


def test_old_generator_json_without_time_origin_keeps_zero_origin():
    old_parameters = asdict(DcmSwParameters())
    old_parameters.pop("time_origin_s")
    loaded = parameters_from_dict(
        {
            "schema_version": 1,
            "model": "single_event_dcm_sw_v2_signed_spikes",
            "parameters": old_parameters,
        }
    )
    assert loaded.time_origin_s == 0.0


def test_parameter_extractor_preserves_absolute_time_axis_and_saves_csv(qapp, tmp_path):
    del qapp
    source_parameters = DcmSwParameters(
        time_origin_s=5e-6,
        total_duration_s=12e-6,
        switching_start_s=7e-6,
        noise_rms_v=0.01,
    )
    waveform = generate_dcm_sw_waveform(source_parameters)
    widget = DcmParameterExtractorWidget()
    widget.set_waveform(
        waveform.time_s,
        waveform.voltage_v,
        source_name="synthetic-export-5-to-17us",
    )

    assert widget.current_fit_result is not None
    assert widget.current_parameters is not None
    assert widget.current_parameters.time_origin_s == pytest.approx(5e-6, abs=1e-18)
    assert widget.current_parameters.total_duration_s == pytest.approx(12e-6, abs=1e-12)
    assert widget.save_reconstruction_csv_btn.isEnabled()

    # 参数表必须明确显示原始绝对时间范围。
    names = [
        widget.result_table.item(row, 0).text()
        for row in range(widget.result_table.rowCount())
        if widget.result_table.item(row, 0) is not None
    ]
    assert "【输入】时间轴起点" in names
    assert "【输入】时间轴终点" in names

    output = widget.save_current_csv(tmp_path / "reconstructed")
    assert output.suffix == ".csv"
    frame = pd.read_csv(output)
    assert list(frame.columns) == [
        "time_s",
        "voltage_v",
        "source_voltage_v",
        "residual_v",
        "ideal_voltage_v",
        "spike_component_v",
        "discontinuous_component_v",
    ]
    saved_time = frame["time_s"].to_numpy()
    assert saved_time[0] == pytest.approx(5e-6, abs=1e-18)
    assert saved_time[-1] == pytest.approx(17e-6, abs=1e-12)
    assert np.allclose(saved_time, waveform.time_s)
    assert np.allclose(
        frame["voltage_v"].to_numpy(),
        widget.current_fit_result.reconstruction_v,
    )
    assert np.allclose(
        frame["source_voltage_v"].to_numpy(),
        waveform.voltage_v,
    )
    assert np.allclose(
        frame["residual_v"].to_numpy(),
        waveform.voltage_v - widget.current_fit_result.reconstruction_v,
    )
