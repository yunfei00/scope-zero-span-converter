from __future__ import annotations

import numpy as np

from scope_zero_span_converter.dcm_sw_generator import DcmSwParameters, generate_dcm_sw_waveform
from scope_zero_span_converter.dcm_zero_span_link import (
    ZeroSpanProfile,
    convert_dcm_waveform_to_zero_span,
    load_zero_span_profile,
    save_zero_span_profile,
)


def test_zero_span_link_preserves_absolute_time_axis():
    parameters = DcmSwParameters(
        time_origin_s=5e-6,
        total_duration_s=12e-6,
        switching_start_s=7e-6,
        on_time_s=2.5e-6,
        freewheel_time_s=2.0e-6,
        sample_rate_hz=2e9,
        noise_rms_v=0.0,
    )
    waveform = generate_dcm_sw_waveform(parameters)
    result = convert_dcm_waveform_to_zero_span(waveform, ZeroSpanProfile())

    assert np.isclose(waveform.time_s[0], 5e-6)
    assert np.isclose(waveform.time_s[-1], 17e-6)
    assert np.allclose(result.time_s, waveform.time_s)
    assert np.isclose(result.time_s[0], 5e-6)
    assert np.isclose(result.time_s[-1], 17e-6)
    assert len(result.amplitude_dbm) == len(waveform.time_s)


def test_zero_span_profile_roundtrip(tmp_path):
    expected = ZeroSpanProfile(
        center_frequency_hz=180e6,
        rbw_hz=8e6,
        vbw_hz=3e6,
        vbw_enabled=False,
        impedance_ohm=75.0,
        calibration_db=-1.25,
        scope_analog_bandwidth_hz=350e6,
    )
    path = save_zero_span_profile(expected, tmp_path / "profile")
    loaded = load_zero_span_profile(path)
    assert loaded == expected


def test_dcm_parameter_change_changes_scope_and_zero_span():
    profile = ZeroSpanProfile(center_frequency_hz=200e6, rbw_hz=10e6, vbw_hz=10e6)
    p1 = DcmSwParameters(noise_rms_v=0.0)
    p2 = DcmSwParameters(on_high_voltage_v=15.0, noise_rms_v=0.0)

    w1 = generate_dcm_sw_waveform(p1)
    z1 = convert_dcm_waveform_to_zero_span(w1, profile)
    w2 = generate_dcm_sw_waveform(p2)
    z2 = convert_dcm_waveform_to_zero_span(w2, profile)

    assert not np.allclose(w1.voltage_v, w2.voltage_v)
    assert not np.allclose(z1.amplitude_dbm, z2.amplitude_dbm)
