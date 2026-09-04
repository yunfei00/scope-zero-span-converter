from __future__ import annotations

import numpy as np
import pytest

from scope_zero_span_converter.dcm_discontinuous_extractor import (
    extract_dcm_discontinuous_resonance,
)
from scope_zero_span_converter.dcm_global_refiner import refine_dcm_parameters_globally
from scope_zero_span_converter.dcm_parameter_extractor import extract_dcm_basic_parameters
from scope_zero_span_converter.dcm_ringing_extractor import extract_dcm_edge_ringing
from scope_zero_span_converter.dcm_sw_generator import DcmSwParameters, generate_dcm_sw_waveform


def _run_full_identification(parameters: DcmSwParameters):
    waveform = generate_dcm_sw_waveform(parameters)
    basic = extract_dcm_basic_parameters(waveform.time_s, waveform.voltage_v)
    ringing = extract_dcm_edge_ringing(waveform.time_s, waveform.voltage_v, basic)
    dcm = extract_dcm_discontinuous_resonance(
        waveform.time_s,
        waveform.voltage_v,
        basic,
        ringing,
    )
    refined = refine_dcm_parameters_globally(
        waveform.time_s,
        waveform.voltage_v,
        basic,
        ringing,
        dcm,
        max_iterations=7,
        max_optimization_points=12_000,
    )
    return waveform, basic, ringing, dcm, refined


def test_global_refinement_reconstructs_default_like_waveform():
    parameters = DcmSwParameters(
        sample_rate_hz=800e6,
        noise_rms_v=0.02,
        random_seed=20260904,
    )
    waveform, _, _, _, refined = _run_full_identification(parameters)

    assert len(refined.optimized_reconstruction_v) == waveform.points
    assert len(refined.final_residual_v) == waveform.points
    assert np.all(np.isfinite(refined.optimized_reconstruction_v))
    assert np.all(np.isfinite(refined.final_residual_v))
    assert refined.optimized_rmse_v <= refined.staged_rmse_v * 1.05
    assert refined.full_r_squared > 0.995

    assert refined.baseline_voltage_v == pytest.approx(parameters.baseline_voltage_v, abs=0.05)
    assert refined.on_high_voltage_v == pytest.approx(parameters.on_high_voltage_v, abs=0.08)
    assert refined.freewheel_low_voltage_v == pytest.approx(parameters.freewheel_low_voltage_v, abs=0.08)

    assert refined.switching_start_s == pytest.approx(parameters.switching_start_s, abs=12e-9)
    assert refined.rise_time_s == pytest.approx(parameters.rise_time_s, abs=12e-9)
    assert refined.on_time_s == pytest.approx(parameters.on_time_s, abs=25e-9)
    assert refined.fall_time_s == pytest.approx(parameters.fall_time_s, abs=12e-9)
    assert refined.freewheel_time_s == pytest.approx(parameters.freewheel_time_s, abs=60e-9)

    assert refined.rise_spike_amplitude_v == pytest.approx(
        parameters.rise_spike_amplitude_v, abs=0.35
    )
    assert refined.fall_spike_amplitude_v == pytest.approx(
        parameters.fall_spike_amplitude_v, abs=0.40
    )
    assert refined.ringing_frequency_hz == pytest.approx(
        parameters.spike_ringing_frequency_hz, rel=0.06
    )
    assert refined.ringing_decay_rate_per_s == pytest.approx(
        parameters.spike_decay_rate_per_s, rel=0.30
    )

    assert refined.dcm_initial_amplitude_v == pytest.approx(
        parameters.discontinuous_initial_amplitude_v, abs=0.25
    )
    assert refined.dcm_frequency_hz == pytest.approx(
        parameters.discontinuous_resonance_frequency_hz, rel=0.06
    )
    assert refined.dcm_decay_rate_per_s == pytest.approx(
        parameters.discontinuous_decay_rate_per_s, rel=0.30
    )
    assert refined.final_noise_rms_v == pytest.approx(parameters.noise_rms_v, abs=0.012)


def test_global_refinement_handles_varied_known_truth_without_truth_columns():
    parameters = DcmSwParameters(
        baseline_voltage_v=-0.15,
        on_high_voltage_v=18.0,
        freewheel_low_voltage_v=0.7,
        total_duration_s=24e-6,
        switching_start_s=2.8e-6,
        rise_time_s=70e-9,
        on_time_s=4.0e-6,
        fall_time_s=85e-9,
        freewheel_time_s=3.2e-6,
        rise_spike_amplitude_v=2.2,
        fall_spike_amplitude_v=-3.1,
        spike_ringing_frequency_hz=82e6,
        spike_decay_rate_per_s=11e6,
        discontinuous_initial_amplitude_v=1.6,
        discontinuous_resonance_frequency_hz=7.0e6,
        discontinuous_decay_rate_per_s=1.2e6,
        noise_rms_v=0.018,
        sample_rate_hz=800e6,
        random_seed=88,
    )
    _, _, _, _, refined = _run_full_identification(parameters)

    assert refined.full_r_squared > 0.995
    assert refined.on_high_voltage_v == pytest.approx(parameters.on_high_voltage_v, abs=0.10)
    assert refined.switching_start_s == pytest.approx(parameters.switching_start_s, abs=15e-9)
    assert refined.on_time_s == pytest.approx(parameters.on_time_s, abs=35e-9)
    assert refined.ringing_frequency_hz == pytest.approx(
        parameters.spike_ringing_frequency_hz, rel=0.08
    )
    assert refined.dcm_frequency_hz == pytest.approx(
        parameters.discontinuous_resonance_frequency_hz, rel=0.08
    )
    assert refined.optimized_rmse_v < 0.12


def test_global_refinement_dict_excludes_waveform_arrays():
    parameters = DcmSwParameters(
        sample_rate_hz=600e6,
        noise_rms_v=0.01,
        random_seed=9,
    )
    _, _, _, _, refined = _run_full_identification(parameters)
    payload = refined.to_dict()

    assert payload["algorithm"] == "dcm_global_joint_refiner_v1"
    assert "optimized_parameters" in payload
    assert "fit_quality" in payload
    assert "optimization" in payload
    assert "optimized_reconstruction_v" not in payload
    assert "final_residual_v" not in payload
