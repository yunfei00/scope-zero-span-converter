from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .dcm_discontinuous_extractor import DcmDiscontinuousExtractionResult
from .dcm_global_refiner import (
    DcmGlobalRefinementResult,
    _design_matrix,
    _final_linear_fit_indices,
    _fit_weights,
    _ideal_basis,
    _robust_sigma,
    _valid_timing,
)
from .dcm_parameter_extractor import DcmBasicExtractionResult
from .dcm_ringing_extractor import DcmRingingExtractionResult


@dataclass(frozen=True)
class DcmManualOnTimeTuningResult:
    """人工调整导通时间后的实时重建与匹配度结果。

    matching_score 是工程上的“当前波形匹配度”，用于人工观察调参方向，
    不等同于统计意义上的置信区间，也不会覆盖自动提取阶段原有置信度。
    """

    source: str
    on_time_s: float
    fall_start_s: float
    fall_end_s: float
    freewheel_end_s: float
    local_rmse_v: float
    local_r_squared: float
    full_rmse_v: float
    full_r_squared: float
    matching_score: float
    final_noise_rms_v: float
    reconstruction_v: np.ndarray
    residual_v: np.ndarray

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": "dcm_manual_on_time_tuner_v2",
            "source": self.source,
            "on_time_s": self.on_time_s,
            "fall_start_s": self.fall_start_s,
            "fall_end_s": self.fall_end_s,
            "freewheel_end_s": self.freewheel_end_s,
            "fit_quality": {
                "matching_score": self.matching_score,
                "local_rmse_v": self.local_rmse_v,
                "local_r_squared": self.local_r_squared,
                "full_rmse_v": self.full_rmse_v,
                "full_r_squared": self.full_r_squared,
                "final_noise_rms_v": self.final_noise_rms_v,
            },
        }


def tune_dcm_on_time_manually(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    basic: DcmBasicExtractionResult,
    ringing: DcmRingingExtractionResult | None = None,
    dcm: DcmDiscontinuousExtractionResult | None = None,
    *,
    on_time_s: float,
    global_result: DcmGlobalRefinementResult | None = None,
    max_fit_points: int = 60_000,
    reconstruction_chunk_points: int = 200_000,
) -> DcmManualOnTimeTuningResult:
    """固定其它已知参数，仅人工调整导通时间并实时重建完整波形。

    人工导通时间校正只依赖第一阶段基础提取结果即可使用：
    - 若全局联合精修已完成，优先使用联合精修的其它参数；
    - 若尖峰/振铃和 DCM 两阶段都成功，则使用完整分阶段模型；
    - 若后续阶段任一未完成，则自动退化为基础电平/时间轨迹重建。

    因此真实 CSV 上即使寄生振铃或 DCM 拟合失败，导通时间滑块仍然可以工作，
    用户仍可通过下降沿位置和基础轨迹重合程度进行人工校正。
    """

    t = np.asarray(time_s, dtype=float)
    y = np.asarray(voltage_v, dtype=float)
    if t.ndim != 1 or y.ndim != 1 or len(t) != len(y):
        raise ValueError("time_s / voltage_v 必须是一维且点数一致")
    if len(t) < 64:
        raise ValueError("人工校正至少需要 64 个采样点")
    if not np.isfinite(on_time_s) or on_time_s < 0:
        raise ValueError("导通时间必须 >= 0")

    dt = float(np.median(np.diff(t)))
    if dt <= 0:
        raise ValueError("无法确定有效采样间隔")

    use_full_model = False
    if global_result is not None:
        source = "global_refinement"
        use_full_model = True
        x = np.array(
            [
                global_result.switching_start_s,
                global_result.rise_time_s,
                float(on_time_s),
                global_result.fall_time_s,
                global_result.freewheel_time_s,
                global_result.ringing_frequency_hz,
                global_result.ringing_decay_rate_per_s,
                global_result.dcm_frequency_hz,
                global_result.dcm_decay_rate_per_s,
            ],
            dtype=float,
        )
    elif ringing is not None and dcm is not None:
        source = "staged_full_model"
        use_full_model = True
        x = np.array(
            [
                basic.switching_start_s,
                basic.rise_time_s,
                float(on_time_s),
                basic.fall_time_s,
                basic.freewheel_time_s,
                ringing.ringing_frequency_hz,
                ringing.decay_rate_per_s,
                dcm.resonance_frequency_hz,
                dcm.decay_rate_per_s,
            ],
            dtype=float,
        )
    else:
        source = "basic_fallback"
        x = np.array(
            [
                basic.switching_start_s,
                basic.rise_time_s,
                float(on_time_s),
                basic.fall_time_s,
                basic.freewheel_time_s,
                0.0,
                0.0,
                0.0,
                0.0,
            ],
            dtype=float,
        )

    if not _valid_timing(x, float(t[0]), float(t[-1]), dt):
        raise ValueError("当前导通时间会使下降沿/续流/DCM 区域超出波形时间范围")

    def build_matrix(current_t: np.ndarray) -> np.ndarray:
        if use_full_model:
            return _design_matrix(current_t, x)
        baseline, high, low = _ideal_basis(current_t, x)
        return np.column_stack((baseline, high, low))

    fit_indices = _final_linear_fit_indices(
        t,
        x,
        max_points=max(2_000, int(max_fit_points)),
    )
    fit_t = t[fit_indices]
    fit_y = y[fit_indices]
    matrix = build_matrix(fit_t)
    weights = _fit_weights(fit_t, x, dt)
    sqrt_w = np.sqrt(weights)
    coeff, *_ = np.linalg.lstsq(
        matrix * sqrt_w[:, None],
        fit_y * sqrt_w,
        rcond=None,
    )

    reconstruction = np.empty_like(y, dtype=float)
    chunk = max(10_000, int(reconstruction_chunk_points))
    for start in range(0, len(t), chunk):
        stop = min(len(t), start + chunk)
        reconstruction[start:stop] = build_matrix(t[start:stop]) @ coeff

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

    t0, tr, ton, tf, tfw = map(float, x[:5])
    fall_start = t0 + tr + ton
    fall_end = fall_start + tf
    freewheel_end = fall_end + tfw

    signal_span = max(
        float(np.percentile(y, 99.0) - np.percentile(y, 1.0)),
        1e-9,
    )
    noise_floor = max(float(basic.estimated_noise_rms_v), 1e-9)

    # 导通时间最直接决定下降沿位置，因此匹配度重点观察下降沿前后局部窗口。
    before = max(80.0 * dt, min(0.45e-6, 0.12 * max(ton, dt)))
    after = max(160.0 * dt, min(1.20e-6, 0.35 * max(tfw, dt)))
    local_mask = (t >= fall_start - before) & (t <= fall_end + after)
    if np.count_nonzero(local_mask) < 16:
        local_mask = np.ones(len(t), dtype=bool)

    local_y = y[local_mask]
    local_error = residual[local_mask]
    local_rmse = float(np.sqrt(np.mean(local_error**2)))
    local_centered = local_y - float(np.mean(local_y))
    local_denominator = float(np.dot(local_centered, local_centered))
    local_r2 = (
        1.0 - float(np.dot(local_error, local_error)) / local_denominator
        if local_denominator > 1e-30
        else 0.0
    )
    local_r2 = float(np.clip(local_r2, -1.0, 1.0))

    # 工程匹配度：局部 RMSE 相对于信号摆幅/噪声底的综合归一化，再与局部 R² 融合。
    # 该值只用于人工调参方向判断，不作为统计置信区间。
    target_rmse = max(3.0 * noise_floor, 0.02 * signal_span, 1e-12)
    rmse_score = 1.0 / (1.0 + (local_rmse / target_rmse) ** 2)
    r2_score = float(np.clip(local_r2, 0.0, 1.0))
    matching_score = float(np.clip(0.70 * rmse_score + 0.30 * r2_score, 0.0, 1.0))

    return DcmManualOnTimeTuningResult(
        source=source,
        on_time_s=float(on_time_s),
        fall_start_s=fall_start,
        fall_end_s=fall_end,
        freewheel_end_s=freewheel_end,
        local_rmse_v=local_rmse,
        local_r_squared=local_r2,
        full_rmse_v=full_rmse,
        full_r_squared=full_r2,
        matching_score=matching_score,
        final_noise_rms_v=float(_robust_sigma(residual)),
        reconstruction_v=reconstruction,
        residual_v=residual,
    )
