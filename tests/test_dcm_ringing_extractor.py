from __future__ import annotations

import numpy as np
import pytest

from scope_zero_span_converter.dcm_parameter_extractor import extract_dcm_basic_parameters
from scope_zero_span_converter.dcm_ringing_extractor import extract_dcm_edge_ringing
from scope_zero_span_converter.dcm_sw_generator import DcmSwParameters, generate_dcm_sw_waveform


def _extract(parameters: DcmSwParameters):
    waveform = generate_dcm_sw_waveform(parameters)
    basic = extract_dcm_basic_parameters(waveform.time_s, waveform.voltage_v)
    ringing = extract_dcm_edge_ringing(waveform.time_s, waveform.voltage_v, basic)
    return waveform, basic, ringing


def test_extracts_default_shared_ringing_truth():
    parameters = DcmSwParameters()
    waveform, basic, result = _extract(parameters)

    assert result.ringing_frequency_hz == pytest.approx(
        parameters.spike_ringing_frequency_hz, rel=0.06
    )
    assert result.decay_rate_per_s == pytest.approx(
        parameters.spike_decay_rate_per_s, rel=0.20
    )
    assert result.rise.signed_initial_amplitude_v == pytest.approx(
        parameters.rise_spike_amplitude_v, abs=0.45
    )
    assert result.fall.signed_initial_amplitude_v == pytest.approx(
        parameters.fall_spike_amplitude_v, abs=0.55
    )
    assert result.rise.r_squared > 0.75
    assert result.fall.r_squared > 0.75
    assert result.overall_confidence > 0.65
    assert len(result.fitted_spike_component_v) == waveform.points
    assert np.all(np.isfinite(result.residual_after_spike_v))

    before = float(np.sqrt(np.mean(basic.residual_v**2)))
    after = float(np.sqrt(np.mean(result.residual_after_spike_v**2)))
    assert after < before


def test_extracts_varied_ringing_truth():
    parameters = DcmSwParameters(
        baseline_voltage_v=-0.2,
        on_high_voltage_v=18.0,
        freewheel_low_voltage_v=0.6,
        switching_start_s=2.2e-6,
        rise_time_s=70e-9,
        on_time_s=3.8e-6,
        fall_time_s=90e-9,
        freewheel_time_s=3.1e-6,
        rise_spike_amplitude_v=1.8,
        fall_spike_amplitude_v=-2.9,
        spike_ringing_frequency_hz=85e6,
        spike_decay_rate_per_s=12e6,
        discontinuous_initial_amplitude_v=1.4,
        discontinuous_resonance_frequency_hz=4.2e6,
        discontinuous_decay_rate_per_s=0.65e6,
        noise_rms_v=0.03,
        sample_rate_hz=2e9,
        random_seed=20260904,
        total_duration_s=22e-6,
    )
    _, _, result = _extract(parameters)

    assert result.ringing_frequency_hz == pytest.approx(
        parameters.spike_ringing_frequency_hz, rel=0.08
    )
    assert result.decay_rate_per_s == pytest.approx(
        parameters.spike_decay_rate_per_s, rel=0.25
    )
    assert result.rise.signed_initial_amplitude_v == pytest.approx(
        parameters.rise_spike_amplitude_v, abs=0.40
    )
    assert result.fall.signed_initial_amplitude_v == pytest.approx(
        parameters.fall_spike_amplitude_v, abs=0.45
    )


def test_zero_spike_case_does_not_create_large_false_amplitude():
    parameters = DcmSwParameters(
        rise_time_s=0.0,
        fall_time_s=0.0,
        rise_spike_amplitude_v=0.0,
        fall_spike_amplitude_v=0.0,
        discontinuous_initial_amplitude_v=0.0,
        noise_rms_v=0.0,
    )
    _, _, result = _extract(parameters)

    assert abs(result.rise.signed_initial_amplitude_v) < 1e-9
    assert abs(result.fall.signed_initial_amplitude_v) < 1e-9
    assert np.max(np.abs(result.fitted_spike_component_v)) < 1e-9
    assert result.overall_confidence < 0.5
