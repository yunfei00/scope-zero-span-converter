from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np


def waveform_signature(time_s: np.ndarray, voltage_v: np.ndarray) -> str:
    """Return a deterministic identity for one exact sampled waveform.

    This is an analysis-consistency key rather than a security primitive.  The
    byte order and dtype are normalized so equivalent arrays have the same
    identity on Windows and Linux, while a voltage-only change is still caught.
    """

    time = np.ascontiguousarray(np.asarray(time_s, dtype="<f8"))
    voltage = np.ascontiguousarray(np.asarray(voltage_v, dtype="<f8"))
    if time.ndim != 1 or voltage.ndim != 1 or len(time) != len(voltage):
        raise ValueError("time_s / voltage_v 必须是一维且点数一致")

    digest = hashlib.blake2b(digest_size=16)
    digest.update(memoryview(time).cast("B"))
    digest.update(memoryview(voltage).cast("B"))
    return digest.hexdigest()


@dataclass(frozen=True)
class WaveformQualityReport:
    points: int
    time_start_s: float
    time_end_s: float
    duration_s: float
    median_dt_s: float
    sample_rate_hz: float
    nyquist_hz: float
    duplicate_timestamps: int
    nonmonotonic_steps: int
    max_dt_deviation_fraction: float
    rms_dt_deviation_fraction: float
    max_gap_ratio: float
    fft_safe: bool
    status: str
    message: str

    def summary(self) -> str:
        jitter_pct = self.max_dt_deviation_fraction * 100.0
        return (
            f"{self.points} 点 | Fs={self.sample_rate_hz/1e6:.6g} MSa/s | "
            f"时长={self.duration_s*1e6:.6g} µs | "
            f"dt最大偏差={jitter_pct:.6g}% | {self.status.upper()}"
        )


def analyze_time_axis(
    time_s: np.ndarray,
    *,
    fail_uniformity_fraction: float = 0.01,
) -> WaveformQualityReport:
    """Inspect whether a time axis is trustworthy for FFT / digital downconversion.

    ``fail_uniformity_fraction`` is the allowed maximum relative deviation from
    the median sample interval. 1% is deliberately tolerant of CSV floating
    formatting while still rejecting visibly non-uniform sampling/gaps.
    """

    t = np.asarray(time_s, dtype=float)
    t = t[np.isfinite(t)]
    if len(t) < 2:
        return WaveformQualityReport(
            points=len(t),
            time_start_s=float(t[0]) if len(t) else float("nan"),
            time_end_s=float(t[-1]) if len(t) else float("nan"),
            duration_s=0.0,
            median_dt_s=float("nan"),
            sample_rate_hz=float("nan"),
            nyquist_hz=float("nan"),
            duplicate_timestamps=0,
            nonmonotonic_steps=0,
            max_dt_deviation_fraction=float("inf"),
            rms_dt_deviation_fraction=float("inf"),
            max_gap_ratio=float("inf"),
            fft_safe=False,
            status="fail",
            message="有效时间点少于 2",
        )

    original_dt = np.diff(t)
    nonmonotonic_steps = int(np.count_nonzero(original_dt < 0))

    sorted_t = np.sort(t)
    duplicate_timestamps = int(len(sorted_t) - len(np.unique(sorted_t)))
    dt = np.diff(sorted_t)
    positive_dt = dt[dt > 0]

    if len(positive_dt) == 0:
        return WaveformQualityReport(
            points=len(t),
            time_start_s=float(sorted_t[0]),
            time_end_s=float(sorted_t[-1]),
            duration_s=float(sorted_t[-1] - sorted_t[0]),
            median_dt_s=float("nan"),
            sample_rate_hz=float("nan"),
            nyquist_hz=float("nan"),
            duplicate_timestamps=duplicate_timestamps,
            nonmonotonic_steps=nonmonotonic_steps,
            max_dt_deviation_fraction=float("inf"),
            rms_dt_deviation_fraction=float("inf"),
            max_gap_ratio=float("inf"),
            fft_safe=False,
            status="fail",
            message="无法得到有效正采样间隔",
        )

    median_dt = float(np.median(positive_dt))
    sample_rate_hz = 1.0 / median_dt
    deviations = np.abs(positive_dt - median_dt) / median_dt
    max_dev = float(np.max(deviations)) if len(deviations) else 0.0
    rms_dev = float(np.sqrt(np.mean(deviations**2))) if len(deviations) else 0.0
    max_gap_ratio = float(np.max(positive_dt) / median_dt)

    reasons: list[str] = []
    if duplicate_timestamps:
        reasons.append(f"存在 {duplicate_timestamps} 个重复时间戳")
    if max_dev > fail_uniformity_fraction:
        reasons.append(
            f"采样间隔最大偏差 {max_dev*100:.6g}% 超过允许值 "
            f"{fail_uniformity_fraction*100:.6g}%"
        )

    fft_safe = not reasons
    status = "pass" if fft_safe else "fail"
    if fft_safe:
        message = "时间轴满足当前 FFT / Zero Span 均匀采样要求"
        if nonmonotonic_steps:
            status = "warn"
            message = (
                f"原始 CSV 有 {nonmonotonic_steps} 处时间倒序；排序后时间轴均匀，"
                "当前可以计算，但建议检查数据导出顺序"
            )
    else:
        message = "；".join(reasons)

    return WaveformQualityReport(
        points=len(t),
        time_start_s=float(sorted_t[0]),
        time_end_s=float(sorted_t[-1]),
        duration_s=float(sorted_t[-1] - sorted_t[0]),
        median_dt_s=median_dt,
        sample_rate_hz=sample_rate_hz,
        nyquist_hz=sample_rate_hz / 2.0,
        duplicate_timestamps=duplicate_timestamps,
        nonmonotonic_steps=nonmonotonic_steps,
        max_dt_deviation_fraction=max_dev,
        rms_dt_deviation_fraction=rms_dev,
        max_gap_ratio=max_gap_ratio,
        fft_safe=fft_safe,
        status=status,
        message=message,
    )


def require_fft_safe(report: WaveformQualityReport) -> None:
    if report.fft_safe:
        return
    raise ValueError(
        "波形时间轴不适合 FFT / Zero Span："
        f"{report.message}。请检查 CSV 是否存在重复时间、缺点或非均匀采样。"
    )
