from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import AppConfig
from .converter import (
    EPS_W,
    ConversionResult,
    _resolve_parameters,
    apply_vbw,
    extract_fsw_settings,
    gaussian_rbw_baseband,
    load_metadata,
)


@dataclass(frozen=True)
class WaveformRegion:
    start_time_s: float
    end_time_s: float
    start_index: int
    end_index: int
    points: int
    duration_s: float


def crop_waveform(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    start_time_s: float,
    end_time_s: float,
    *,
    min_points: int = 32,
) -> tuple[np.ndarray, np.ndarray, WaveformRegion]:
    t = np.asarray(time_s, dtype=float)
    v = np.asarray(voltage_v, dtype=float)

    if t.ndim != 1 or v.ndim != 1 or len(t) != len(v):
        raise ValueError("time_s 与 voltage_v 必须是一维且长度一致")
    if len(t) < min_points:
        raise ValueError(f"原始波形点数少于 {min_points}")

    start = float(start_time_s)
    end = float(end_time_s)
    if end < start:
        start, end = end, start

    start = max(start, float(t[0]))
    end = min(end, float(t[-1]))
    if end <= start:
        raise ValueError("研究区域没有有效时间范围")

    indices = np.flatnonzero((t >= start) & (t <= end))
    if len(indices) < min_points:
        raise ValueError(
            f"研究区域只有 {len(indices)} 个点，至少需要 {min_points} 个点"
        )

    first = int(indices[0])
    last = int(indices[-1])
    region_t = t[first : last + 1]
    region_v = v[first : last + 1]

    region = WaveformRegion(
        start_time_s=float(region_t[0]),
        end_time_s=float(region_t[-1]),
        start_index=first,
        end_index=last,
        points=len(region_t),
        duration_s=float(region_t[-1] - region_t[0]),
    )
    return region_t, region_v, region


def save_waveform_region(
    path: str | Path,
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    region: WaveformRegion,
    *,
    source_waveform: str | Path | None = None,
    reset_time_to_zero: bool = False,
    save_metadata: bool = True,
) -> tuple[Path, Path | None]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    output_time = np.asarray(time_s, dtype=float).copy()
    if reset_time_to_zero:
        output_time = output_time - output_time[0]

    pd.DataFrame(
        {
            "time_s": output_time,
            "voltage_v": np.asarray(voltage_v, dtype=float),
        }
    ).to_csv(path, index=False, encoding="utf-8-sig")

    metadata_path: Path | None = None
    if save_metadata:
        metadata_path = path.with_suffix(".region.json")
        payload = {
            "schema_version": 1,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_waveform": str(source_waveform) if source_waveform else None,
            "selection": {
                "start_time_s": region.start_time_s,
                "end_time_s": region.end_time_s,
                "duration_s": region.duration_s,
                "start_index": region.start_index,
                "end_index": region.end_index,
                "points": region.points,
            },
            "saved_time_axis": "relative_zero" if reset_time_to_zero else "original",
            "output_csv": str(path),
        }
        metadata_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return path, metadata_path


def _sample_rate_from_time(time_s: np.ndarray) -> float:
    dt = np.diff(np.asarray(time_s, dtype=float))
    dt = dt[np.isfinite(dt) & (dt > 0)]
    if len(dt) == 0:
        raise ValueError("研究区域无法推导采样率")
    return 1.0 / float(np.median(dt))


def convert_waveform_region(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    metadata_path: str | Path,
    config: AppConfig,
) -> ConversionResult:
    """对当前研究区域执行 Zero Span 转换。

    研究模式故意不重采样到原 FSW Sweep Time / Points，输出时间轴始终对应
    当前选中的波形区域，便于上、下两条曲线按同一研究区联动观察。
    """
    config.validate()

    t = np.asarray(time_s, dtype=float)
    v = np.asarray(voltage_v, dtype=float)
    if len(t) < 32 or len(t) != len(v):
        raise ValueError("研究区域波形无效或点数不足")

    meta = load_metadata(metadata_path)
    meta_settings = extract_fsw_settings(meta)
    center_hz, rbw_hz, vbw_hz, parameter_sources = _resolve_parameters(
        config,
        meta_settings,
    )

    sample_rate_hz = _sample_rate_from_time(t)
    nyquist_hz = sample_rate_hz / 2.0
    top_hz = center_hz + rbw_hz / 2.0

    if top_hz >= nyquist_hz:
        raise ValueError(
            f"采样率不足：Center+RBW/2={top_hz:g} Hz, Nyquist={nyquist_hz:g} Hz"
        )
    if top_hz > config.scope.analog_bandwidth_hz:
        raise ValueError(
            f"目标通带超出示波器模拟带宽：{top_hz:g} > "
            f"{config.scope.analog_bandwidth_hz:g} Hz"
        )

    baseband = gaussian_rbw_baseband(
        t,
        v,
        sample_rate_hz,
        center_hz,
        rbw_hz,
    )
    envelope_v_rms = np.abs(baseband) / np.sqrt(2.0)
    power_w = envelope_v_rms**2 / config.conversion.impedance_ohm

    effective_vbw = vbw_hz if config.conversion.vbw_enabled else None
    power_w = apply_vbw(power_w, sample_rate_hz, effective_vbw)
    amplitude_dbm = (
        10.0 * np.log10(np.maximum(power_w, EPS_W) / 1e-3)
        + config.conversion.calibration_db
    )

    return ConversionResult(
        time_s=t - t[0],
        amplitude_dbm=amplitude_dbm,
        envelope_v_rms=envelope_v_rms,
        center_frequency_hz=center_hz,
        rbw_hz=rbw_hz,
        vbw_hz=effective_vbw,
        sample_rate_hz=sample_rate_hz,
        input_points=len(t),
        parameter_sources=parameter_sources,
        fsw_sweep_time_s=meta_settings.get("sweep_time_s"),
        fsw_trace_points=meta_settings.get("points"),
        resampled_to_fsw_axis=False,
    )
