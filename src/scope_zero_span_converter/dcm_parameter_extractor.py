from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


_MIN_POINTS = 64
_U10 = float(np.arccos(0.8) / np.pi)
_U90 = float(np.arccos(-0.8) / np.pi)
_HALF_COSINE_10_90_FACTOR = _U90 - _U10


@dataclass(frozen=True)
class DcmBasicExtractionResult:
    """DCM SW 基础参数提取结果。

    第一阶段只识别电平、主要时刻和边沿时间；尖峰、寄生振铃、DCM 谐振与
    噪声的精细拟合留给后续阶段。fitted_ideal_voltage_v 是根据当前提取结果重建的
    理想分段轨迹，residual_v 保留真实波形与该轨迹之间的残差。
    """

    sample_rate_hz: float
    total_duration_s: float
    baseline_voltage_v: float
    on_high_voltage_v: float
    freewheel_low_voltage_v: float
    switching_start_s: float
    rise_time_s: float
    on_time_s: float
    fall_time_s: float
    freewheel_time_s: float
    rise_time_10_90_s: float
    fall_time_10_90_s: float
    rise_end_s: float
    fall_start_s: float
    fall_end_s: float
    freewheel_end_s: float
    estimated_noise_rms_v: float
    confidence: dict[str, float]
    overall_confidence: float
    warnings: tuple[str, ...]
    fitted_ideal_voltage_v: np.ndarray
    residual_v: np.ndarray

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": "dcm_basic_parameter_extractor_v1",
            "sample_rate_hz": self.sample_rate_hz,
            "total_duration_s": self.total_duration_s,
            "levels": {
                "baseline_voltage_v": self.baseline_voltage_v,
                "on_high_voltage_v": self.on_high_voltage_v,
                "freewheel_low_voltage_v": self.freewheel_low_voltage_v,
            },
            "timing": {
                "switching_start_s": self.switching_start_s,
                "rise_time_s": self.rise_time_s,
                "rise_time_10_90_s": self.rise_time_10_90_s,
                "rise_end_s": self.rise_end_s,
                "on_time_s": self.on_time_s,
                "fall_start_s": self.fall_start_s,
                "fall_time_s": self.fall_time_s,
                "fall_time_10_90_s": self.fall_time_10_90_s,
                "fall_end_s": self.fall_end_s,
                "freewheel_time_s": self.freewheel_time_s,
                "freewheel_end_s": self.freewheel_end_s,
            },
            "estimated_noise_rms_v": self.estimated_noise_rms_v,
            "confidence": dict(self.confidence),
            "overall_confidence": self.overall_confidence,
            "warnings": list(self.warnings),
        }


def load_waveform_csv(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """只读取 time_s / voltage_v，不使用合成波形附带的任何真值列。"""

    path = Path(path)
    frame = pd.read_csv(path)
    required = {"time_s", "voltage_v"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(
            "CSV 缺少必要列：" + ", ".join(sorted(missing)) + "；需要 time_s, voltage_v"
        )
    time_s = frame["time_s"].to_numpy(dtype=float)
    voltage_v = frame["voltage_v"].to_numpy(dtype=float)
    _validate_waveform(time_s, voltage_v)
    return time_s, voltage_v


def extract_dcm_basic_parameters(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
) -> DcmBasicExtractionResult:
    """从单个 DCM SW 事件中提取第一阶段基础参数。

    方法概要：
    1. 长时间窗平滑后用 dV/dt 粗定位主上升沿和主下降沿；
    2. 在稳定区使用 median 估计基线、高电平、续流低电平；
    3. 在原始波形上寻找 10%/90% 穿越点，并按当前半余弦边沿定义反解完整边沿；
    4. 低通趋势用于定位续流结束 / DCM 断续区开始；
    5. 根据提取结果重建理想轨迹，残差留给后续尖峰/振铃拟合。

    当前假设 CSV 中包含一个主要 DCM 开关事件。多周期自动选择会在后续阶段加入。
    """

    t = np.asarray(time_s, dtype=float)
    v = np.asarray(voltage_v, dtype=float)
    _validate_waveform(t, v)

    n = len(t)
    dt = float(np.median(np.diff(t)))
    sample_rate_hz = 1.0 / dt
    total_duration_s = float(t[-1] - t[0])

    coarse_window = _odd(max(5, min(2001, int(round(n * 0.01)))))
    coarse = _moving_average(v, coarse_window)
    derivative = np.gradient(coarse, t)
    margin = max(coarse_window, int(0.01 * n))
    if n - 2 * margin < 16:
        margin = max(2, n // 20)

    seed_count = max(16, int(0.05 * n))
    baseline_seed = float(np.median(v[:seed_count]))
    interior = coarse[margin : n - margin] if n - margin > margin else coarse
    coarse_min = float(np.percentile(interior, 1.0))
    coarse_max = float(np.percentile(interior, 99.0))
    polarity = 1 if abs(coarse_max - baseline_seed) >= abs(baseline_seed - coarse_min) else -1

    valid = np.arange(margin, n - margin)
    if valid.size < 8:
        raise ValueError("有效波形区域过短，无法定位主要开关沿")

    if polarity > 0:
        rise_index = int(valid[np.argmax(derivative[valid])])
        after = _indices_after(rise_index, n, margin, coarse_window)
        fall_index = int(after[np.argmin(derivative[after])])
    else:
        rise_index = int(valid[np.argmin(derivative[valid])])
        after = _indices_after(rise_index, n, margin, coarse_window)
        fall_index = int(after[np.argmax(derivative[after])])

    if fall_index <= rise_index:
        raise ValueError("未能识别有效的上升沿→高电平→下降沿顺序")

    # 稳定电平：尽量远离边沿和初始尖峰。
    pre_end = max(8, rise_index - coarse_window // 2)
    pre_start = max(0, int(pre_end * 0.10))
    baseline_voltage_v = float(np.median(v[pre_start:pre_end]))

    high_span = max(10, fall_index - rise_index)
    high_start = rise_index + int(0.30 * high_span)
    high_end = rise_index + int(0.70 * high_span)
    on_high_voltage_v = float(np.median(v[high_start:high_end]))

    initial_low_start = min(n - 2, fall_index + max(5, coarse_window // 2))
    initial_low_end = min(n, initial_low_start + max(16, int(0.015 * n)))
    freewheel_low_voltage_v = float(np.median(v[initial_low_start:initial_low_end]))

    edge_search = max(coarse_window * 3, int(0.03 * n))

    rise_direction = 1 if on_high_voltage_v > baseline_voltage_v else -1
    rise_10 = _crossing_time(
        t,
        v,
        baseline_voltage_v + 0.10 * (on_high_voltage_v - baseline_voltage_v),
        rise_index - edge_search,
        rise_index + edge_search,
        rise_direction,
    )
    rise_90 = _crossing_time(
        t,
        v,
        baseline_voltage_v + 0.90 * (on_high_voltage_v - baseline_voltage_v),
        rise_index - edge_search,
        rise_index + edge_search,
        rise_direction,
    )
    if rise_10 is None or rise_90 is None or rise_90 < rise_10:
        raise ValueError("无法稳定找到上升沿 10%/90% 穿越点")

    rise_10_90_s = float(max(0.0, rise_90 - rise_10))
    rise_time_s = rise_10_90_s / _HALF_COSINE_10_90_FACTOR
    if rise_time_s <= 2.5 * dt:
        rise_time_s = 0.0
        switching_start_s = float(rise_10)
    else:
        switching_start_s = float(rise_10 - _U10 * rise_time_s)
    rise_end_s = switching_start_s + rise_time_s

    # 先用初始续流电平估计下降沿，再在定位续流结束后重新精修一次。
    fall_start_s, fall_time_s, fall_10_90_s = _extract_fall_edge(
        t,
        v,
        on_high_voltage_v,
        freewheel_low_voltage_v,
        fall_index,
        edge_search,
        dt,
    )
    fall_end_s = fall_start_s + fall_time_s

    # 用较长平均趋势抑制断续区振铃，寻找续流电平向基线回归的中点。
    trend_window = _odd(max(9, min(5001, int(round(n * 0.01)))))
    trend = _moving_average(v, trend_window)
    fall_end_index = int(np.searchsorted(t, fall_end_s))
    low_guard = max(3, int(0.002 * n))
    low_start = min(n - 2, fall_end_index + low_guard)
    low_end = min(n, low_start + max(16, int(0.01 * n)))
    freewheel_low_voltage_v = float(np.median(v[low_start:low_end]))

    freewheel_end_s, found_freewheel_end = _find_freewheel_end(
        t,
        trend,
        baseline_voltage_v,
        freewheel_low_voltage_v,
        low_end,
    )

    # 使用已经得到的续流区中部再次估计 Vlow，减少下降沿残留振铃的污染。
    freewheel_end_index = int(np.searchsorted(t, freewheel_end_s))
    if freewheel_end_index > fall_end_index + 20:
        middle_start = fall_end_index + int(0.20 * (freewheel_end_index - fall_end_index))
        middle_end = fall_end_index + int(0.65 * (freewheel_end_index - fall_end_index))
        if middle_end > middle_start + 5:
            freewheel_low_voltage_v = float(np.median(v[middle_start:middle_end]))

    fall_start_s, fall_time_s, fall_10_90_s = _extract_fall_edge(
        t,
        v,
        on_high_voltage_v,
        freewheel_low_voltage_v,
        fall_index,
        edge_search,
        dt,
    )
    fall_end_s = fall_start_s + fall_time_s

    # 精修后的 Vlow 再定位一次 t4。
    refined_search_start = int(np.searchsorted(t, fall_end_s)) + low_guard
    refined_end, refined_found = _find_freewheel_end(
        t,
        trend,
        baseline_voltage_v,
        freewheel_low_voltage_v,
        refined_search_start,
    )
    if refined_found:
        freewheel_end_s = refined_end
        found_freewheel_end = True

    on_time_s = max(0.0, fall_start_s - rise_end_s)
    freewheel_time_s = max(0.0, freewheel_end_s - fall_end_s)

    quiet = v[pre_start:pre_end]
    estimated_noise_rms_v = _robust_sigma(quiet)
    fitted_ideal = _build_fitted_ideal(
        t,
        baseline_voltage_v,
        on_high_voltage_v,
        freewheel_low_voltage_v,
        switching_start_s,
        rise_time_s,
        fall_start_s,
        fall_time_s,
        freewheel_end_s,
    )
    residual = v - fitted_ideal

    confidence, warnings = _build_confidence(
        baseline_voltage_v=baseline_voltage_v,
        high_voltage_v=on_high_voltage_v,
        low_voltage_v=freewheel_low_voltage_v,
        noise_rms_v=estimated_noise_rms_v,
        rise_time_s=rise_time_s,
        fall_time_s=fall_time_s,
        on_time_s=on_time_s,
        freewheel_time_s=freewheel_time_s,
        dt=dt,
        found_freewheel_end=found_freewheel_end,
    )
    overall = float(np.mean(list(confidence.values()))) if confidence else 0.0

    return DcmBasicExtractionResult(
        sample_rate_hz=sample_rate_hz,
        total_duration_s=total_duration_s,
        baseline_voltage_v=baseline_voltage_v,
        on_high_voltage_v=on_high_voltage_v,
        freewheel_low_voltage_v=freewheel_low_voltage_v,
        switching_start_s=switching_start_s,
        rise_time_s=rise_time_s,
        on_time_s=on_time_s,
        fall_time_s=fall_time_s,
        freewheel_time_s=freewheel_time_s,
        rise_time_10_90_s=rise_10_90_s,
        fall_time_10_90_s=fall_10_90_s,
        rise_end_s=rise_end_s,
        fall_start_s=fall_start_s,
        fall_end_s=fall_end_s,
        freewheel_end_s=freewheel_end_s,
        estimated_noise_rms_v=estimated_noise_rms_v,
        confidence=confidence,
        overall_confidence=overall,
        warnings=tuple(warnings),
        fitted_ideal_voltage_v=fitted_ideal,
        residual_v=residual,
    )


def _validate_waveform(time_s: np.ndarray, voltage_v: np.ndarray) -> None:
    if time_s.ndim != 1 or voltage_v.ndim != 1:
        raise ValueError("time_s 和 voltage_v 必须是一维数组")
    if len(time_s) != len(voltage_v):
        raise ValueError("time_s 和 voltage_v 点数不一致")
    if len(time_s) < _MIN_POINTS:
        raise ValueError(f"波形至少需要 {_MIN_POINTS} 个点")
    if not np.all(np.isfinite(time_s)) or not np.all(np.isfinite(voltage_v)):
        raise ValueError("波形包含 NaN 或 Inf")
    diff = np.diff(time_s)
    if np.any(diff <= 0):
        raise ValueError("time_s 必须严格递增")
    median_dt = float(np.median(diff))
    if median_dt <= 0:
        raise ValueError("无法确定有效采样间隔")
    # 第一阶段允许轻微非均匀时间轴，但明显不均匀需要先重采样。
    max_deviation = float(np.max(np.abs(diff - median_dt)))
    if max_deviation > median_dt * 0.05:
        raise ValueError("当前基础提取器要求近似等间隔 time_s；请先重采样")


def _odd(value: int) -> int:
    value = max(1, int(value))
    return value if value % 2 else value + 1


def _moving_average(values: np.ndarray, window: int) -> np.ndarray:
    window = _odd(window)
    if window <= 1:
        return values.astype(float, copy=True)
    pad = window // 2
    padded = np.pad(values, pad, mode="edge")
    kernel = np.ones(window, dtype=float) / window
    return np.convolve(padded, kernel, mode="valid")


def _indices_after(rise_index: int, n: int, margin: int, coarse_window: int) -> np.ndarray:
    min_separation = max(coarse_window, int(0.01 * n))
    start = min(n - margin - 1, rise_index + min_separation)
    indices = np.arange(start, n - margin)
    if indices.size < 8:
        raise ValueError("上升沿之后没有足够数据用于寻找下降沿")
    return indices


def _crossing_time(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    level_v: float,
    start_index: int,
    end_index: int,
    direction: int,
) -> float | None:
    start = max(0, int(start_index))
    end = min(len(voltage_v) - 1, int(end_index))
    if end <= start:
        return None
    segment = voltage_v[start : end + 1]
    if direction > 0:
        hits = np.where((segment[:-1] < level_v) & (segment[1:] >= level_v))[0]
    else:
        hits = np.where((segment[:-1] > level_v) & (segment[1:] <= level_v))[0]
    if hits.size == 0:
        return None
    index = start + int(hits[0])
    y0 = float(voltage_v[index])
    y1 = float(voltage_v[index + 1])
    if y1 == y0:
        return float(time_s[index])
    fraction = (level_v - y0) / (y1 - y0)
    return float(time_s[index] + fraction * (time_s[index + 1] - time_s[index]))


def _extract_fall_edge(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    high_v: float,
    low_v: float,
    fall_index: int,
    search_radius: int,
    dt: float,
) -> tuple[float, float, float]:
    direction = 1 if low_v > high_v else -1
    level_10 = high_v + 0.10 * (low_v - high_v)
    level_90 = high_v + 0.90 * (low_v - high_v)
    time_10 = _crossing_time(
        time_s,
        voltage_v,
        level_10,
        fall_index - search_radius,
        fall_index + search_radius,
        direction,
    )
    time_90 = _crossing_time(
        time_s,
        voltage_v,
        level_90,
        fall_index - search_radius,
        fall_index + search_radius,
        direction,
    )
    if time_10 is None or time_90 is None or time_90 < time_10:
        raise ValueError("无法稳定找到下降沿 10%/90% 穿越点")
    span_10_90 = float(max(0.0, time_90 - time_10))
    full_time = span_10_90 / _HALF_COSINE_10_90_FACTOR
    if full_time <= 2.5 * dt:
        full_time = 0.0
        start_time = float(time_10)
    else:
        start_time = float(time_10 - _U10 * full_time)
    return start_time, float(full_time), span_10_90


def _find_freewheel_end(
    time_s: np.ndarray,
    trend_voltage_v: np.ndarray,
    baseline_v: float,
    low_v: float,
    start_index: int,
) -> tuple[float, bool]:
    start = max(0, min(len(time_s) - 2, int(start_index)))
    midpoint = baseline_v + 0.5 * (low_v - baseline_v)
    segment = trend_voltage_v[start:]
    if low_v > baseline_v:
        hits = np.where((segment[:-1] > midpoint) & (segment[1:] <= midpoint))[0]
    else:
        hits = np.where((segment[:-1] < midpoint) & (segment[1:] >= midpoint))[0]
    if hits.size == 0:
        return float(time_s[-1]), False
    index = start + int(hits[0])
    y0 = float(trend_voltage_v[index])
    y1 = float(trend_voltage_v[index + 1])
    if y1 == y0:
        return float(time_s[index]), True
    fraction = (midpoint - y0) / (y1 - y0)
    crossing = time_s[index] + fraction * (time_s[index + 1] - time_s[index])
    return float(crossing), True


def _half_cosine_transition(
    time_s: np.ndarray,
    start_s: float,
    duration_s: float,
    start_v: float,
    end_v: float,
) -> np.ndarray:
    if duration_s <= 0:
        return np.where(time_s >= start_s, end_v, start_v)
    u = np.clip((time_s - start_s) / duration_s, 0.0, 1.0)
    return start_v + (end_v - start_v) * (0.5 - 0.5 * np.cos(np.pi * u))


def _build_fitted_ideal(
    time_s: np.ndarray,
    baseline_v: float,
    high_v: float,
    low_v: float,
    rise_start_s: float,
    rise_time_s: float,
    fall_start_s: float,
    fall_time_s: float,
    freewheel_end_s: float,
) -> np.ndarray:
    result = np.full(len(time_s), baseline_v, dtype=float)
    rise_end_s = rise_start_s + rise_time_s
    fall_end_s = fall_start_s + fall_time_s

    rise_mask = (time_s >= rise_start_s) & (time_s < rise_end_s)
    if np.any(rise_mask):
        result[rise_mask] = _half_cosine_transition(
            time_s[rise_mask], rise_start_s, rise_time_s, baseline_v, high_v
        )
    result[(time_s >= rise_end_s) & (time_s < fall_start_s)] = high_v

    fall_mask = (time_s >= fall_start_s) & (time_s < fall_end_s)
    if np.any(fall_mask):
        result[fall_mask] = _half_cosine_transition(
            time_s[fall_mask], fall_start_s, fall_time_s, high_v, low_v
        )
    result[(time_s >= fall_end_s) & (time_s < freewheel_end_s)] = low_v
    result[time_s >= freewheel_end_s] = baseline_v
    return result


def _robust_sigma(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    return 1.4826 * mad


def _snr_confidence(delta_v: float, noise_rms_v: float) -> float:
    noise = max(abs(noise_rms_v), 1e-12)
    snr = abs(delta_v) / noise
    return float(np.clip((snr - 3.0) / 17.0, 0.0, 1.0))


def _build_confidence(
    *,
    baseline_voltage_v: float,
    high_voltage_v: float,
    low_voltage_v: float,
    noise_rms_v: float,
    rise_time_s: float,
    fall_time_s: float,
    on_time_s: float,
    freewheel_time_s: float,
    dt: float,
    found_freewheel_end: bool,
) -> tuple[dict[str, float], list[str]]:
    main_level = _snr_confidence(high_voltage_v - baseline_voltage_v, noise_rms_v)
    low_level = _snr_confidence(low_voltage_v - baseline_voltage_v, noise_rms_v)
    edge_base = min(1.0, 0.55 + 0.45 * main_level)
    timing_base = min(main_level, 1.0 if on_time_s > 4 * dt else 0.35)
    freewheel_conf = low_level * (1.0 if found_freewheel_end else 0.25)

    confidence = {
        "baseline_voltage": max(main_level, 0.5),
        "on_high_voltage": main_level,
        "freewheel_low_voltage": low_level,
        "switching_start": edge_base,
        "rise_time": edge_base if rise_time_s > 0 else max(0.75, edge_base),
        "on_time": timing_base,
        "fall_time": edge_base if fall_time_s > 0 else max(0.75, edge_base),
        "freewheel_time": freewheel_conf,
    }
    confidence = {name: float(np.clip(value, 0.0, 1.0)) for name, value in confidence.items()}

    warnings: list[str] = []
    if main_level < 0.5:
        warnings.append("主高低电平相对于噪声的分离度较低，边沿与导通时间可信度可能下降。")
    if low_level < 0.5:
        warnings.append("续流低电平与基线较接近，续流结束点可能存在较大不确定性。")
    if not found_freewheel_end:
        warnings.append("未找到明确的续流结束 / DCM 断续区开始点，续流时间仅为保守估计。")
    if rise_time_s > 0 and rise_time_s < 5 * dt:
        warnings.append("上升沿采样点较少，上升时间受采样率限制。")
    if fall_time_s > 0 and fall_time_s < 5 * dt:
        warnings.append("下降沿采样点较少，下降时间受采样率限制。")
    return confidence, warnings
