from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class ComparisonResult:
    time_s: np.ndarray
    reconstructed_dbm: np.ndarray
    reference_dbm: np.ndarray
    error_db: np.ndarray
    mae_db: float
    rmse_db: float
    bias_db: float
    max_abs_error_db: float
    correlation: float | None
    points: int


def load_fsw_zero_span_csv(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """读取 FSW Zero Span CSV。

    标准格式为 ``time_s, amplitude_dbm``。为了兼容客户已有文件，
    amplitude 列也接受 ``level_dbm`` / ``power_dbm``。
    """

    df = pd.read_csv(path)
    if "time_s" not in df.columns:
        raise ValueError("FSW Zero Span CSV 缺少 time_s 列")

    amplitude_column = None
    for name in ("amplitude_dbm", "level_dbm", "power_dbm"):
        if name in df.columns:
            amplitude_column = name
            break
    if amplitude_column is None:
        raise ValueError(
            "FSW Zero Span CSV 缺少 amplitude_dbm 列"
            "（也兼容 level_dbm / power_dbm）"
        )

    time_s = pd.to_numeric(df["time_s"], errors="coerce").to_numpy(float)
    amplitude_dbm = pd.to_numeric(
        df[amplitude_column], errors="coerce"
    ).to_numpy(float)

    mask = np.isfinite(time_s) & np.isfinite(amplitude_dbm)
    time_s = time_s[mask]
    amplitude_dbm = amplitude_dbm[mask]

    if len(time_s) < 2:
        raise ValueError("FSW Zero Span CSV 有效点数少于 2")

    order = np.argsort(time_s)
    time_s = time_s[order]
    amplitude_dbm = amplitude_dbm[order]

    # 重复时间点只保留第一次，避免 np.interp 出现不明确行为。
    unique_time, unique_indices = np.unique(time_s, return_index=True)
    return unique_time, amplitude_dbm[unique_indices]


def compare_zero_span(
    reconstructed_time_s: np.ndarray,
    reconstructed_dbm: np.ndarray,
    reference_time_s: np.ndarray,
    reference_dbm: np.ndarray,
) -> ComparisonResult:
    """在两条曲线共同时间范围内进行对齐和误差计算。"""

    reconstructed_time_s = np.asarray(reconstructed_time_s, dtype=float)
    reconstructed_dbm = np.asarray(reconstructed_dbm, dtype=float)
    reference_time_s = np.asarray(reference_time_s, dtype=float)
    reference_dbm = np.asarray(reference_dbm, dtype=float)

    if len(reconstructed_time_s) != len(reconstructed_dbm):
        raise ValueError("恢复曲线 time/amplitude 长度不一致")
    if len(reference_time_s) != len(reference_dbm):
        raise ValueError("FSW 参考曲线 time/amplitude 长度不一致")

    overlap_start = max(float(reconstructed_time_s[0]), float(reference_time_s[0]))
    overlap_stop = min(float(reconstructed_time_s[-1]), float(reference_time_s[-1]))
    if overlap_stop <= overlap_start:
        raise ValueError("恢复曲线与 FSW 参考曲线没有共同时间范围")

    mask = (
        np.isfinite(reconstructed_time_s)
        & np.isfinite(reconstructed_dbm)
        & (reconstructed_time_s >= overlap_start)
        & (reconstructed_time_s <= overlap_stop)
    )
    aligned_time = reconstructed_time_s[mask]
    aligned_reconstructed = reconstructed_dbm[mask]
    if len(aligned_time) < 2:
        raise ValueError("两条曲线共同时间范围内有效点数少于 2")

    aligned_reference = np.interp(
        aligned_time,
        reference_time_s,
        reference_dbm,
    )
    error_db = aligned_reconstructed - aligned_reference

    mae_db = float(np.mean(np.abs(error_db)))
    rmse_db = float(np.sqrt(np.mean(error_db**2)))
    bias_db = float(np.mean(error_db))
    max_abs_error_db = float(np.max(np.abs(error_db)))

    correlation: float | None
    if (
        len(aligned_reconstructed) >= 2
        and float(np.std(aligned_reconstructed)) > 0
        and float(np.std(aligned_reference)) > 0
    ):
        correlation = float(
            np.corrcoef(aligned_reconstructed, aligned_reference)[0, 1]
        )
    else:
        correlation = None

    return ComparisonResult(
        time_s=aligned_time,
        reconstructed_dbm=aligned_reconstructed,
        reference_dbm=aligned_reference,
        error_db=error_db,
        mae_db=mae_db,
        rmse_db=rmse_db,
        bias_db=bias_db,
        max_abs_error_db=max_abs_error_db,
        correlation=correlation,
        points=len(aligned_time),
    )
