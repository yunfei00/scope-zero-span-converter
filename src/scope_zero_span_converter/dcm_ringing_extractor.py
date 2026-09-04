from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .dcm_parameter_extractor import DcmBasicExtractionResult


@dataclass(frozen=True)
class DampedRingingEdgeFit:
    """单个开关沿局部阻尼振铃拟合结果。"""

    start_s: float
    end_s: float
    signed_initial_amplitude_v: float
    phase_rad: float
    offset_v: float
    rmse_v: float
    r_squared: float
    confidence: float
    points: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_s": self.start_s,
            "end_s": self.end_s,
            "signed_initial_amplitude_v": self.signed_initial_amplitude_v,
            "phase_rad": self.phase_rad,
            "offset_v": self.offset_v,
            "rmse_v": self.rmse_v,
            "r_squared": self.r_squared,
            "confidence": self.confidence,
            "points": self.points,
        }


@dataclass(frozen=True)
class DcmRingingExtractionResult:
    """第二阶段：上/下降沿尖峰及共享寄生振铃参数。"""

    ringing_frequency_hz: float
    decay_rate_per_s: float
    rise: DampedRingingEdgeFit
    fall: DampedRingingEdgeFit
    overall_confidence: float
    warnings: tuple[str, ...]
    fitted_spike_component_v: np.ndarray
    residual_after_spike_v: np.ndarray

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": "dcm_edge_ringing_extractor_v1",
            "shared_ringing": {
                "frequency_hz": self.ringing_frequency_hz,
                "decay_rate_per_s": self.decay_rate_per_s,
            },
            "rise_edge": self.rise.to_dict(),
            "fall_edge": self.fall.to_dict(),
            "overall_confidence": self.overall_confidence,
            "warnings": list(self.warnings),
        }


def extract_dcm_edge_ringing(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    basic: DcmBasicExtractionResult,
) -> DcmRingingExtractionResult:
    """从基础理想轨迹残差中反演上下沿尖峰与寄生振铃。

    当前模型假设两个开关沿共享寄生振铃频率和指数衰减率，但分别具有独立的
    有符号初始幅度和相位。相位作为内部拟合参数，用于吸收实际 CSV 中边界定位、
    采样相位和真实寄生网络造成的相位差。

    算法只使用 time_s、voltage_v 以及第一阶段从这两列数据得到的 basic 结果，
    不读取任何合成真值列或参数 JSON。
    """

    t = np.asarray(time_s, dtype=float)
    v = np.asarray(voltage_v, dtype=float)
    if t.ndim != 1 or v.ndim != 1 or len(t) != len(v):
        raise ValueError("time_s / voltage_v 必须是一维且点数一致")
    if len(t) != len(basic.residual_v):
        raise ValueError("基础提取结果与当前波形点数不一致")

    dt = float(np.median(np.diff(t)))
    fs = 1.0 / dt
    residual = np.asarray(basic.residual_v, dtype=float)

    rise_t, rise_y = _extract_edge_window(
        t,
        residual,
        start_s=basic.rise_end_s,
        stop_limit_s=basic.fall_start_s,
        section_duration_s=basic.on_time_s,
        dt=dt,
    )
    fall_t, fall_y = _extract_edge_window(
        t,
        residual,
        start_s=basic.fall_end_s,
        stop_limit_s=basic.freewheel_end_s,
        section_duration_s=basic.freewheel_time_s,
        dt=dt,
    )

    noise = max(float(basic.estimated_noise_rms_v), 1e-12)
    rise_strength = _early_signal_strength(rise_y, noise)
    fall_strength = _early_signal_strength(fall_y, noise)

    f_candidates: list[tuple[float, float]] = []
    for local_t, local_y, strength in (
        (rise_t, rise_y, rise_strength),
        (fall_t, fall_y, fall_strength),
    ):
        estimate = _estimate_frequency_fft(local_t, local_y, fs)
        if estimate > 0 and strength > 1.5:
            f_candidates.append((estimate, strength))

    if f_candidates:
        numerator = sum(value * weight for value, weight in f_candidates)
        denominator = sum(weight for _, weight in f_candidates)
        initial_frequency = numerator / max(denominator, 1e-12)
    else:
        initial_frequency = 0.0

    duration = max(float(rise_t[-1]), float(fall_t[-1]), 20.0 * dt)
    nyquist = fs / 2.0
    min_resolvable = max(1.0 / duration, fs / max(len(t), 1))

    if initial_frequency <= 0:
        # 没有明显周期峰时仍保留 0 Hz（纯指数瞬态）候选，并给一个低频搜索区。
        frequency_grid = np.concatenate(
            ([0.0], np.linspace(min_resolvable, min(0.20 * nyquist, 20.0 / duration), 24))
        )
    else:
        low = max(min_resolvable, initial_frequency * 0.65)
        high = min(0.45 * fs, initial_frequency * 1.35)
        frequency_grid = np.linspace(low, high, 31)

    alpha_grid = _decay_grid(duration)
    best_frequency, best_alpha, rise_coeff, fall_coeff, best_sse = _joint_grid_fit(
        rise_t,
        rise_y,
        fall_t,
        fall_y,
        frequency_grid,
        alpha_grid,
    )

    # 第二轮在粗搜索最优点附近做局部精修。
    f_half_width = max(best_frequency * 0.05, 0.75 / duration)
    f_low = max(0.0, best_frequency - f_half_width)
    f_high = min(0.45 * fs, best_frequency + f_half_width)
    fine_f = np.linspace(f_low, f_high, 25)

    alpha_half_width = max(best_alpha * 0.20, 0.5 / duration)
    a_low = max(0.0, best_alpha - alpha_half_width)
    a_high = best_alpha + alpha_half_width
    fine_a = np.linspace(a_low, a_high, 25)

    refined = _joint_grid_fit(
        rise_t,
        rise_y,
        fall_t,
        fall_y,
        fine_f,
        fine_a,
    )
    if refined[-1] <= best_sse:
        best_frequency, best_alpha, rise_coeff, fall_coeff, best_sse = refined

    rise_fit = _edge_fit_result(
        rise_t,
        rise_y,
        rise_coeff,
        frequency_hz=best_frequency,
        decay_rate_per_s=best_alpha,
        absolute_start_s=basic.rise_end_s,
        noise_rms_v=noise,
    )
    fall_fit = _edge_fit_result(
        fall_t,
        fall_y,
        fall_coeff,
        frequency_hz=best_frequency,
        decay_rate_per_s=best_alpha,
        absolute_start_s=basic.fall_end_s,
        noise_rms_v=noise,
    )

    fitted_spike = np.zeros_like(t, dtype=float)
    fitted_spike += _evaluate_edge_component(
        t,
        basic.rise_end_s,
        rise_fit.signed_initial_amplitude_v,
        rise_fit.phase_rad,
        best_frequency,
        best_alpha,
    )
    fitted_spike += _evaluate_edge_component(
        t,
        basic.fall_end_s,
        fall_fit.signed_initial_amplitude_v,
        fall_fit.phase_rad,
        best_frequency,
        best_alpha,
    )

    residual_after = residual - fitted_spike
    overall = float(np.mean([rise_fit.confidence, fall_fit.confidence]))
    warnings: list[str] = []

    if best_frequency > 0:
        rise_cycles = best_frequency * max(float(rise_t[-1]), 0.0)
        fall_cycles = best_frequency * max(float(fall_t[-1]), 0.0)
        if min(rise_cycles, fall_cycles) < 2.0:
            warnings.append("至少一个开关沿窗口内不足 2 个完整振铃周期，频率估计可信度有限")
    if rise_fit.confidence < 0.6:
        warnings.append("上升沿尖峰/振铃拟合置信度偏低")
    if fall_fit.confidence < 0.6:
        warnings.append("下降沿尖峰/振铃拟合置信度偏低")
    if abs(rise_fit.signed_initial_amplitude_v) < 3.0 * noise:
        warnings.append("上升沿尖峰接近底噪水平")
    if abs(fall_fit.signed_initial_amplitude_v) < 3.0 * noise:
        warnings.append("下降沿尖峰接近底噪水平")

    return DcmRingingExtractionResult(
        ringing_frequency_hz=float(best_frequency),
        decay_rate_per_s=float(best_alpha),
        rise=rise_fit,
        fall=fall_fit,
        overall_confidence=overall,
        warnings=tuple(dict.fromkeys(warnings)),
        fitted_spike_component_v=fitted_spike,
        residual_after_spike_v=residual_after,
    )


def _extract_edge_window(
    time_s: np.ndarray,
    residual_v: np.ndarray,
    *,
    start_s: float,
    stop_limit_s: float,
    section_duration_s: float,
    dt: float,
) -> tuple[np.ndarray, np.ndarray]:
    if stop_limit_s <= start_s:
        raise ValueError("开关沿之后没有足够稳定区用于尖峰/振铃拟合")

    # 上限 1.5 us；尽量使用所在稳定区的 45%，避免碰到下一个主事件。
    desired = min(1.5e-6, max(80.0 * dt, 0.45 * max(section_duration_s, 0.0)))
    end_s = min(stop_limit_s - 4.0 * dt, start_s + desired)
    if end_s <= start_s + 16.0 * dt:
        end_s = stop_limit_s - 2.0 * dt

    start_index = max(0, int(np.searchsorted(time_s, start_s, side="left")))
    end_index = min(len(time_s), int(np.searchsorted(time_s, end_s, side="right")))
    if end_index - start_index < 32:
        raise ValueError("尖峰/振铃局部窗口少于 32 点，无法稳定拟合")

    local_t = time_s[start_index:end_index] - start_s
    local_y = residual_v[start_index:end_index].astype(float, copy=True)
    return local_t, local_y


def _early_signal_strength(values: np.ndarray, noise_rms_v: float) -> float:
    count = max(8, min(len(values), len(values) // 6))
    early = values[:count]
    robust_peak = float(np.percentile(np.abs(early - np.median(early)), 95.0))
    return robust_peak / max(noise_rms_v, 1e-12)


def _estimate_frequency_fft(local_t: np.ndarray, values: np.ndarray, sample_rate_hz: float) -> float:
    n = len(values)
    if n < 32:
        return 0.0
    duration = max(float(local_t[-1] - local_t[0]), 1.0 / sample_rate_hz)
    centered = values - float(np.median(values[-max(8, n // 5) :]))
    window = np.hanning(n)
    spectrum = np.abs(np.fft.rfft(centered * window))
    freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate_hz)

    min_frequency = max(1.0 / duration, sample_rate_hz / n)
    valid = (freqs >= min_frequency) & (freqs <= 0.45 * sample_rate_hz)
    if not np.any(valid):
        return 0.0
    indices = np.where(valid)[0]
    peak_index = int(indices[np.argmax(spectrum[indices])])
    if peak_index <= 0 or spectrum[peak_index] <= 0:
        return 0.0

    # 对 FFT 峰做三点抛物线插值，降低频率栅格误差。
    if 0 < peak_index < len(spectrum) - 1:
        y0, y1, y2 = (float(spectrum[peak_index - 1]), float(spectrum[peak_index]), float(spectrum[peak_index + 1]))
        denominator = y0 - 2.0 * y1 + y2
        if abs(denominator) > 1e-30:
            delta = 0.5 * (y0 - y2) / denominator
            delta = float(np.clip(delta, -0.5, 0.5))
            bin_width = freqs[1] - freqs[0]
            return float(freqs[peak_index] + delta * bin_width)
    return float(freqs[peak_index])


def _decay_grid(duration_s: float) -> np.ndarray:
    duration = max(duration_s, 1e-12)
    positive = np.geomspace(0.15 / duration, 100.0 / duration, 30)
    return np.concatenate(([0.0], positive))


def _joint_grid_fit(
    rise_t: np.ndarray,
    rise_y: np.ndarray,
    fall_t: np.ndarray,
    fall_y: np.ndarray,
    frequency_grid: np.ndarray,
    alpha_grid: np.ndarray,
) -> tuple[float, float, np.ndarray, np.ndarray, float]:
    best: tuple[float, float, np.ndarray, np.ndarray, float] | None = None
    for frequency in frequency_grid:
        omega = 2.0 * np.pi * float(frequency)
        for alpha in alpha_grid:
            rise_coeff, rise_sse = _fit_linear_components(rise_t, rise_y, omega, float(alpha))
            fall_coeff, fall_sse = _fit_linear_components(fall_t, fall_y, omega, float(alpha))
            total = rise_sse + fall_sse
            if best is None or total < best[-1]:
                best = (float(frequency), float(alpha), rise_coeff, fall_coeff, float(total))
    if best is None:
        raise ValueError("寄生振铃联合拟合失败")
    return best


def _fit_linear_components(
    local_t: np.ndarray,
    values: np.ndarray,
    omega: float,
    alpha: float,
) -> tuple[np.ndarray, float]:
    envelope = np.exp(-alpha * local_t)
    cosine = envelope * np.cos(omega * local_t)
    sine = envelope * np.sin(omega * local_t)
    matrix = np.column_stack((np.ones(len(local_t)), cosine, sine))
    coeff, *_ = np.linalg.lstsq(matrix, values, rcond=None)
    residual = values - matrix @ coeff
    return coeff, float(np.dot(residual, residual))


def _edge_fit_result(
    local_t: np.ndarray,
    values: np.ndarray,
    coeff: np.ndarray,
    *,
    frequency_hz: float,
    decay_rate_per_s: float,
    absolute_start_s: float,
    noise_rms_v: float,
) -> DampedRingingEdgeFit:
    offset, cos_coeff, sin_coeff = (float(coeff[0]), float(coeff[1]), float(coeff[2]))
    magnitude = float(np.hypot(cos_coeff, sin_coeff))
    phase = float(np.arctan2(-sin_coeff, cos_coeff))
    signed_amplitude = magnitude

    # 把相位折叠到 [-pi/2, pi/2]，多出来的 pi 由幅度符号承担。
    if phase > np.pi / 2.0:
        phase -= np.pi
        signed_amplitude = -magnitude
    elif phase < -np.pi / 2.0:
        phase += np.pi
        signed_amplitude = -magnitude

    omega = 2.0 * np.pi * frequency_hz
    envelope = np.exp(-decay_rate_per_s * local_t)
    predicted = offset + signed_amplitude * envelope * np.cos(omega * local_t + phase)
    error = values - predicted
    rmse = float(np.sqrt(np.mean(error**2)))
    centered = values - float(np.mean(values))
    denom = float(np.dot(centered, centered))
    r_squared = 1.0 - float(np.dot(error, error)) / denom if denom > 1e-30 else 0.0
    r_squared = float(np.clip(r_squared, -1.0, 1.0))

    snr = abs(signed_amplitude) / max(noise_rms_v, 1e-12)
    snr_score = float(np.clip((snr - 2.0) / 18.0, 0.0, 1.0))
    fit_score = float(np.clip((r_squared - 0.25) / 0.70, 0.0, 1.0))
    cycles = frequency_hz * max(float(local_t[-1]), 0.0)
    cycle_score = 1.0 if frequency_hz <= 0 else float(np.clip(cycles / 4.0, 0.0, 1.0))
    confidence = 0.45 * fit_score + 0.35 * snr_score + 0.20 * cycle_score

    return DampedRingingEdgeFit(
        start_s=float(absolute_start_s),
        end_s=float(absolute_start_s + local_t[-1]),
        signed_initial_amplitude_v=signed_amplitude,
        phase_rad=phase,
        offset_v=offset,
        rmse_v=rmse,
        r_squared=r_squared,
        confidence=float(np.clip(confidence, 0.0, 1.0)),
        points=len(local_t),
    )


def _evaluate_edge_component(
    time_s: np.ndarray,
    start_s: float,
    signed_amplitude_v: float,
    phase_rad: float,
    frequency_hz: float,
    decay_rate_per_s: float,
) -> np.ndarray:
    result = np.zeros_like(time_s, dtype=float)
    active = time_s >= start_s
    if not np.any(active) or signed_amplitude_v == 0:
        return result
    local_t = time_s[active] - start_s
    result[active] = (
        signed_amplitude_v
        * np.exp(-decay_rate_per_s * local_t)
        * np.cos(2.0 * np.pi * frequency_hz * local_t + phase_rad)
    )
    return result
