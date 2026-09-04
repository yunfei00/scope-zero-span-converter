from __future__ import annotations

from scope_zero_span_converter.dcm_discontinuous_extractor import extract_dcm_discontinuous_resonance
from scope_zero_span_converter.dcm_manual_tuner import tune_dcm_on_time_manually
from scope_zero_span_converter.dcm_parameter_extractor import extract_dcm_basic_parameters
from scope_zero_span_converter.dcm_ringing_extractor import extract_dcm_edge_ringing
from scope_zero_span_converter.dcm_sw_generator import DcmSwParameters, generate_dcm_sw_waveform


def _staged(waveform):
    basic = extract_dcm_basic_parameters(waveform.time_s, waveform.voltage_v)
    ringing = extract_dcm_edge_ringing(waveform.time_s, waveform.voltage_v, basic)
    dcm = extract_dcm_discontinuous_resonance(
        waveform.time_s,
        waveform.voltage_v,
        basic,
        ringing,
    )
    return basic, ringing, dcm


def test_manual_on_time_tuning_prefers_value_near_truth():
    params = DcmSwParameters(noise_rms_v=0.01)
    waveform = generate_dcm_sw_waveform(params)
    basic, ringing, dcm = _staged(waveform)

    near_truth = tune_dcm_on_time_manually(
        waveform.time_s,
        waveform.voltage_v,
        basic,
        ringing,
        dcm,
        on_time_s=params.on_time_s,
    )
    wrong = tune_dcm_on_time_manually(
        waveform.time_s,
        waveform.voltage_v,
        basic,
        ringing,
        dcm,
        on_time_s=params.on_time_s + 0.55e-6,
    )

    assert near_truth.matching_score > wrong.matching_score
    assert near_truth.local_rmse_v < wrong.local_rmse_v
    assert near_truth.full_rmse_v < wrong.full_rmse_v
    assert abs(near_truth.fall_start_s - wrong.fall_start_s) > 0.5e-6


def test_manual_on_time_tuning_returns_full_length_reconstruction():
    waveform = generate_dcm_sw_waveform(DcmSwParameters())
    basic, ringing, dcm = _staged(waveform)
    tuned = tune_dcm_on_time_manually(
        waveform.time_s,
        waveform.voltage_v,
        basic,
        ringing,
        dcm,
        on_time_s=basic.on_time_s,
    )

    assert len(tuned.reconstruction_v) == len(waveform.time_s)
    assert len(tuned.residual_v) == len(waveform.time_s)
    assert 0.0 <= tuned.matching_score <= 1.0
    assert -1.0 <= tuned.full_r_squared <= 1.0


def test_manual_on_time_tuning_works_with_basic_result_only():
    """真实 CSV 后续振铃/DCM 拟合失败时，导通时间人工校正仍必须可用。"""

    params = DcmSwParameters(noise_rms_v=0.01)
    waveform = generate_dcm_sw_waveform(params)
    basic = extract_dcm_basic_parameters(waveform.time_s, waveform.voltage_v)

    near_truth = tune_dcm_on_time_manually(
        waveform.time_s,
        waveform.voltage_v,
        basic,
        None,
        None,
        on_time_s=params.on_time_s,
    )
    wrong = tune_dcm_on_time_manually(
        waveform.time_s,
        waveform.voltage_v,
        basic,
        None,
        None,
        on_time_s=params.on_time_s + 0.55e-6,
    )

    assert near_truth.source == "basic_fallback"
    assert near_truth.matching_score > wrong.matching_score
    assert near_truth.local_rmse_v < wrong.local_rmse_v
    assert len(near_truth.reconstruction_v) == len(waveform.time_s)
