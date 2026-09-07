from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .waveform_quality import WaveformQualityReport, analyze_time_axis, require_fft_safe


@dataclass(frozen=True)
class WaveformData:
    time_s: np.ndarray
    voltage_v: np.ndarray
    quality: WaveformQualityReport
    source_path: Path
    rows_total: int
    rows_dropped: int

    @property
    def sample_rate_hz(self) -> float:
        return self.quality.sample_rate_hz

    @property
    def points(self) -> int:
        return len(self.time_s)


def load_waveform_csv_checked(
    path: str | Path,
    *,
    min_points: int = 32,
    require_named_columns: bool = False,
) -> WaveformData:
    """Load waveform CSV using the commercial time-axis quality policy.

    The time-axis report is calculated before sorting so an out-of-order export
    remains traceable as WARN. Duplicate timestamps or non-uniform/missing-sample
    patterns fail the shared FFT / Zero Span quality gate.
    """

    source_path = Path(path)
    frame = pd.read_csv(source_path)
    rows_total = len(frame)

    if {"time_s", "voltage_v"}.issubset(frame.columns):
        raw_time = pd.to_numeric(frame["time_s"], errors="coerce").to_numpy(float)
        raw_voltage = pd.to_numeric(frame["voltage_v"], errors="coerce").to_numpy(float)
    elif require_named_columns:
        missing = {"time_s", "voltage_v"} - set(frame.columns)
        raise ValueError(
            "CSV 缺少必要列：" + ", ".join(sorted(missing)) + "；需要 time_s, voltage_v"
        )
    elif len(frame.columns) >= 2:
        raw_time = pd.to_numeric(frame.iloc[:, 0], errors="coerce").to_numpy(float)
        raw_voltage = pd.to_numeric(frame.iloc[:, 1], errors="coerce").to_numpy(float)
    else:
        raise ValueError("waveform.csv 至少需要两列，推荐 time_s,voltage_v")

    finite = np.isfinite(raw_time) & np.isfinite(raw_voltage)
    time_s = raw_time[finite]
    voltage_v = raw_voltage[finite]
    rows_dropped = int(rows_total - len(time_s))

    if len(time_s) < int(min_points):
        raise ValueError(f"有效波形点数少于 {int(min_points)}")

    quality = analyze_time_axis(time_s)
    require_fft_safe(quality)

    order = np.argsort(time_s)
    time_s = np.asarray(time_s[order], dtype=float)
    voltage_v = np.asarray(voltage_v[order], dtype=float)

    return WaveformData(
        time_s=time_s,
        voltage_v=voltage_v,
        quality=quality,
        source_path=source_path,
        rows_total=rows_total,
        rows_dropped=rows_dropped,
    )
