from __future__ import annotations

from dataclasses import replace

import numpy as np

from scope_zero_span_converter.dcm_sw_generator import (
    DcmSwParameters,
    evaluate_dcm_sw_deterministic_components,
    generate_dcm_sw_waveform,
)


def test_generator_uses_same_deterministic_model_components():
    params = DcmSwParameters(noise_rms_v=0.0)
    waveform = generate_dcm_sw_waveform(params)
    components = evaluate_dcm_sw_deterministic_components(waveform.time_s, params)

    assert np.allclose(waveform.ideal_voltage_v, components.ideal_voltage_v)
    assert np.allclose(waveform.spike_component_v, components.spike_component_v)
    assert np.allclose(waveform.discontinuous_component_v, components.discontinuous_component_v)
    assert np.allclose(waveform.voltage_v, components.deterministic_voltage_v)


def test_every_customer_core_parameter_changes_deterministic_waveform():
    base = DcmSwParameters(noise_rms_v=0.0)
    waveform = generate_dcm_sw_waveform(base)
    t = waveform.time_s
    reference = evaluate_dcm_sw_deterministic_components(t, base).deterministic_voltage_v

    variants = {
        "baseline_voltage_v": base.baseline_voltage_v + 0.35,
        "on_high_voltage_v": base.on_high_voltage_v + 0.8,
        "freewheel_low_voltage_v": base.freewheel_low_voltage_v + 0.4,
        "switching_start_s": base.switching_start_s + 0.20e-6,
        "rise_time_s": base.rise_time_s + 20e-9,
        "on_time_s": base.on_time_s + 0.25e-6,
        "fall_time_s": base.fall_time_s + 25e-9,
        "freewheel_time_s": base.freewheel_time_s + 0.30e-6,
        "rise_spike_amplitude_v": base.rise_spike_amplitude_v + 0.7,
        "fall_spike_amplitude_v": base.fall_spike_amplitude_v - 0.7,
        "spike_ringing_frequency_hz": base.spike_ringing_frequency_hz + 12e6,
        "spike_decay_rate_per_s": base.spike_decay_rate_per_s + 2e6,
        "discontinuous_initial_amplitude_v": base.discontinuous_initial_amplitude_v + 0.6,
        "discontinuous_resonance_frequency_hz": base.discontinuous_resonance_frequency_hz + 1.2e6,
        "discontinuous_decay_rate_per_s": base.discontinuous_decay_rate_per_s + 0.4e6,
    }

    for key, value in variants.items():
        changed = replace(base, **{key: value})
        candidate = evaluate_dcm_sw_deterministic_components(t, changed).deterministic_voltage_v
        max_delta = float(np.max(np.abs(candidate - reference)))
        assert max_delta > 1e-6, f"{key} 修改后没有影响确定性波形"


def test_spike_frequency_has_no_effect_only_when_both_spike_amplitudes_are_zero():
    base = DcmSwParameters(
        rise_spike_amplitude_v=0.0,
        fall_spike_amplitude_v=0.0,
        noise_rms_v=0.0,
    )
    waveform = generate_dcm_sw_waveform(base)
    t = waveform.time_s

    a = evaluate_dcm_sw_deterministic_components(t, base).deterministic_voltage_v
    b = evaluate_dcm_sw_deterministic_components(
        t,
        replace(base, spike_ringing_frequency_hz=base.spike_ringing_frequency_hz + 30e6),
    ).deterministic_voltage_v
    assert np.allclose(a, b)

    active = replace(base, rise_spike_amplitude_v=1.0)
    c = evaluate_dcm_sw_deterministic_components(t, active).deterministic_voltage_v
    d = evaluate_dcm_sw_deterministic_components(
        t,
        replace(active, spike_ringing_frequency_hz=active.spike_ringing_frequency_hz + 30e6),
    ).deterministic_voltage_v
    assert not np.allclose(c, d)
