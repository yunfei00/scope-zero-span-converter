from __future__ import annotations

import numpy as np
import pytest

from scope_zero_span_converter.dcm_discontinuous_extractor import (
    extract_dcm_discontinuous_resonance,
)
from scope_zero_span_converter.dcm_parameter_extractor import extract_dcm_basic_parameters
from scope_zero_span_converter.dcm_ringing_extractor import extract_dcm_edge_ringing
from scope_zero_span_converter.dcm_sw_generator import DcmSwParameters, generate_dcm_sw_waveform


def _extract(parameters: DcmSwParameters):
    waveform = generate_dcm_sw_waveform(parameters)
    basic = extract_dcm_basic_parameters(waveform.time_s, waveform.voltage_v)
    ringing = extract_dcm_edge_ringing(waveform.time_s, waveform.voltage_v, basic)
    dcm = extract_dcm_discontinuous_resonance(
        waveform.time_s,
        waveform.voltage_v,
        basic,
        ringing,
    )
    return waveform, basic, ringing, dcm


def test_extracts_default_dcm_resonance_from_staged_residual():
    parameters = DcmSwParameters()
    waveform, basic, ringing, result = _extract(parameters)

    assert result.signed_initial_amplitude_v == pytest.approx(
        parameters.discontinuous_initial_amplitude_v, abs=0.15
    )
    assert result.resonance_frequency_hz == pytest.approx(
        parameters.discontinuous_resonance_frequency_hz, abs=0.25e6
    )
    assert result.decay_rate_per_s == pytest.approx(
        parameters.discontinuous_decay_rate_per_s, abs=0.15e6
    )
    assert result.r_squared > 0.95
    assert result.confidence > 0.75
    assert result.final_noise_rms_v == pytest.approx(parameters.noise_rms_v, abs=0.006)
    assert len(result.fitted_discontinuous_component_v) == waveform.points
    assert len(result.final_residual_v) == waveform.points
    assert np.all(np.isfinite(result.final_residual_v))

    # 第三阶段之后的残差应显著小于尚含 DCM 谐振的第二阶段残差。
    before = np.sqrt(np.mean(ringing.residual_after_spike_v**2))
    after = np.sqrt(np.mean(result.final_residual_v**2))
    assert after < before * 0.45


def test_extracts_varied_dcm_frequency_decay_and_amplitude():
    parameters = DcmSwParameters(
        total_duration_s=24e-6,
        switching_start_s=2.5e-6,
        rise_time_s=80e-9,
        on_time_s=3.8e-6,
        fall_time_s=70e-9,
        freewheel_time_s=2.8e-6,
        rise_spike_amplitude_v=2.2,
        fall_spike_amplitude_v=-3.2,
        spike_ringing_frequency_hz=72e6,
        spike_decay_rate_per_s=9.5e6,
        discontinuous_initial_amplitude_v=1.7,
        discontinuous_resonance_frequency_hz=7.5e6,
        discontinuous_decay_rate_per_s=1.4e6,
        noise_rms_v=0.015,
        sample_rate_hz=2e9,
        random_seed=20260904,
    )
    _, _, _, result = _extract(parameters)

    assert result.signed_initial_amplitude_v == pytest.approx(
        parameters.discontinuous_initial_amplitude_v, abs=0.16
    )
    assert result.resonance_frequency_hz == pytest.approx(
        parameters.discontinuous_resonance_frequency_hz, abs=0.35e6
    )
    assert result.decay_rate_per_s == pytest.approx(
        parameters.discontinuous_decay_rate_per_s, abs=0.25e6
    )
    assert result.final_noise_rms_v == pytest.approx(parameters.noise_rms_v, abs=0.005)
    assert result.r_squared > 0.90


def test_zero_dcm_resonance_does_not_create_large_false_component():
    parameters = DcmSwParameters(
        discontinuous_initial_amplitude_v=0.0,
        discontinuous_resonance_frequency_hz=5e6,
        discontinuous_decay_rate_per_s=0.8e6,
        noise_rms_v=0.01,
        random_seed=77,
    )
    _, _, _, result = _extract(parameters)

    assert abs(result.signed_initial_amplitude_v) < 0.08
    assert result.final_noise_rms_v == pytest.approx(parameters.noise_rms_v, abs=0.004)
    assert any("接近底噪" in item or "置信度偏低" in item for item in result.warnings)
