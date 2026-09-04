from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from .dcm_discontinuous_extractor import DcmDiscontinuousExtractionResult
from .dcm_global_refiner import DcmGlobalRefinementResult
from .dcm_parameter_extractor import DcmBasicExtractionResult
from .dcm_ringing_extractor import DcmRingingExtractionResult
from .dcm_sw_generator import (
    DcmSwParameters,
    evaluate_dcm_sw_deterministic_components,
    event_times,
)


@dataclass(frozen=True)
class DcmUnifiedFitResult:
    """使用 DCM SW 生成器同一套参数和正向模型得到的当前拟合结果。"""

    parameters: DcmSwParameters
    full_rmse_v: float
    full_r_squared: float
    final_noise_rms_v: float
    overall_matching_score: float
    region_scores: dict[str, float]
    reconstruction_v: np.ndarray
    residual_v: np.ndarray

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": "dcm_generator_unified_fit_v1",
            "parameters": asdict(self.parameters),
            "fit_quality": {
                "full_rmse_v": self.full_rmse_v,
                "full_r_squared": self.full_r_squared,
                "final_noise_rms_v": self.final_noise_rms_v,
                "overall_matching_score": self.overall_matching_score,
                "region_scores": dict(self.region_scores),
            },
        }


def parameters_from_extraction(
    basic: DcmBasicExtractionResult,
    ringing: DcmRingingExtractionResult | None,
    dcm: DcmDiscontinuousExtractionResult | None,
    global_result: DcmGlobalRefinementResult | None = None,
) -> DcmSwParameters:
    """把自动提取结果映射成生成器原生 DcmSwParameters。

    phase 是反演内部的辅助量，不属于当前生成器模型，因此不会进入最终主参数。
    noise_rms_v 记录自动估计值，但人工确定性重建不会重新注入随机噪声。
    """

    if global_result is not None:
        return DcmSwParameters(
            baseline_voltage_v=global_result.baseline_voltage_v,
            on_high_voltage_v=global_result.on_high_voltage_v,
            freewheel_low_voltage_v=global_result.freewheel_low_voltage_v,
            total_duration_s=basic.total_duration_s,
            switching_start_s=global_result.switching_start_s,
            on_time_s=global_result.on_time_s,
            freewheel_time_s=global_result.freewheel_time_s,
            rise_time_s=global_result.rise_time_s,
            fall_time_s=global_result.fall_time_s,
            rise_spike_amplitude_v=global_result.rise_spike_amplitude_v,
            fall_spike_amplitude_v=global_result.fall_spike_amplitude_v,
            spike_ringing_frequency_hz=global_result.ringing_frequency_hz,
            spike_decay_rate_per_s=global_result.ringing_decay_rate_per_s,
            discontinuous_initial_amplitude_v=global_result.dcm_initial_amplitude_v,
            discontinuous_resonance_frequency_hz=global_result.dcm_frequency_hz,
            discontinuous_decay_rate_per_s=global_result.dcm_decay_rate_per_s,
            noise_rms_v=global_result.final_noise_rms_v,
            sample_rate_hz=basic.sample_rate_hz,
            random_seed=0,
        )

    if ringing is None:
        rise_amp = 0.0
        fall_amp = 0.0
        ring_f = 0.0
        ring_alpha = 0.0
    else:
        rise_amp = ringing.rise.signed_initial_amplitude_v
        fall_amp = ringing.fall.signed_initial_amplitude_v
        ring_f = ringing.ringing_frequency_hz
        ring_alpha = ringing.decay_rate_per_s

    if dcm is None:
        dcm_amp = 0.0
        dcm_f = 0.0
        dcm_alpha = 0.0
        noise_rms = basic.estimated_noise_rms_v
    else:
        dcm_amp = dcm.signed_initial_amplitude_v
        dcm_f = dcm.resonance_frequency_hz
        dcm_alpha = dcm.decay_rate_per_s
        noise_rms = dcm.final_noise_rms_v

    return DcmSwParameters(
        baseline_voltage_v=basic.baseline_voltage_v,
        on_high_voltage_v=basic.on_high_voltage_v,
        freewheel_low_voltage_v=basic.freewheel_low_voltage_v,
        total_duration_s=basic.total_duration_s,
        switching_start_s=basic.switching_start_s,
        on_time_s=basic.on_time_s,
        freewheel_time_s=basic.freewheel_time_s,
        rise_time_s=basic.rise_time_s,
        fall_time_s=basic.fall_time_s,
        rise_spike_amplitude_v=rise_amp,
        fall_spike_amplitude_v=fall_amp,
        spike_ringing_frequency_hz=ring_f,
        spike_decay_rate_per_s=ring_alpha,
        discontinuous_initial_amplitude_v=dcm_amp,
        discontinuous_resonance_frequency_hz=dcm_f,
        discontinuous_decay_rate_per_s=dcm_alpha,
        noise_rms_v=max(float(noise_rms), 0.0),
        sample_rate_hz=basic.sample_rate_hz,
        random_seed=0,
    )


def evaluate_unified_dcm_fit(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    parameters: DcmSwParameters,
) -> DcmUnifiedFitResult:
    """使用生成器唯一确定性正向模型重建 CSV 并计算实时拟合指标。"""

    t = np.asarray(time_s, dtype=float)
    y = np.asarray(voltage_v, dtype=float)
    if t.ndim != 1 or y.ndim != 1 or len(t) != len(y):
        raise ValueError("time_s / voltage_v 必须是一维且点数一致")
    if len(t) < 64:
        raise ValueError("全参数校正至少需要 64 个采样点")
    if not np.all(np.isfinite(t)) or not np.all(np.isfinite(y)):
        raise ValueError("波形包含 NaN 或 Inf")

    dt = float(np.median(np.diff(t)))
    if dt <= 0:
        raise ValueError("无法确定有效采样间隔")
    _validate_for_time_axis(parameters, float(t[0]), float(t[-1]), dt)

    components = evaluate_dcm_sw_deterministic_components(t, parameters)
    reconstruction = components.deterministic_voltage_v
    residual = y - reconstruction

    full_rmse = float(np.sqrt(np.mean(residual**2)))
    centered = y - float(np.mean(y))
    denominator = float(np.dot(centered, centered))
    full_r2 = (
        1.0 - float(np.dot(residual, residual)) / denominator
        if denominator > 1e-30
        else 0.0
    )
    full_r2 = float(np.clip(full_r2, -1.0, 1.0))

    signal_span = max(
        float(np.percentile(y, 99.0) - np.percentile(y, 1.0)),
        1e-9,
    )
    noise_floor = max(float(parameters.noise_rms_v), 1e-9)
    target_rmse = max(3.0 * noise_floor, 0.02 * signal_span, 1e-12)

    masks = _region_masks(t, parameters, dt)
    region_scores = {
        name: _matching_score(y, residual, mask, target_rmse)
        for name, mask in masks.items()
    }
    overall_rmse_score = 1.0 / (1.0 + (full_rmse / target_rmse) ** 2)
    overall_r2_score = float(np.clip(full_r2, 0.0, 1.0))
    overall = float(np.clip(0.65 * overall_rmse_score + 0.35 * overall_r2_score, 0.0, 1.0))
    region_scores["overall"] = overall

    return DcmUnifiedFitResult(
        parameters=parameters,
        full_rmse_v=full_rmse,
        full_r_squared=full_r2,
        final_noise_rms_v=_robust_sigma(residual),
        overall_matching_score=overall,
        region_scores=region_scores,
        reconstruction_v=reconstruction,
        residual_v=residual,
    )


def parameter_dependency_note(parameters: DcmSwParameters, key: str) -> str | None:
    """返回当前参数为何暂时不影响波形的明确原因。"""

    if key in {"spike_ringing_frequency_hz", "spike_decay_rate_per_s"}:
        if abs(parameters.rise_spike_amplitude_v) + abs(parameters.fall_spike_amplitude_v) <= 1e-15:
            return "当前无效：上升/下降尖峰电压均为 0"
    if key in {
        "discontinuous_resonance_frequency_hz",
        "discontinuous_decay_rate_per_s",
    }:
        if abs(parameters.discontinuous_initial_amplitude_v) <= 1e-15:
            return "当前无效：DCM 初始振幅为 0"
    return None


def _validate_for_time_axis(
    p: DcmSwParameters,
    start_s: float,
    end_s: float,
    dt: float,
) -> None:
    values = np.asarray(
        [
            p.baseline_voltage_v,
            p.on_high_voltage_v,
            p.freewheel_low_voltage_v,
            p.switching_start_s,
            p.rise_time_s,
            p.on_time_s,
            p.fall_time_s,
            p.freewheel_time_s,
            p.rise_spike_amplitude_v,
            p.fall_spike_amplitude_v,
            p.spike_ringing_frequency_hz,
            p.spike_decay_rate_per_s,
            p.discontinuous_initial_amplitude_v,
            p.discontinuous_resonance_frequency_hz,
            p.discontinuous_decay_rate_per_s,
        ],
        dtype=float,
    )
    if not np.all(np.isfinite(values)):
        raise ValueError("当前参数包含 NaN 或 Inf")
    if p.switching_start_s < start_s:
        raise ValueError("开关起始时间不能早于 CSV 时间轴起点")
    if min(p.rise_time_s, p.on_time_s, p.fall_time_s, p.freewheel_time_s) < 0:
        raise ValueError("上升/导通/下降/续流时间必须 >= 0")
    if min(
        p.spike_ringing_frequency_hz,
        p.spike_decay_rate_per_s,
        p.discontinuous_resonance_frequency_hz,
        p.discontinuous_decay_rate_per_s,
    ) < 0:
        raise ValueError("频率和衰减速率必须 >= 0")

    events = event_times(p)
    if events.freewheel_end_s > end_s - 2.0 * dt:
        raise ValueError("当前时间参数使 DCM 起点超出波形有效范围")

    safe_nyquist = 0.45 / dt
    if p.spike_ringing_frequency_hz > safe_nyquist:
        raise ValueError("尖峰寄生振铃频率超过当前 CSV 采样率安全范围")
    if p.discontinuous_resonance_frequency_hz > safe_nyquist:
        raise ValueError("DCM 谐振频率超过当前 CSV 采样率安全范围")


def _region_masks(
    time_s: np.ndarray,
    p: DcmSwParameters,
    dt: float,
) -> dict[str, np.ndarray]:
    t = time_s
    e = event_times(p)
    settle = max(10.0 * dt, 0.08 * max(p.on_time_s, p.freewheel_time_s, dt))
    edge_window = max(120.0 * dt, min(1.0e-6, 0.35 * max(p.on_time_s, dt)))
    dcm_window = max(200.0 * dt, min(4.0e-6, max(1.5 * p.freewheel_time_s, 1.0e-6)))

    baseline = t < max(e.rise_start_s - settle, t[0] + 8.0 * dt)
    high = (t >= e.rise_end_s + settle) & (t < e.high_end_s - settle)
    freewheel = (t >= e.fall_end_s + settle) & (t < e.freewheel_end_s - settle)
    rise_edge = (t >= e.rise_start_s - edge_window * 0.25) & (t <= e.rise_end_s + edge_window)
    fall_edge = (t >= e.high_end_s - edge_window * 0.35) & (t <= e.fall_end_s + edge_window)
    edges = rise_edge | fall_edge
    dcm = (t >= e.freewheel_end_s) & (t <= min(t[-1], e.freewheel_end_s + dcm_window))

    masks = {
        "baseline": baseline,
        "high": high,
        "freewheel": freewheel,
        "rise_edge": rise_edge,
        "fall_edge": fall_edge,
        "edges": edges,
        "dcm": dcm,
    }
    for name, mask in list(masks.items()):
        if np.count_nonzero(mask) < 8:
            masks[name] = np.ones(len(t), dtype=bool)
    return masks


def _matching_score(
    y: np.ndarray,
    residual: np.ndarray,
    mask: np.ndarray,
    target_rmse: float,
) -> float:
    local_y = y[mask]
    local_error = residual[mask]
    rmse = float(np.sqrt(np.mean(local_error**2)))
    centered = local_y - float(np.mean(local_y))
    denom = float(np.dot(centered, centered))
    r2 = 1.0 - float(np.dot(local_error, local_error)) / denom if denom > 1e-30 else 0.0
    rmse_score = 1.0 / (1.0 + (rmse / target_rmse) ** 2)
    return float(np.clip(0.70 * rmse_score + 0.30 * np.clip(r2, 0.0, 1.0), 0.0, 1.0))


def _robust_sigma(values: np.ndarray) -> float:
    x = np.asarray(values, dtype=float)
    median = float(np.median(x))
    mad = float(np.median(np.abs(x - median)))
    return 1.4826 * mad
