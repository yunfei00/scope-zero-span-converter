from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import asdict

import numpy as np
import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_parameter_extractor_widget_v6 import (
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
        switching_start_s=1.8e-6,
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


def test_parameter_extractor_saves_current_reconstruction_csv(qapp, tmp_path):
    del qapp
    waveform = generate_dcm_sw_waveform(DcmSwParameters(noise_rms_v=0.01))
    widget = DcmParameterExtractorWidget()
    widget.set_waveform(
        waveform.time_s,
        waveform.voltage_v,
        source_name="synthetic-export",
    )

    assert widget.current_fit_result is not None
    assert widget.save_reconstruction_csv_btn.isEnabled()

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
    assert np.allclose(frame["time_s"].to_numpy(), waveform.time_s)
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
