from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TimeMarker:
    """One DCM time-domain marker snapped to an actual waveform sample."""

    index: int
    time_s: float
    voltage_v: float


@dataclass(frozen=True)
class TimeMarkerDelta:
    """Difference from marker A to marker B."""

    delta_time_s: float
    delta_voltage_v: float


def time_marker_at_time(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    target_time_s: float,
) -> TimeMarker:
    """Return the waveform sample nearest to ``target_time_s``.

    Marker readout is intentionally sample-based rather than interpolated so
    customers can trace the displayed value back to one real CSV/generator point.
    """

    t = np.asarray(time_s, dtype=float)
    v = np.asarray(voltage_v, dtype=float)
    if t.ndim != 1 or v.ndim != 1 or len(t) != len(v) or len(t) == 0:
        raise ValueError("时域 Marker 需要非空且等长的一维 time_s / voltage_v")
    if not np.all(np.isfinite(t)) or not np.all(np.isfinite(v)):
        raise ValueError("时域 Marker 输入包含 NaN 或 Inf")
    if not np.isfinite(target_time_s):
        raise ValueError("Marker 时间必须为有限值")

    index = int(np.argmin(np.abs(t - float(target_time_s))))
    return TimeMarker(
        index=index,
        time_s=float(t[index]),
        voltage_v=float(v[index]),
    )


def time_marker_delta(marker_a: TimeMarker, marker_b: TimeMarker) -> TimeMarkerDelta:
    return TimeMarkerDelta(
        delta_time_s=float(marker_b.time_s - marker_a.time_s),
        delta_voltage_v=float(marker_b.voltage_v - marker_a.voltage_v),
    )
