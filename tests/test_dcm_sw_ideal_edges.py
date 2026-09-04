import numpy as np
import pytest

from scope_zero_span_converter.dcm_sw_generator import (
    DcmSwParameters,
    event_times,
    generate_dcm_sw_waveform,
)


def _index_at_or_after(time_s: np.ndarray, value_s: float) -> int:
    return int(np.searchsorted(time_s, value_s, side="left"))


def test_zero_rise_time_is_ideal_step():
    p = DcmSwParameters(
        rise_time_s=0.0,
        fall_time_s=50e-9,
        noise_rms_v=0.0,
        rise_spike_amplitude_v=0.0,
        fall_spike_amplitude_v=0.0,
        discontinuous_initial_amplitude_v=0.0,
    )
    w = generate_dcm_sw_waveform(p)
    e = event_times(p)

    assert e.rise_end_s == pytest.approx(e.rise_start_s)
    i = _index_at_or_after(w.time_s, e.rise_start_s)
    assert i > 0
    assert w.ideal_voltage_v[i - 1] == pytest.approx(p.baseline_voltage_v)
    assert w.ideal_voltage_v[i] == pytest.approx(p.on_high_voltage_v)


def test_zero_fall_time_is_ideal_step():
    p = DcmSwParameters(
        rise_time_s=40e-9,
        fall_time_s=0.0,
        noise_rms_v=0.0,
        rise_spike_amplitude_v=0.0,
        fall_spike_amplitude_v=0.0,
        discontinuous_initial_amplitude_v=0.0,
    )
    w = generate_dcm_sw_waveform(p)
    e = event_times(p)

    assert e.fall_end_s == pytest.approx(e.high_end_s)
    i = _index_at_or_after(w.time_s, e.high_end_s)
    assert i > 0
    assert w.ideal_voltage_v[i - 1] == pytest.approx(p.on_high_voltage_v)
    assert w.ideal_voltage_v[i] == pytest.approx(p.freewheel_low_voltage_v)


def test_both_edges_can_be_zero():
    p = DcmSwParameters(
        rise_time_s=0.0,
        fall_time_s=0.0,
        noise_rms_v=0.0,
        rise_spike_amplitude_v=0.0,
        fall_spike_amplitude_v=0.0,
        discontinuous_initial_amplitude_v=0.0,
    )
    w = generate_dcm_sw_waveform(p)
    e = event_times(p)

    assert e.rise_start_s == pytest.approx(e.rise_end_s)
    assert e.high_end_s == pytest.approx(e.fall_end_s)
    assert np.all(np.isfinite(w.voltage_v))
