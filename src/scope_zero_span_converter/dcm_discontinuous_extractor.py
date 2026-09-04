from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .dcm_parameter_extractor import DcmBasicExtractionResult
from .dcm_ringing_extractor import DcmRingingExtractionResult


@dataclass(frozen=True)
class DcmDiscontinuousExtractionResult:
    """第三阶段：DCM 断续区阻尼谐振与最终残差噪声估计。"""

    start_s: float
    end_s: float
    signed_initial_amplitude_v: float
    resonance_frequency_hz: float
    decay_rate_per_s: float
    phase_rad: float
    offset_v: float
    rmse_v: float
    r_squared: float
    confidence: float
    final_noise_rms_v: float
    final_residual_rmse_v: float
    warnings: tuple[str, ...]
    fitted_discontinuous_component_v: np.ndarray
    final_residual_v: np.ndarray

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": "dcm_discontinuous_resonance_extractor_v1",
            "start_s": self.start_s,
            "end_s": self.end_s,
            "signed_initial_amplitude_v": self.signed_initial_amplitude_v,
            "resonance_frequency_hz": self.resonance_frequency_hz,
            "decay_rate_per_s": self.decay_rate_per_s,
            "phase_rad": self.phase_rad,
            "offset_v": self.offset_v,
            "rmse_v": self.rmse_v,
            "r_squared": self.r_squared,
            "confidence": self.confidence,
            "final_noise_rms_v": self.final_noise_rms_v,
            "final_residual_rmse_v": self.final_residual_rmse_v,
            "warnings": list(self.warnings),
        }


def extract_dcm_discontinuous_resonance(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    basic: DcmBasicExtractionResult,
    ringing: DcmRingingExtractionResult | None = None,
) -> DcmDiscontinuousExtractionResult:
    """从逐阶段残差中反演 DCM 断续区谐振。

    输入仍然只来自 time_s、voltage_v 以及前两阶段由这两列数据得到的提取结果，
    不读取合成 CSV 的真值分量或参数 JSON。

    当前把第一阶段的 freewheel_end_s 作为断续区起点。局部模型采用：

        offset + A * exp(-alpha*t) * cos(2*pi*f*t + phase)

    phase 作为内部拟合参数，用于吸收起点定位和采样相位的轻微误差。
    """

    t = np.asarray(time_s, dtype=float)
    v = np.asarray(voltage_v, dtype=float)
    if t.ndim != 1 or v.ndim != 1 or len(t) != len(v):
        raise ValueError("time_s / voltage_v 必须是一维且点数一致")
    if len(t) != len(basic.residual_v):
        raise ValueError("基础提取结果与当前波形点数不一致")

    dt = float(np.median(np.diff(t)))
    fs = 1.0 / dt
    if ringing is not None:
        if len(ringing.residual_after_spike_v) != len(t):
            raise ValueError("尖峰/寄生振铃提取结果与当前波形点数不一致")
        staged_residual = np.asarray(ringing.residual_after_spike_v, dtype=float)
    else:
        staged_residual = np.asarray(basic.residual_v, dtype=float)

    start_s = float(basic.freewheel_end_s)
    start_index = int(np.searchsorted(t, start_s, side="left"))
    start_index = max(0, min(len(t) - 2, start_index))
    if len(t) - start_index < 64:
        raise ValueError("断续区有效数据少于 64 点，无法稳定拟合 DCM 谐振")

    local_t = t[start_index:] - start_s
    local_y = staged_residual[start_index:].astype(float, copy=True)
    duration = max(float(local_t[-1]), 1.0 / fs)
    noise = max(float(basic.estimated_noise_rms_v), 1e-12)

    initial_frequency = _estimate_frequency_fft(local_t, local_y, fs)
    nyquist = fs / 2.0
    min_resolvable = max(1.0 / duration, fs / max(len(local_t), 1))

    if initial_frequency <= 0:
        high = min(0.20 * nyquist, 20.0 / duration)
        if high <= min_resolvable:
            frequency_grid = np.array([0.0, min_resolvable], dtype=float)
        else:
            frequency_grid = np.concatenate(
                ([0.0], np.linspace(min_resolvable, high, 32))
            )
    else:
        low = max(min_resolvable, initial_frequency * 0.60)
        high = min(0.45 * fs, initial_frequency * 1.40)
        frequency_grid = np.linspace(low, high, 41)

    alpha_grid = _decay_grid(duration)
    best_f, best_alpha, best_coeff, best_sse = _grid_fit(
        local_t,
        local_y,
        frequency_grid,
        alpha_grid,
    )

    # 在粗搜索最优点附近再精修一次。
    f_half_width = max(best_f * 0.06, 0.75 / duration)
    fine_f = np.linspace(
        max(0.0, best_f - f_half_width),
        min(0.45 * fs, best_f + f_half_width),
        31,
    )
    alpha_half_width = max(best_alpha * 0.25, 0.5 / duration)
    fine_alpha = np.linspace(
        max(0.0, best_alpha - alpha_half_width),
        best_alpha + alpha_half_width,
        31,
    )
    refined = _grid_fit(local_t, local_y, fine_f, fine_alpha)
    if refined[-1] <= best_sse:
        best_f, best_alpha, best_coeff, best_sse = refined

    offset, cos_coeff, sin_coeff = (
        float(best_coeff[0]),
        float(best_coeff[1]),
        float(best_coeff[2]),
    )
    magnitude = float(np.hypot(cos_coeff, sin_coeff))
    phase = float(np.arctan2(-sin_coeff, cos_coeff))
    signed_amplitude = magnitude

    # 把相位折叠到 [-pi/2, pi/2]，额外的 pi 用幅度符号表达。
    if phase > np.pi / 2.0:
        phase -= np.pi
        signed_amplitude = -magnitude
    elif phase < -np.pi / 2.0:
        phase += np.pi
        signed_amplitude = -magnitude

    predicted_local = offset + _evaluate_local_component(
        local_t,
        signed_amplitude,
        phase,
        best_f,
        best_alpha,
    )
    error_local = local_y - predicted_local
    rmse = float(np.sqrt(np.mean(error_local**2)))
    centered = local_y - float(np.mean(local_y))
    denominator = float(np.dot(centered, centered))
    r_squared = 1.0 - float(np.dot(error_local, error_local)) / denominator if denominator > 1e-30 else 0.0
    r_squared = float(np.clip(r_squared, -1.0, 1.0))

    fitted_component = np.zeros_like(t, dtype=float)
    active = t >= start_s
    active_t = t[active] - start_s
    fitted_component[active] = _evaluate_local_component(
        active_t,
        signed_amplitude,
        phase,
        best_f,
        best_alpha,
    )

    final_residual = staged_residual - fitted_component
    # 用 robust sigma 估计“所有可解释分量扣除后”的噪声，降低少量边界残差的影响。
    final_noise_rms = _robust_sigma(final_residual)
    final_residual_rmse = float(np.sqrt(np.mean(final_residual**2)))

    snr = abs(signed_amplitude) / noise
    snr_score = float(np.clip((snr - 2.0) / 18.0, 0.0, 1.0))
    fit_score = float(np.clip((r_squared - 0.25) / 0.70, 0.0, 1.0))
    cycles = best_f * duration
    cycle_score = 1.0 if best_f <= 0 else float(np.clip(cycles / 5.0, 0.0, 1.0))
    confidence = float(np.clip(0.50 * fit_score + 0.30 * snr_score + 0.20 * cycle_score, 0.0, 1.0))

    warnings: list[str] = []
    if best_f > 0 and cycles < 2.0:
        warnings.append("DCM 断续区不足 2 个完整谐振周期，频率估计可信度有限")
    if confidence < 0.6:
        warnings.append("DCM 断续谐振拟合置信度偏低")
    if abs(signed_amplitude) < 3.0 * noise:
        warnings.append("DCM 断续谐振初始振幅接近底噪水平")
    if ringing is None:
        warnings.append("本次未先扣除开关沿寄生振铃，DCM 结果可能受到前级残差影响")

    return DcmDiscontinuousExtractionResult(
        start_s=start_s,
        end_s=float(t[-1]),
        signed_initial_amplitude_v=signed_amplitude,
        resonance_frequency_hz=float(best_f),
        decay_rate_per_s=float(best_alpha),
        phase_rad=phase,
        offset_v=offset,
        rmse_v=rmse,
        r_squared=r_squared,
        confidence=confidence,
        final_noise_rms_v=float(final_noise_rms),
        final_residual_rmse_v=final_residual_rmse,
        warnings=tuple(dict.fromkeys(warnings)),
        fitted_discontinuous_component_v=fitted_component,
        final_residual_v=final_residual,
    )


def _estimate_frequency_fft(local_t: np.ndarray, values: np.ndarray, sample_rate_hz: float) -> float:
    n = len(values)
    if n < 64:
        return 0.0
    duration = max(float(local_t[-1] - local_t[0]), 1.0 / sample_rate_hz)

    tail = values[-max(16, n // 8) :]
    centered = values - float(np.median(tail))

    # DCM 是“从窗口起点最强、随后衰减”的瞬态，因此不能使用两端都归零的 Hann。
    # 这里只对末端约 15% 做余弦渐消，保留起始幅值用于频率估计。
    taper = np.ones(n, dtype=float)
    taper_points = max(8, int(round(0.15 * n)))
    if taper_points < n:
        x = np.linspace(0.0, np.pi / 2.0, taper_points)
        taper[-taper_points:] = np.cos(x) ** 2

    # 零填充提升粗频率栅格分辨率；真实精度仍由后续时域联合拟合决定。
    fft_points = 1
    target = max(n * 4, 256)
    while fft_points < target:
        fft_points *= 2
    spectrum = np.abs(np.fft.rfft(centered * taper, n=fft_points))
    freqs = np.fft.rfftfreq(fft_points, d=1.0 / sample_rate_hz)

    min_frequency = max(1.0 / duration, sample_rate_hz / fft_points)
    valid = (freqs >= min_frequency) & (freqs <= 0.45 * sample_rate_hz)
    if not np.any(valid):
        return 0.0
    indices = np.where(valid)[0]
    peak_index = int(indices[np.argmax(spectrum[indices])])
    if peak_index <= 0 or spectrum[peak_index] <= 0:
        return 0.0

    if 0 < peak_index < len(spectrum) - 1:
        y0 = float(spectrum[peak_index - 1])
        y1 = float(spectrum[peak_index])
        y2 = float(spectrum[peak_index + 1])
        denominator = y0 - 2.0 * y1 + y2
        if abs(denominator) > 1e-30:
            delta = float(np.clip(0.5 * (y0 - y2) / denominator, -0.5, 0.5))
            return float(freqs[peak_index] + delta * (freqs[1] - freqs[0]))
    return float(freqs[peak_index])


def _decay_grid(duration_s: float) -> np.ndarray:
    duration = max(duration_s, 1e-12)
    positive = np.geomspace(0.08 / duration, 120.0 / duration, 36)
    return np.concatenate(([0.0], positive))


def _grid_fit(
    local_t: np.ndarray,
    values: np.ndarray,
    frequency_grid: np.ndarray,
    alpha_grid: np.ndarray,
) -> tuple[float, float, np.ndarray, float]:
    best: tuple[float, float, np.ndarray, float] | None = None
    for frequency in frequency_grid:
        omega = 2.0 * np.pi * float(frequency)
        for alpha in alpha_grid:
            coeff, sse = _fit_linear_components(local_t, values, omega, float(alpha))
            if best is None or sse < best[-1]:
                best = (float(frequency), float(alpha), coeff, float(sse))
    if best is None:
        raise ValueError("DCM 断续谐振拟合失败")
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


def _evaluate_local_component(
    local_t: np.ndarray,
    signed_amplitude_v: float,
    phase_rad: float,
    frequency_hz: float,
    decay_rate_per_s: float,
) -> np.ndarray:
    return (
        signed_amplitude_v
        * np.exp(-decay_rate_per_s * local_t)
        * np.cos(2.0 * np.pi * frequency_hz * local_t + phase_rad)
    )


def _robust_sigma(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    return 1.4826 * mad
