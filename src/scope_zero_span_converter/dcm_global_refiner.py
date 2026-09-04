from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .dcm_discontinuous_extractor import DcmDiscontinuousExtractionResult
from .dcm_parameter_extractor import DcmBasicExtractionResult
from .dcm_ringing_extractor import DcmRingingExtractionResult


_NONLINEAR_NAMES = (
    "switching_start_s",
    "rise_time_s",
    "on_time_s",
    "fall_time_s",
    "freewheel_time_s",
    "ringing_frequency_hz",
    "ringing_decay_rate_per_s",
    "dcm_frequency_hz",
    "dcm_decay_rate_per_s",
)


@dataclass(frozen=True)
class DcmGlobalRefinementResult:
    """第四阶段：以前三阶段结果为初值的完整 DCM 波形联合精修结果。"""

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

    staged_rmse_v: float
    optimized_rmse_v: float
    rmse_improvement_percent: float
    final_noise_rms_v: float
    full_r_squared: float
    objective_initial: float
    objective_final: float
    iterations: int
    evaluations: int
    converged: bool
    optimized_points: int
    warnings: tuple[str, ...]
    optimized_reconstruction_v: np.ndarray
    final_residual_v: np.ndarray

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
            "algorithm": "dcm_global_joint_refiner_v1",
            "optimized_parameters": {
                "levels": {
                    "baseline_voltage_v": self.baseline_voltage_v,
                    "on_high_voltage_v": self.on_high_voltage_v,
                    "freewheel_low_voltage_v": self.freewheel_low_voltage_v,
                },
                "timing": {
                    "switching_start_s": self.switching_start_s,
                    "rise_time_s": self.rise_time_s,
                    "rise_end_s": self.rise_end_s,
                    "on_time_s": self.on_time_s,
                    "fall_start_s": self.fall_start_s,
                    "fall_time_s": self.fall_time_s,
                    "fall_end_s": self.fall_end_s,
                    "freewheel_time_s": self.freewheel_time_s,
                    "freewheel_end_s": self.freewheel_end_s,
                },
                "edge_ringing": {
                    "rise_spike_amplitude_v": self.rise_spike_amplitude_v,
                    "rise_spike_phase_rad": self.rise_spike_phase_rad,
                    "fall_spike_amplitude_v": self.fall_spike_amplitude_v,
                    "fall_spike_phase_rad": self.fall_spike_phase_rad,
                    "ringing_frequency_hz": self.ringing_frequency_hz,
                    "ringing_decay_rate_per_s": self.ringing_decay_rate_per_s,
                },
                "discontinuous_resonance": {
                    "initial_amplitude_v": self.dcm_initial_amplitude_v,
                    "phase_rad": self.dcm_phase_rad,
                    "frequency_hz": self.dcm_frequency_hz,
                    "decay_rate_per_s": self.dcm_decay_rate_per_s,
                },
            },
            "fit_quality": {
                "staged_rmse_v": self.staged_rmse_v,
                "optimized_rmse_v": self.optimized_rmse_v,
                "rmse_improvement_percent": self.rmse_improvement_percent,
                "final_noise_rms_v": self.final_noise_rms_v,
                "full_r_squared": self.full_r_squared,
            },
            "optimization": {
                "objective_initial": self.objective_initial,
                "objective_final": self.objective_final,
                "iterations": self.iterations,
                "evaluations": self.evaluations,
                "converged": self.converged,
                "optimized_points": self.optimized_points,
            },
            "warnings": list(self.warnings),
        }


def refine_dcm_parameters_globally(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    basic: DcmBasicExtractionResult,
    ringing: DcmRingingExtractionResult,
    dcm: DcmDiscontinuousExtractionResult,
    *,
    max_iterations: int = 10,
    max_optimization_points: int = 18_000,
) -> DcmGlobalRefinementResult:
    """以分阶段参数为初值，联合精修完整 DCM 模型。

    设计原则：
    - 仍然只使用 time_s / voltage_v 和前三阶段由二者得到的结果；
    - 不读取合成 CSV 真值列或参数 JSON；
    - 非线性参数只在分阶段初值附近做有界搜索，避免真实波形中过拟合；
    - 每个非线性候选点上，电平和三个阻尼振铃的 cos/sin 系数用加权
      线性最小二乘直接求最优值；
    - 优化抽样保留边沿和 DCM 瞬态高密度点，最终重建仍返回完整时间轴。
    """

    t = np.asarray(time_s, dtype=float)
    y = np.asarray(voltage_v, dtype=float)
    if t.ndim != 1 or y.ndim != 1 or len(t) != len(y):
        raise ValueError("time_s / voltage_v 必须是一维且点数一致")
    if len(t) < 64:
        raise ValueError("全局联合优化至少需要 64 个采样点")
    if len(basic.fitted_ideal_voltage_v) != len(t):
        raise ValueError("基础提取结果与当前波形点数不一致")
    if len(ringing.fitted_spike_component_v) != len(t):
        raise ValueError("尖峰/振铃结果与当前波形点数不一致")
    if len(dcm.fitted_discontinuous_component_v) != len(t):
        raise ValueError("DCM 结果与当前波形点数不一致")

    dt = float(np.median(np.diff(t)))
    if dt <= 0:
        raise ValueError("无法确定有效采样间隔")
    duration = float(t[-1] - t[0])
    if duration <= 0:
        raise ValueError("波形总时长必须 > 0")

    staged_reconstruction = (
        np.asarray(basic.fitted_ideal_voltage_v, dtype=float)
        + np.asarray(ringing.fitted_spike_component_v, dtype=float)
        + np.asarray(dcm.fitted_discontinuous_component_v, dtype=float)
    )
    staged_residual = y - staged_reconstruction
    staged_rmse = float(np.sqrt(np.mean(staged_residual**2)))

    x0 = np.array(
        [
            basic.switching_start_s,
            basic.rise_time_s,
            basic.on_time_s,
            basic.fall_time_s,
            basic.freewheel_time_s,
            ringing.ringing_frequency_hz,
            ringing.decay_rate_per_s,
            dcm.resonance_frequency_hz,
            dcm.decay_rate_per_s,
        ],
        dtype=float,
    )
    lower, upper = _build_bounds(t, basic, ringing, dcm, dt)
    x0 = np.clip(x0, lower, upper)

    indices = _optimization_indices(
        t,
        basic,
        max_points=max(512, int(max_optimization_points)),
    )
    fit_t = t[indices]
    fit_y = y[indices]

    signal_scale = max(
        float(np.percentile(y, 99.0) - np.percentile(y, 1.0)),
        10.0 * max(float(basic.estimated_noise_rms_v), 1e-9),
        1e-9,
    )

    evaluations = 0

    def evaluate(candidate: np.ndarray) -> tuple[float, np.ndarray]:
        nonlocal evaluations
        evaluations += 1
        if not _valid_timing(candidate, t[0], t[-1], dt):
            return float("inf"), np.zeros(9, dtype=float)
        matrix = _design_matrix(fit_t, candidate)
        weights = _fit_weights(fit_t, candidate, dt)
        sqrt_w = np.sqrt(weights)
        weighted_matrix = matrix * sqrt_w[:, None]
        weighted_y = fit_y * sqrt_w
        coeff, *_ = np.linalg.lstsq(weighted_matrix, weighted_y, rcond=None)
        prediction = matrix @ coeff
        error = fit_y - prediction
        score = _composite_objective(
            fit_t,
            error,
            candidate,
            signal_scale=signal_scale,
            dt=dt,
        )
        spans = np.maximum(upper - lower, 1e-30)
        active = spans > 1e-20
        if np.any(active):
            regularization = float(np.mean(((candidate[active] - x0[active]) / spans[active]) ** 2))
            score += 1e-7 * regularization
        return score, coeff

    best_x = x0.copy()
    best_score, best_coeff = evaluate(best_x)
    initial_objective = float(best_score)
    spans = np.maximum(upper - lower, 0.0)
    steps = 0.18 * spans
    min_steps = np.maximum(0.0025 * spans, _minimum_steps(x0, dt))

    converged = False
    iterations_done = 0
    for iteration in range(max(1, int(max_iterations))):
        iterations_done = iteration + 1
        improved_any = False
        for dimension in range(len(best_x)):
            if spans[dimension] <= 0 or steps[dimension] <= 0:
                continue
            local_best_score = best_score
            local_best_x = best_x
            local_best_coeff = best_coeff
            for direction in (-1.0, 1.0):
                candidate = best_x.copy()
                candidate[dimension] = np.clip(
                    candidate[dimension] + direction * steps[dimension],
                    lower[dimension],
                    upper[dimension],
                )
                if candidate[dimension] == best_x[dimension]:
                    continue
                score, coeff = evaluate(candidate)
                if score < local_best_score - 1e-12:
                    local_best_score = score
                    local_best_x = candidate
                    local_best_coeff = coeff
            if local_best_score < best_score - 1e-12:
                best_x = local_best_x
                best_score = local_best_score
                best_coeff = local_best_coeff
                improved_any = True

        if not improved_any:
            steps *= 0.5
        else:
            # 有改善时也轻微收缩，逐步从粗搜索进入精修。
            steps *= 0.88

        active_steps = steps[spans > 0]
        active_min = min_steps[spans > 0]
        if active_steps.size == 0 or np.all(active_steps <= active_min):
            converged = True
            break

    # 在优化后的非线性参数上，用更完整的数据集重新求一次线性系数。
    final_indices = _final_linear_fit_indices(t, best_x, max_points=120_000)
    final_t = t[final_indices]
    final_y = y[final_indices]
    final_matrix = _design_matrix(final_t, best_x)
    final_weights = _fit_weights(final_t, best_x, dt)
    sqrt_w = np.sqrt(final_weights)
    best_coeff, *_ = np.linalg.lstsq(
        final_matrix * sqrt_w[:, None],
        final_y * sqrt_w,
        rcond=None,
    )

    full_matrix = _design_matrix(t, best_x)
    optimized_reconstruction = full_matrix @ best_coeff
    final_residual = y - optimized_reconstruction
    optimized_rmse = float(np.sqrt(np.mean(final_residual**2)))
    final_noise = _robust_sigma(final_residual)
    improvement = (
        100.0 * (staged_rmse - optimized_rmse) / staged_rmse
        if staged_rmse > 1e-30
        else 0.0
    )
    centered = y - float(np.mean(y))
    denominator = float(np.dot(centered, centered))
    full_r_squared = (
        1.0 - float(np.dot(final_residual, final_residual)) / denominator
        if denominator > 1e-30
        else 0.0
    )
    full_r_squared = float(np.clip(full_r_squared, -1.0, 1.0))

    baseline, high, low = map(float, best_coeff[:3])
    rise_amp, rise_phase = _signed_amplitude_phase(best_coeff[3], best_coeff[4])
    fall_amp, fall_phase = _signed_amplitude_phase(best_coeff[5], best_coeff[6])
    dcm_amp, dcm_phase = _signed_amplitude_phase(best_coeff[7], best_coeff[8])

    warnings: list[str] = []
    if not converged:
        warnings.append("全局联合优化达到最大迭代次数，仍可使用当前最优结果")
    if improvement < -0.5:
        warnings.append("联合优化后的全局 RMSE 略高于分阶段结果，建议优先参考分阶段参数")
    elif improvement < 0.5:
        warnings.append("联合优化对全局 RMSE 改善较小，说明分阶段初值已经较接近局部最优")
    if final_noise > max(3.0 * basic.estimated_noise_rms_v, 1e-9):
        warnings.append("最终残差仍明显高于基线区噪声，真实波形可能包含当前模型未描述的成分")

    return DcmGlobalRefinementResult(
        baseline_voltage_v=baseline,
        on_high_voltage_v=high,
        freewheel_low_voltage_v=low,
        switching_start_s=float(best_x[0]),
        rise_time_s=float(best_x[1]),
        on_time_s=float(best_x[2]),
        fall_time_s=float(best_x[3]),
        freewheel_time_s=float(best_x[4]),
        rise_spike_amplitude_v=rise_amp,
        rise_spike_phase_rad=rise_phase,
        fall_spike_amplitude_v=fall_amp,
        fall_spike_phase_rad=fall_phase,
        ringing_frequency_hz=float(best_x[5]),
        ringing_decay_rate_per_s=float(best_x[6]),
        dcm_initial_amplitude_v=dcm_amp,
        dcm_phase_rad=dcm_phase,
        dcm_frequency_hz=float(best_x[7]),
        dcm_decay_rate_per_s=float(best_x[8]),
        staged_rmse_v=staged_rmse,
        optimized_rmse_v=optimized_rmse,
        rmse_improvement_percent=float(improvement),
        final_noise_rms_v=float(final_noise),
        full_r_squared=full_r_squared,
        objective_initial=initial_objective,
        objective_final=float(best_score),
        iterations=iterations_done,
        evaluations=evaluations,
        converged=converged,
        optimized_points=len(indices),
        warnings=tuple(dict.fromkeys(warnings)),
        optimized_reconstruction_v=optimized_reconstruction,
        final_residual_v=final_residual,
    )


def _build_bounds(
    time_s: np.ndarray,
    basic: DcmBasicExtractionResult,
    ringing: DcmRingingExtractionResult,
    dcm: DcmDiscontinuousExtractionResult,
    dt: float,
) -> tuple[np.ndarray, np.ndarray]:
    duration = float(time_s[-1] - time_s[0])

    def around(value: float, half_width: float, minimum: float = 0.0) -> tuple[float, float]:
        return max(minimum, value - half_width), max(minimum, value + half_width)

    t0_half = max(12.0 * dt, 0.02 * max(basic.on_time_s, dt), 0.002 * duration)
    t0_low = max(float(time_s[0]), basic.switching_start_s - t0_half)
    t0_high = min(float(time_s[-1]), basic.switching_start_s + t0_half)

    if basic.rise_time_s <= 2.5 * dt:
        rise_low, rise_high = 0.0, max(6.0 * dt, basic.rise_time_s + 4.0 * dt)
    else:
        rise_low, rise_high = around(basic.rise_time_s, max(8.0 * dt, 0.55 * basic.rise_time_s))

    on_low, on_high = around(
        basic.on_time_s,
        max(20.0 * dt, 0.10 * max(basic.on_time_s, dt)),
    )

    if basic.fall_time_s <= 2.5 * dt:
        fall_low, fall_high = 0.0, max(6.0 * dt, basic.fall_time_s + 4.0 * dt)
    else:
        fall_low, fall_high = around(basic.fall_time_s, max(8.0 * dt, 0.55 * basic.fall_time_s))

    freewheel_low, freewheel_high = around(
        basic.freewheel_time_s,
        max(20.0 * dt, 0.14 * max(basic.freewheel_time_s, dt)),
    )

    edge_signal = max(
        abs(ringing.rise.signed_initial_amplitude_v),
        abs(ringing.fall.signed_initial_amplitude_v),
    )
    noise = max(float(basic.estimated_noise_rms_v), 1e-12)
    if ringing.ringing_frequency_hz > 0 and edge_signal >= 2.5 * noise:
        ring_f_low = max(0.0, 0.70 * ringing.ringing_frequency_hz)
        ring_f_high = 1.30 * ringing.ringing_frequency_hz
        if ringing.decay_rate_per_s > 0:
            ring_a_low = 0.40 * ringing.decay_rate_per_s
            ring_a_high = 1.80 * ringing.decay_rate_per_s
        else:
            ring_a_low = 0.0
            ring_a_high = max(5.0 / max(basic.on_time_s, 50.0 * dt), 1.0)
    else:
        ring_f_low = ring_f_high = max(0.0, ringing.ringing_frequency_hz)
        ring_a_low = ring_a_high = max(0.0, ringing.decay_rate_per_s)

    if dcm.resonance_frequency_hz > 0 and abs(dcm.signed_initial_amplitude_v) >= 2.5 * noise:
        dcm_f_low = max(0.0, 0.70 * dcm.resonance_frequency_hz)
        dcm_f_high = 1.30 * dcm.resonance_frequency_hz
        if dcm.decay_rate_per_s > 0:
            dcm_a_low = 0.40 * dcm.decay_rate_per_s
            dcm_a_high = 1.80 * dcm.decay_rate_per_s
        else:
            dcm_a_low = 0.0
            dcm_a_high = max(5.0 / max(duration - basic.freewheel_end_s, 50.0 * dt), 1.0)
    else:
        dcm_f_low = dcm_f_high = max(0.0, dcm.resonance_frequency_hz)
        dcm_a_low = dcm_a_high = max(0.0, dcm.decay_rate_per_s)

    nyquist_guard = 0.45 / dt
    ring_f_high = min(ring_f_high, nyquist_guard)
    dcm_f_high = min(dcm_f_high, nyquist_guard)

    lower = np.array(
        [
            t0_low,
            rise_low,
            on_low,
            fall_low,
            freewheel_low,
            ring_f_low,
            ring_a_low,
            dcm_f_low,
            dcm_a_low,
        ],
        dtype=float,
    )
    upper = np.array(
        [
            t0_high,
            rise_high,
            on_high,
            fall_high,
            freewheel_high,
            ring_f_high,
            ring_a_high,
            dcm_f_high,
            dcm_a_high,
        ],
        dtype=float,
    )
    upper = np.maximum(upper, lower)
    return lower, upper


def _minimum_steps(x0: np.ndarray, dt: float) -> np.ndarray:
    return np.array(
        [
            0.5 * dt,
            0.5 * dt,
            0.5 * dt,
            0.5 * dt,
            0.5 * dt,
            max(1e-4 * max(x0[5], 1.0), 1.0),
            max(1e-4 * max(x0[6], 1.0), 1.0),
            max(1e-4 * max(x0[7], 1.0), 1.0),
            max(1e-4 * max(x0[8], 1.0), 1.0),
        ],
        dtype=float,
    )


def _valid_timing(x: np.ndarray, start_s: float, end_s: float, dt: float) -> bool:
    t0, tr, ton, tf, tfw = map(float, x[:5])
    if t0 < start_s or min(tr, ton, tf, tfw) < 0:
        return False
    rise_end = t0 + tr
    fall_start = rise_end + ton
    fall_end = fall_start + tf
    freewheel_end = fall_end + tfw
    return (
        rise_end <= fall_start
        and fall_start <= fall_end
        and fall_end <= freewheel_end
        and freewheel_end <= end_s - 2.0 * dt
    )


def _ideal_basis(time_s: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    t0, tr, ton, tf, tfw = map(float, x[:5])
    rise_end = t0 + tr
    fall_start = rise_end + ton
    fall_end = fall_start + tf
    freewheel_end = fall_end + tfw

    baseline = np.zeros(len(time_s), dtype=float)
    high = np.zeros(len(time_s), dtype=float)
    low = np.zeros(len(time_s), dtype=float)

    baseline[time_s < t0] = 1.0

    if tr > 0:
        mask = (time_s >= t0) & (time_s < rise_end)
        u = np.clip((time_s[mask] - t0) / tr, 0.0, 1.0)
        smooth = 0.5 - 0.5 * np.cos(np.pi * u)
        baseline[mask] = 1.0 - smooth
        high[mask] = smooth
    else:
        rise_end = t0

    high[(time_s >= rise_end) & (time_s < fall_start)] = 1.0

    if tf > 0:
        mask = (time_s >= fall_start) & (time_s < fall_end)
        u = np.clip((time_s[mask] - fall_start) / tf, 0.0, 1.0)
        smooth = 0.5 - 0.5 * np.cos(np.pi * u)
        high[mask] = 1.0 - smooth
        low[mask] = smooth
    else:
        fall_end = fall_start

    low[(time_s >= fall_end) & (time_s < freewheel_end)] = 1.0
    baseline[time_s >= freewheel_end] = 1.0
    return baseline, high, low


def _damped_basis(
    time_s: np.ndarray,
    start_s: float,
    frequency_hz: float,
    decay_rate_per_s: float,
) -> tuple[np.ndarray, np.ndarray]:
    cosine = np.zeros(len(time_s), dtype=float)
    sine = np.zeros(len(time_s), dtype=float)
    active = time_s >= start_s
    if not np.any(active):
        return cosine, sine
    local_t = time_s[active] - start_s
    envelope = np.exp(-max(0.0, decay_rate_per_s) * local_t)
    angle = 2.0 * np.pi * max(0.0, frequency_hz) * local_t
    cosine[active] = envelope * np.cos(angle)
    sine[active] = envelope * np.sin(angle)
    return cosine, sine


def _design_matrix(time_s: np.ndarray, x: np.ndarray) -> np.ndarray:
    t0, tr, ton, tf, tfw, ring_f, ring_alpha, dcm_f, dcm_alpha = map(float, x)
    rise_end = t0 + tr
    fall_start = rise_end + ton
    fall_end = fall_start + tf
    freewheel_end = fall_end + tfw

    base, high, low = _ideal_basis(time_s, x)
    rise_cos, rise_sin = _damped_basis(time_s, rise_end, ring_f, ring_alpha)
    fall_cos, fall_sin = _damped_basis(time_s, fall_end, ring_f, ring_alpha)
    dcm_cos, dcm_sin = _damped_basis(time_s, freewheel_end, dcm_f, dcm_alpha)
    return np.column_stack(
        (
            base,
            high,
            low,
            rise_cos,
            rise_sin,
            fall_cos,
            fall_sin,
            dcm_cos,
            dcm_sin,
        )
    )


def _fit_weights(time_s: np.ndarray, x: np.ndarray, dt: float) -> np.ndarray:
    t0, tr, ton, tf, tfw = map(float, x[:5])
    rise_end = t0 + tr
    fall_start = rise_end + ton
    fall_end = fall_start + tf
    freewheel_end = fall_end + tfw

    weights = np.ones(len(time_s), dtype=float)
    edge_window = max(80.0 * dt, min(1.0e-6, 0.35 * max(ton, tfw, dt)))
    weights[(time_s >= rise_end) & (time_s <= rise_end + edge_window)] = 5.0
    weights[(time_s >= fall_end) & (time_s <= fall_end + edge_window)] = 5.0
    dcm_window = max(160.0 * dt, min(5.0e-6, max(time_s[-1] - freewheel_end, dt)))
    weights[(time_s >= freewheel_end) & (time_s <= freewheel_end + dcm_window)] = 3.0
    return weights


def _composite_objective(
    time_s: np.ndarray,
    error_v: np.ndarray,
    x: np.ndarray,
    *,
    signal_scale: float,
    dt: float,
) -> float:
    t0, tr, ton, tf, tfw = map(float, x[:5])
    rise_end = t0 + tr
    fall_start = rise_end + ton
    fall_end = fall_start + tf
    freewheel_end = fall_end + tfw

    scale2 = max(signal_scale**2, 1e-30)
    overall = float(np.mean(error_v**2)) / scale2

    edge_window = max(80.0 * dt, min(1.0e-6, 0.35 * max(ton, tfw, dt)))
    rise_mask = (time_s >= rise_end) & (time_s <= rise_end + edge_window)
    fall_mask = (time_s >= fall_end) & (time_s <= fall_end + edge_window)
    dcm_mask = time_s >= freewheel_end

    rise_score = float(np.mean(error_v[rise_mask] ** 2)) / scale2 if np.any(rise_mask) else overall
    fall_score = float(np.mean(error_v[fall_mask] ** 2)) / scale2 if np.any(fall_mask) else overall
    dcm_score = float(np.mean(error_v[dcm_mask] ** 2)) / scale2 if np.any(dcm_mask) else overall
    return 0.55 * overall + 0.15 * rise_score + 0.15 * fall_score + 0.15 * dcm_score


def _optimization_indices(
    time_s: np.ndarray,
    basic: DcmBasicExtractionResult,
    *,
    max_points: int,
) -> np.ndarray:
    n = len(time_s)
    if n <= max_points:
        return np.arange(n, dtype=int)

    dt = float(np.median(np.diff(time_s)))
    parts: list[np.ndarray] = []
    parts.append(_even_indices(0, n, min(6000, max_points // 3)))

    edge_half = max(120.0 * dt, 0.35e-6)
    for center in (basic.rise_end_s, basic.fall_end_s):
        start = int(np.searchsorted(time_s, center - 0.10 * edge_half, side="left"))
        stop = int(np.searchsorted(time_s, center + edge_half, side="right"))
        parts.append(_even_indices(start, stop, min(3000, max_points // 5)))

    dcm_start = int(np.searchsorted(time_s, basic.freewheel_end_s, side="left"))
    dcm_stop_time = min(float(time_s[-1]), basic.freewheel_end_s + 5.0e-6)
    dcm_stop = int(np.searchsorted(time_s, dcm_stop_time, side="right"))
    parts.append(_even_indices(dcm_start, dcm_stop, min(6000, max_points // 3)))

    merged = np.unique(np.concatenate([part for part in parts if part.size]))
    if len(merged) > max_points:
        select = np.linspace(0, len(merged) - 1, max_points).astype(int)
        merged = merged[select]
    return merged.astype(int)


def _final_linear_fit_indices(time_s: np.ndarray, x: np.ndarray, *, max_points: int) -> np.ndarray:
    n = len(time_s)
    if n <= max_points:
        return np.arange(n, dtype=int)

    t0, tr, ton, tf, tfw = map(float, x[:5])
    rise_end = t0 + tr
    fall_end = rise_end + ton + tf
    dcm_start = fall_end + tfw
    dummy = type(
        "_Timing",
        (),
        {
            "rise_end_s": rise_end,
            "fall_end_s": fall_end,
            "freewheel_end_s": dcm_start,
        },
    )()
    # 复用同样的分层抽样思想，但给最终线性系数更多点。
    parts = [_even_indices(0, n, min(50_000, max_points // 2))]
    dt = float(np.median(np.diff(time_s)))
    for center in (dummy.rise_end_s, dummy.fall_end_s):
        start = int(np.searchsorted(time_s, center - 0.1e-6, side="left"))
        stop = int(np.searchsorted(time_s, center + max(0.6e-6, 120.0 * dt), side="right"))
        parts.append(_even_indices(start, stop, min(20_000, max_points // 5)))
    start = int(np.searchsorted(time_s, dummy.freewheel_end_s, side="left"))
    parts.append(_even_indices(start, n, min(40_000, max_points // 3)))
    merged = np.unique(np.concatenate([part for part in parts if part.size]))
    if len(merged) > max_points:
        select = np.linspace(0, len(merged) - 1, max_points).astype(int)
        merged = merged[select]
    return merged.astype(int)


def _even_indices(start: int, stop: int, count: int) -> np.ndarray:
    start = max(0, int(start))
    stop = max(start, int(stop))
    length = stop - start
    if length <= 0 or count <= 0:
        return np.empty(0, dtype=int)
    if length <= count:
        return np.arange(start, stop, dtype=int)
    return np.unique(np.linspace(start, stop - 1, count).astype(int))


def _signed_amplitude_phase(cos_coeff: float, sin_coeff: float) -> tuple[float, float]:
    cos_coeff = float(cos_coeff)
    sin_coeff = float(sin_coeff)
    magnitude = float(np.hypot(cos_coeff, sin_coeff))
    phase = float(np.arctan2(-sin_coeff, cos_coeff))
    signed_amplitude = magnitude
    if phase > np.pi / 2.0:
        phase -= np.pi
        signed_amplitude = -magnitude
    elif phase < -np.pi / 2.0:
        phase += np.pi
        signed_amplitude = -magnitude
    return signed_amplitude, phase


def _robust_sigma(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    return 1.4826 * mad
