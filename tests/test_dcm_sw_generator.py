import json

import numpy as np
import pandas as pd
import pytest

from scope_zero_span_converter.converter import load_waveform
from scope_zero_span_converter.dcm_sw_generator import (
    DcmSwParameters,
    event_times,
    generate_dcm_sw_waveform,
    load_dcm_sw_parameters,
    save_dcm_sw_parameters,
    save_dcm_sw_waveform,
)


def _nearest_index(time_s: np.ndarray, value_s: float) -> int:
    return int(np.argmin(np.abs(time_s - value_s)))


def test_default_dcm_sw_phase_truths():
    p = DcmSwParameters(noise_rms_v=0.0)
    w = generate_dcm_sw_waveform(p)
    e = event_times(p)

    assert w.points == int(np.floor(p.total_duration_s * p.sample_rate_hz)) + 1
    assert w.time_s[0] == pytest.approx(0.0)
    assert w.time_s[-1] <= p.total_duration_s

    before = _nearest_index(w.time_s, p.switching_start_s / 2.0)
    assert w.ideal_voltage_v[before] == pytest.approx(p.baseline_voltage_v)

    high_mid_s = e.rise_end_s + p.on_time_s / 2.0
    high_mid = _nearest_index(w.time_s, high_mid_s)
    assert w.ideal_voltage_v[high_mid] == pytest.approx(p.on_high_voltage_v)

    freewheel_mid_s = e.fall_end_s + p.freewheel_time_s / 2.0
    freewheel_mid = _nearest_index(w.time_s, freewheel_mid_s)
    assert w.ideal_voltage_v[freewheel_mid] == pytest.approx(p.freewheel_low_voltage_v)

    after_freewheel = _nearest_index(w.time_s, e.freewheel_end_s + 0.5e-6)
    assert w.ideal_voltage_v[after_freewheel] == pytest.approx(p.baseline_voltage_v)

    rise_spike_index = _nearest_index(w.time_s, e.rise_end_s)
    assert w.spike_component_v[rise_spike_index] > 0.9 * p.rise_spike_amplitude_v

    dcm_index = _nearest_index(w.time_s, e.freewheel_end_s)
    assert w.discontinuous_component_v[dcm_index] == pytest.approx(
        p.discontinuous_initial_amplitude_v,
        abs=0.02,
    )


def test_dcm_sw_noise_is_reproducible_with_seed():
    p1 = DcmSwParameters(random_seed=2468)
    p2 = DcmSwParameters(random_seed=2468)
    p3 = DcmSwParameters(random_seed=2469)

    w1 = generate_dcm_sw_waveform(p1)
    w2 = generate_dcm_sw_waveform(p2)
    w3 = generate_dcm_sw_waveform(p3)

    assert np.array_equal(w1.voltage_v, w2.voltage_v)
    assert not np.array_equal(w1.voltage_v, w3.voltage_v)
    assert np.std(w1.noise_component_v) == pytest.approx(p1.noise_rms_v, rel=0.08)


def test_dcm_sw_parameter_json_round_trip(tmp_path):
    p = DcmSwParameters(
        baseline_voltage_v=1.25,
        on_high_voltage_v=27.0,
        discontinuous_resonance_frequency_hz=7.5e6,
        random_seed=9876,
    )
    path = tmp_path / "dcm.json"
    save_dcm_sw_parameters(p, path)
    loaded = load_dcm_sw_parameters(path)

    assert loaded.baseline_voltage_v == pytest.approx(1.25)
    assert loaded.on_high_voltage_v == pytest.approx(27.0)
    assert loaded.discontinuous_resonance_frequency_hz == pytest.approx(7.5e6)
    assert loaded.random_seed == 9876


def test_dcm_sw_waveform_save_contains_truth_components(tmp_path):
    p = DcmSwParameters(noise_rms_v=0.0)
    w = generate_dcm_sw_waveform(p)
    csv_path, parameters_path = save_dcm_sw_waveform(
        w,
        tmp_path / "synthetic_dcm_sw.csv",
    )

    assert csv_path.exists()
    assert parameters_path is not None and parameters_path.exists()

    df = pd.read_csv(csv_path)
    assert list(df.columns) == [
        "time_s",
        "voltage_v",
        "ideal_voltage_v",
        "spike_component_v",
        "discontinuous_component_v",
        "noise_component_v",
    ]
    assert len(df) == w.points

    # 与项目既有 waveform.csv 读取协议兼容，额外真值列不会影响研究页面。
    t, v, fs = load_waveform(csv_path)
    assert len(t) == w.points
    assert len(v) == w.points
    assert fs == pytest.approx(p.sample_rate_hz, rel=1e-9)

    metadata = json.loads(parameters_path.read_text(encoding="utf-8"))
    assert metadata["model"] == "single_event_dcm_sw_v1"
    assert metadata["derived_events"]["freewheel_end_s"] == pytest.approx(
        w.events.freewheel_end_s
    )


def test_dcm_sw_rejects_display_window_shorter_than_event():
    p = DcmSwParameters(total_duration_s=5e-6)
    with pytest.raises(ValueError, match="总显示时长不足"):
        generate_dcm_sw_waveform(p)


def test_dcm_sw_rejects_aliasing_sampling_rate():
    p = DcmSwParameters(
        sample_rate_hz=100e6,
        spike_ringing_frequency_hz=60e6,
    )
    with pytest.raises(ValueError, match="采样率不足"):
        generate_dcm_sw_waveform(p)
