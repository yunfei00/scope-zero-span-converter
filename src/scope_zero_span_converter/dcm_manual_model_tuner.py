from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .dcm_discontinuous_extractor import DcmDiscontinuousExtractionResult
from .dcm_global_refiner import DcmGlobalRefinementResult
from .dcm_parameter_extractor import DcmBasicExtractionResult
from .dcm_ringing_extractor import DcmRingingExtractionResult


@dataclass(frozen=True)
class DcmManualModelParameters:
    """研究人员可直接人工调节的完整 DCM 现象模型参数。"""

    baseline_voltage_v: float
    on_high_voltage_v: float
    freewheel_low_voltage_v: float

    switching_start_s: float
    rise_time_s: float
    on_time_s: float
    fall_time_s: float
    freewheel_time_s: float

    rise_spike_amplitude_v: float
    rise_spike_phase_rad: float
    fall_spike_amplitude_v: float
    fall_spike_phase_rad: float
    ringing_frequency_hz: float
    ringing_decay_rate_per_s: float

    dcm_initial_amplitude_v: float
    dcm_phase_rad: float
    dcm_frequency_hz: float
    dcm_decay_rate_per_s: float

    @property
    def rise_end_s(self) -> float:
        return self.switching_start_s + self.rise_time_s

    @property
    def fall_start_s(self) -> float:
        return self.rise_end_s + self.on_time_s

    @property
    def fall_end_s(self) -> float:
        return self.fall_start_s + self.fall_time_s

    @property
    def freewheel_end_s(self) -> float:
        return self.fall_end_s + self.freewheel_time_s

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_voltage_v": self.baseline_voltage_v,
            "on_high_voltage_v": self.on_high_voltage_v,
            "freewheel_low_voltage_v": self.freewheel_low_voltage_v,
            "switching_start_s": self.switching_start_s,
            "rise_time_s": self.rise_time_s,
            "on_time_s": self.on_time_s,
            "fall_time_s": self.fall_time_s,
            "freewheel_time_s": self.freewheel_time_s,
            "rise_spike_amplitude_v": self.rise_spike_amplitude_v,
            "rise_spike_phase_rad": self.rise_spike_phase_rad,
            "fall_spike_amplitude_v": self.fall_spike_amplitude_v,
            "fall_spike_phase_rad": self.fall_spike_phase_rad,
            "ringing_frequency_hz": self.ringing_frequency_hz,
            "ringing_decay_rate_per_s": self.ringing_decay_rate_per_s,
            "dcm_initial_amplitude_v": self.dcm_initial_amplitude_v,
            "dcm_phase_rad": self.dcm_phase_rad,
            "dcm_frequency_hz": self.dcm_frequency_hz,
            "dcm_decay_rate_per_s": self.dcm_decay_rate_per_s,
        }


@dataclass(frozen=True)
class DcmManualModelFitResult:
    """当前人工参数对应的完整重建、残差和局部匹配指标。"""

    parameters: DcmManualModelParameters
    full_rmse_v: float
    full_r_squared: float
    final_noise_rms_v: float
    overall_matching_score: float
    region_scores: dict[str, float]
    reconstruction_v: np.ndarray
    residual_v: np.ndarray

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": "dcm_manual_full_model_tuner_v1",
            "parameters": self.parameters.to_dict(),
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
) -> DcmManualModelParameters:
    """把自动分阶段/联合精修结果转换为可人工编辑的模型初值。"""

    if global_result is not None:
        return DcmManualModelParameters(
            baseline_voltage_v=global_result.baseline_voltage_v,
            on_high_voltage_v=global_result.on_high_voltage_v,
            freewheel_low_voltage_v=global_result.freewheel_low_voltage_v,
            switching_start_s=global_result.switching_start_s,
            rise_time_s=global_result.rise_time_s,
            on_time_s=global_result.on_time_s,
            fall_time_s=global_result.fall_time_s,
            freewheel_time_s=global_result.freewheel_time_s,
            rise_spike_amplitude_v=global_result.rise_spike_amplitude_v,
            rise_spike_phase_rad=global_result.rise_spike_phase_rad,
            fall_spike_amplitude_v=global_result.fall_spike_amplitude_v,
            fall_spike_phase_rad=global_result.fall_spike_phase_rad,
            ringing_frequency_hz=global_result.ringing_frequency_hz,
            ringing_decay_rate_per_s=global_result.ringing_decay_rate_per_s,
            dcm_initial_amplitude_v=global_result.dcm_initial_amplitude_v,
            dcm_phase_rad=global_result.dcm_phase_rad,
            dcm_frequency_hz=global_result.dcm_frequency_hz,
            dcm_decay_rate_per_s=global_result.dcm_decay_rate_per_s,
        )

    if ringing is None:
        rise_amp = 0.0
        rise_phase = 0.0
        fall_amp = 0.0
        fall_phase = 0.0
        ring_f = 0.0
        ring_alpha = 0.0
    else:
        rise_amp = ringing.rise.signed_initial_amplitude_v
        rise_phase = ringing.rise.phase_rad
        fall_amp = ringing.fall.signed_initial_amplitude_v
        fall_phase = ringing.fall.phase_rad
        ring_f = ringing.ringing_frequency_hz
        ring_alpha = ringing.decay_rate_per_s

    if dcm is None:
        dcm_amp = 0.0
        dcm_phase = 0.0
        dcm_f = 0.0
        dcm_alpha = 0.0
    else:
        dcm_amp = dcm.signed_initial_amplitude_v
        dcm_phase = dcm.phase_rad
        dcm_f = dcm.resonance_frequency_hz
        dcm_alpha = dcm.decay_rate_per_s

    return DcmManualModelParameters(
        baseline_voltage_v=basic.baseline_voltage_v,
        on_high_voltage_v=basic.on_high_voltage_v,
        freewheel_low_voltage_v=basic.freewheel_low_voltage_v,
        switching_start_s=basic.switching_start_s,
        rise_time_s=basic.rise_time_s,
        on_time_s=basic.on_time_s,
        fall_time_s=basic.fall_time_s,
        freewheel_time_s=basic.freewheel_time_s,
        rise_spike_amplitude_v=rise_amp,
        rise_spike_phase_rad=rise_phase,
        fall_spike_amplitude_v=fall_amp,
        fall_spike_phase_rad=fall_phase,
        ringing_frequency_hz=ring_f,
        ringing_decay_rate_per_s=ring_alpha,
        dcm_initial_amplitude_v=dcm_amp,
        dcm_phase_rad=dcm_phase,
        dcm_frequency_hz=dcm_f,
        dcm_decay_rate_per_s=dcm_alpha,
    )


def evaluate_manual_dcm_model(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    parameters: DcmManualModelParameters,
    *,
    estimated_noise_rms_v: float,
    reconstruction_chunk_points: int = 200_000,
) -> DcmManualModelFitResult:
    """按当前人工参数原样重建完整波形，并计算用于人工调参的实时匹配度。"""

    t = np.asarray(time_s, dtype=float)
    y = np.asarray(voltage_v, dtype=float)
    if t.ndim != 1 or y.ndim != 1 or len(t) != len(y):
        raise ValueError("time_s / voltage_v 必须是一维且点数一致")
    if len(t) < 64:
        raise ValueError("人工全参数校正至少需要 64 个采样点")
    if not np.all(np.isfinite(t)) or not np.all(np.isfinite(y)):
        raise ValueError("波形包含 NaN 或 Inf")

    dt = float(np.median(np.diff(t)))
    if dt <= 0:
        raise ValueError("无法确定有效采样间隔")
    _validate_parameters(parameters, float(t[0]), float(t[-1]), dt)

    reconstruction = np.empty_like(y, dtype=float)
    chunk = max(10_000, int(reconstruction_chunk_points))
    for start in range(0, len(t), chunk):
        stop = min(len(t), start + chunk)
        reconstruction[start:stop] = _reconstruct_chunk(t[start:stop], parameters)

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
    noise_floor = max(float(estimated_noise_rms_v), 1e-9)
    target_rmse = max(3.0 * noise_floor, 0.02 * signal_span, 1e-12)

    masks = _region_masks(t, parameters, dt)
    region_scores: dict[str, float] = {}
    for name, mask in masks.items():
        region_scores[name] = _matching_score(y, residual, mask, target_rmse)

    overall_rmse_score = 1.0 / (1.0 + (full_rmse / target_rmse) ** 2)
    overall_r2_score = float(np.clip(full_r2, 0.0, 1.0))
    overall = float(np.clip(0.65 * overall_rmse_score + 0.35 * overall_r2_score, 0.0, 1.0))
    region_scores["overall"] = overall

    return DcmManualModelFitResult(
        parameters=parameters,
        full_rmse_v=full_rmse,
        full_r_squared=full_r2,
        final_noise_rms_v=_robust_sigma(residual),
        overall_matching_score=overall,
        region_scores=region_scores,
        reconstruction_v=reconstruction,
        residual_v=residual,
    )


def _validate_parameters(
    p: DcmManualModelParameters,
    start_s: float,
    end_s: float,
    dt: float,
) -> None:
    values = np.asarray(list(p.to_dict().values()), dtype=float)
    if not np.all(np.isfinite(values)):
        raise ValueError("人工参数包含 NaN 或 Inf")
    if p.switching_start_s < start_s:
        raise ValueError("开关起始时间不能早于当前 CSV 起点")
    if min(p.rise_time_s, p.on_time_s, p.fall_time_s, p.freewheel_time_s) < 0:
        raise ValueError("上升/导通/下降/续流时间必须 >= 0")
    if min(p.ringing_frequency_hz, p.ringing_decay_rate_per_s, p.dcm_frequency_hz, p.dcm_decay_rate_per_s) < 0:
        raise ValueError("频率和衰减速率必须 >= 0")
    if p.freewheel_end_s > end_s - 2.0 * dt:
        raise ValueError("当前时间参数使 DCM 起点超出波形有效范围")
    nyquist_guard = 0.45 / dt
    if p.ringing_frequency_hz > nyquist_guard or p.dcm_frequency_hz > nyquist_guard:
        raise ValueError("当前振铃频率超过采样率允许的安全范围")


def _reconstruct_chunk(time_s: np.ndarray, p: DcmManualModelParameters) -> np.ndarray:
    t = np.asarray(time_s, dtype=float)
    out = np.full(len(t), p.baseline_voltage_v, dtype=float)

    t0 = p.switching_start_s
    rise_end = p.rise_end_s
    fall_start = p.fall_start_s
    fall_end = p.fall_end_s
    freewheel_end = p.freewheel_end_s

    if p.rise_time_s > 0:
        mask = (t >= t0) & (t < rise_end)
        if np.any(mask):
            u = np.clip((t[mask] - t0) / p.rise_time_s, 0.0, 1.0)
            smooth = 0.5 - 0.5 * np.cos(np.pi * u)
            out[mask] = (
                p.baseline_voltage_v
                + (p.on_high_voltage_v - p.baseline_voltage_v) * smooth
            )

    high_mask = (t >= rise_end) & (t < fall_start)
    out[high_mask] = p.on_high_voltage_v

    if p.fall_time_s > 0:
        mask = (t >= fall_start) & (t < fall_end)
        if np.any(mask):
            u = np.clip((t[mask] - fall_start) / p.fall_time_s, 0.0, 1.0)
            smooth = 0.5 - 0.5 * np.cos(np.pi * u)
            out[mask] = (
                p.on_high_voltage_v
                + (p.freewheel_low_voltage_v - p.on_high_voltage_v) * smooth
            )

    low_mask = (t >= fall_end) & (t < freewheel_end)
    out[low_mask] = p.freewheel_low_voltage_v

    _add_damped_component(
        out,
        t,
        rise_end,
        p.rise_spike_amplitude_v,
        p.rise_spike_phase_rad,
        p.ringing_frequency_hz,
        p.ringing_decay_rate_per_s,
    )
    _add_damped_component(
        out,
        t,
        fall_end,
        p.fall_spike_amplitude_v,
        p.fall_spike_phase_rad,
        p.ringing_frequency_hz,
        p.ringing_decay_rate_per_s,
    )
    _add_damped_component(
        out,
        t,
        freewheel_end,
        p.dcm_initial_amplitude_v,
        p.dcm_phase_rad,
        p.dcm_frequency_hz,
        p.dcm_decay_rate_per_s,
    )
    return out


def _add_damped_component(
    output: np.ndarray,
    time_s: np.ndarray,
    start_s: float,
    amplitude_v: float,
    phase_rad: float,
    frequency_hz: float,
    decay_rate_per_s: float,
) -> None:
    if amplitude_v == 0.0:
        return
    mask = time_s >= start_s
    if not np.any(mask):
        return
    local_t = time_s[mask] - start_s
    envelope = np.exp(-decay_rate_per_s * local_t)
    output[mask] += amplitude_v * envelope * np.cos(
        2.0 * np.pi * frequency_hz * local_t + phase_rad
    )


def _region_masks(
    time_s: np.ndarray,
    p: DcmManualModelParameters,
    dt: float,
) -> dict[str, np.ndarray]:
    t = time_s
    rise_end = p.rise_end_s
    fall_start = p.fall_start_s
    fall_end = p.fall_end_s
    freewheel_end = p.freewheel_end_s

    settle = max(10.0 * dt, 0.08 * max(p.on_time_s, p.freewheel_time_s, dt))
    edge_window = max(120.0 * dt, min(1.0e-6, 0.30 * max(p.on_time_s, p.freewheel_time_s, dt)))
    dcm_window = max(200.0 * dt, min(5.0e-6, max(t[-1] - freewheel_end, dt)))

    baseline = t < max(t[0], p.switching_start_s - settle)
    high = (t >= rise_end + settle) & (t < fall_start - settle)
    freewheel = (t >= fall_end + settle) & (t < freewheel_end - settle)
    rise_edge = (t >= p.switching_start_s - 20.0 * dt) & (t <= rise_end + edge_window)
    fall_edge = (t >= fall_start - 20.0 * dt) & (t <= fall_end + edge_window)
    dcm = (t >= freewheel_end) & (t <= freewheel_end + dcm_window)

    all_mask = np.ones(len(t), dtype=bool)
    return {
        "baseline": baseline if np.count_nonzero(baseline) >= 8 else all_mask,
        "high": high if np.count_nonzero(high) >= 8 else all_mask,
        "freewheel": freewheel if np.count_nonzero(freewheel) >= 8 else all_mask,
        "rise_edge": rise_edge if np.count_nonzero(rise_edge) >= 8 else all_mask,
        "fall_edge": fall_edge if np.count_nonzero(fall_edge) >= 8 else all_mask,
        "dcm": dcm if np.count_nonzero(dcm) >= 8 else all_mask,
    }


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
    denominator = float(np.dot(centered, centered))
    r2 = (
        1.0 - float(np.dot(local_error, local_error)) / denominator
        if denominator > 1e-30
        else 0.0
    )
    rmse_score = 1.0 / (1.0 + (rmse / target_rmse) ** 2)
    r2_score = float(np.clip(r2, 0.0, 1.0))
    return float(np.clip(0.70 * rmse_score + 0.30 * r2_score, 0.0, 1.0))


def _robust_sigma(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    return 1.4826 * mad
