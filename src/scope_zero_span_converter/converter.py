from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import __version__
from .comparison import ComparisonResult, compare_zero_span, load_fsw_zero_span_csv
from .config import AppConfig
from .plotting import configure_matplotlib_chinese
from .waveform_quality import WaveformQualityReport, analyze_time_axis, require_fft_safe


EPS_W = 1e-30
configure_matplotlib_chinese()


@dataclass
class ConversionResult:
    time_s: np.ndarray
    amplitude_dbm: np.ndarray
    envelope_v_rms: np.ndarray
    center_frequency_hz: float
    rbw_hz: float
    vbw_hz: float | None
    sample_rate_hz: float
    input_points: int
    parameter_sources: dict[str, str]
    fsw_sweep_time_s: float | None
    fsw_trace_points: int | None
    resampled_to_fsw_axis: bool
    waveform_quality: WaveformQualityReport
    output_csv: Path | None = None
    output_plot: Path | None = None
    output_metadata: Path | None = None
    output_comparison_csv: Path | None = None
    comparison: ComparisonResult | None = None


def _nested_get(obj: dict, keys: tuple[str, ...]):
    cur = obj
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _as_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def load_metadata(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def extract_fsw_settings(meta: dict) -> dict:
    """Backward-compatible metadata parser.

    Metadata remains available for diagnostics/provenance, but conversion runtime
    parameters are no longer resolved from it.
    """

    cfg = _nested_get(
        meta,
        ("metadata", "instruments", "spectrum_analyzer", "configuration"),
    )
    if not isinstance(cfg, dict):
        cfg = _nested_get(meta, ("instruments", "spectrum_analyzer", "configuration"))
    if not isinstance(cfg, dict):
        cfg = {}

    ext = _nested_get(meta, ("spectra", "ext"))
    if not isinstance(ext, dict):
        ext = {}
    ext_meta = ext.get("metadata") if isinstance(ext.get("metadata"), dict) else {}

    center_hz = _as_float(ext_meta.get("center_frequency_hz"))
    if center_hz is None:
        center_hz = _as_float(cfg.get("center_frequency_hz"))

    span_hz = _as_float(ext_meta.get("span_hz"))
    if span_hz is None:
        span_hz = _as_float(cfg.get("span_hz"))

    rbw_hz = _as_float(cfg.get("rbw_hz"))
    vbw_hz = _as_float(cfg.get("vbw_hz"))
    sweep_time_s = _as_float(ext_meta.get("sweep_time_s"))

    points = ext.get("points")
    try:
        points = int(points) if points is not None else None
    except (TypeError, ValueError):
        points = None

    return {
        "center_frequency_hz": center_hz,
        "span_hz": span_hz,
        "rbw_hz": rbw_hz,
        "vbw_hz": vbw_hz,
        "sweep_time_s": sweep_time_s,
        "points": points,
    }


def load_waveform_with_quality(
    path: str | Path,
) -> tuple[np.ndarray, np.ndarray, float, WaveformQualityReport]:
    """Load a waveform and enforce the shared FFT/Zero Span time-axis policy."""

    df = pd.read_csv(path)
    if {"time_s", "voltage_v"}.issubset(df.columns):
        t = pd.to_numeric(df["time_s"], errors="coerce").to_numpy(float)
        v = pd.to_numeric(df["voltage_v"], errors="coerce").to_numpy(float)
    elif len(df.columns) >= 2:
        t = pd.to_numeric(df.iloc[:, 0], errors="coerce").to_numpy(float)
        v = pd.to_numeric(df.iloc[:, 1], errors="coerce").to_numpy(float)
    else:
        raise ValueError("waveform.csv 至少需要两列，推荐 time_s,voltage_v")

    mask = np.isfinite(t) & np.isfinite(v)
    t = t[mask]
    v = v[mask]
    if len(t) < 32:
        raise ValueError("有效波形点数少于 32")

    quality = analyze_time_axis(t)
    require_fft_safe(quality)

    order = np.argsort(t)
    t = t[order]
    v = v[order]
    return t, v, quality.sample_rate_hz, quality


def load_waveform(path: str | Path):
    """Backward-compatible waveform loader returning time, voltage and Fs."""

    t, v, sample_rate_hz, _quality = load_waveform_with_quality(path)
    return t, v, sample_rate_hz


def gaussian_rbw_baseband(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    sample_rate_hz: float,
    center_frequency_hz: float,
    rbw_hz: float,
) -> np.ndarray:
    x = np.asarray(voltage_v, dtype=float)
    x = x - np.mean(x)
    n = len(x)

    pad = int(math.ceil(8.0 * sample_rate_hz / rbw_hz))
    pad = max(64, min(pad, max(64, n // 2)))
    x_pad = np.pad(x, (pad, pad), mode="reflect")

    dt = 1.0 / sample_rate_hz
    idx = np.arange(len(x_pad), dtype=float) - pad
    t_pad = float(time_s[0]) + idx * dt

    baseband = 2.0 * x_pad * np.exp(
        -1j * 2.0 * np.pi * center_frequency_hz * t_pad
    )

    freq = np.fft.fftfreq(len(baseband), d=dt)
    response = np.exp(-2.0 * np.log(2.0) * (freq / rbw_hz) ** 2)
    filtered = np.fft.ifft(np.fft.fft(baseband) * response)
    return filtered[pad:-pad]


def apply_vbw(power_w: np.ndarray, sample_rate_hz: float, vbw_hz: float | None):
    if vbw_hz is None or vbw_hz <= 0 or vbw_hz >= sample_rate_hz / 2.0:
        return power_w.copy()

    dt = 1.0 / sample_rate_hz
    tau = 1.0 / (2.0 * np.pi * vbw_hz)
    alpha = dt / (tau + dt)
    out = np.empty_like(power_w)
    out[0] = power_w[0]
    for i in range(1, len(power_w)):
        out[i] = out[i - 1] + alpha * (power_w[i] - out[i - 1])
    return out


def resample_to_fsw_axis(
    scope_time_s: np.ndarray,
    power_w: np.ndarray,
    envelope_v_rms: np.ndarray,
    points: int | None,
    sweep_time_s: float | None,
):
    scope_time_s = np.asarray(scope_time_s, dtype=float)
    power_w = np.asarray(power_w, dtype=float)
    envelope_v_rms = np.asarray(envelope_v_rms, dtype=float)

    if not (
        len(scope_time_s) == len(power_w) == len(envelope_v_rms)
        and len(scope_time_s) >= 2
    ):
        raise ValueError("FSW 重采样输入长度不一致或有效点数少于 2")

    t_rel = scope_time_s - scope_time_s[0]
    if points is None or points < 2 or sweep_time_s is None or sweep_time_s <= 0:
        return t_rel, power_w, envelope_v_rms, False

    available_duration_s = float(t_rel[-1])
    requested_sweep_s = float(sweep_time_s)
    tolerance_s = max(abs(available_duration_s), abs(requested_sweep_s), 1e-15) * 1e-9
    if requested_sweep_s > available_duration_s + tolerance_s:
        raise ValueError(
            "FSW Sweep Time 超出示波器实际记录时长："
            f"Sweep={requested_sweep_s:.12g} s, "
            f"Scope={available_duration_s:.12g} s。"
            "为避免静默尾值外推，请重新采集更长的示波器波形或缩短 FSW Sweep Time。"
        )

    target_t = np.linspace(0.0, requested_sweep_s, points)
    return (
        target_t,
        np.interp(target_t, t_rel, power_w),
        np.interp(target_t, t_rel, envelope_v_rms),
        True,
    )


def _resolve_parameters(config: AppConfig, _meta_settings: dict | None = None):
    """Resolve runtime parameters exclusively from GUI/AppConfig."""

    signal = config.signal
    center = float(signal.center_frequency_hz)
    rbw = float(signal.rbw_hz)
    vbw = float(signal.vbw_hz)
    span = float(signal.span_hz)

    if abs(span) > 1e-9:
        raise ValueError(f"当前数据不是 Zero Span：span_hz={span}")

    sources = {
        "center_frequency_hz": "config",
        "rbw_hz": "config",
        "vbw_hz": "config",
        "span_hz": "config",
    }
    return center, rbw, vbw, sources


def convert(
    waveform_path: str | Path,
    metadata_path: str | Path,
    config: AppConfig,
) -> ConversionResult:
    """Convert using GUI/AppConfig as the sole source of runtime parameters.

    ``metadata_path`` is retained in the public signature for compatibility and
    output provenance. Its FSW parameter values do not affect conversion.
    """

    del metadata_path
    config.conversion.use_metadata_parameters = False
    config.validate()
    center_hz, rbw_hz, vbw_hz, parameter_sources = _resolve_parameters(config)

    t, voltage_v, sample_rate_hz, waveform_quality = load_waveform_with_quality(
        waveform_path
    )
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
        voltage_v,
        sample_rate_hz,
        center_hz,
        rbw_hz,
    )
    envelope_v_rms = np.abs(baseband) / np.sqrt(2.0)
    power_w = envelope_v_rms**2 / config.conversion.impedance_ohm

    effective_vbw = vbw_hz if config.conversion.vbw_enabled else None
    power_w = apply_vbw(power_w, sample_rate_hz, effective_vbw)

    sweep_time_s = config.conversion.fsw_sweep_time_s
    trace_points = config.conversion.fsw_trace_points
    if config.conversion.resample_to_fsw_axis:
        out_t, out_power_w, out_env, resampled = resample_to_fsw_axis(
            t,
            power_w,
            envelope_v_rms,
            trace_points,
            sweep_time_s,
        )
    else:
        out_t = t - t[0]
        out_power_w = power_w
        out_env = envelope_v_rms
        resampled = False

    amplitude_dbm = (
        10.0 * np.log10(np.maximum(out_power_w, EPS_W) / 1e-3)
        + config.conversion.calibration_db
    )

    return ConversionResult(
        time_s=out_t,
        amplitude_dbm=amplitude_dbm,
        envelope_v_rms=out_env,
        center_frequency_hz=center_hz,
        rbw_hz=rbw_hz,
        vbw_hz=effective_vbw,
        sample_rate_hz=sample_rate_hz,
        input_points=len(t),
        parameter_sources=parameter_sources,
        fsw_sweep_time_s=sweep_time_s,
        fsw_trace_points=trace_points,
        resampled_to_fsw_axis=resampled,
        waveform_quality=waveform_quality,
    )


def _comparison_as_dict(comparison: ComparisonResult | None):
    if comparison is None:
        return None
    return {
        "points": comparison.points,
        "mae_db": comparison.mae_db,
        "rmse_db": comparison.rmse_db,
        "bias_db": comparison.bias_db,
        "max_abs_error_db": comparison.max_abs_error_db,
        "correlation": comparison.correlation,
    }


def _write_conversion_metadata(
    path: Path,
    result: ConversionResult,
    config: AppConfig,
    waveform_path: Path,
    metadata_path: Path | None,
    reference_fsw_path: Path | None,
) -> None:
    payload = {
        "schema_version": 1,
        "software": {
            "name": "scope-zero-span-converter",
            "version": __version__,
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "waveform_file": str(waveform_path),
            "metadata_file": str(metadata_path) if metadata_path else None,
            "fsw_reference_file": str(reference_fsw_path) if reference_fsw_path else None,
        },
        "effective_parameters": {
            "center_frequency_hz": result.center_frequency_hz,
            "span_hz": 0.0,
            "rbw_hz": result.rbw_hz,
            "vbw_hz": result.vbw_hz,
            "detector": config.conversion.detector,
            "rbw_filter": config.conversion.rbw_filter,
            "vbw_enabled": config.conversion.vbw_enabled,
            "fsw_sweep_time_s": config.conversion.fsw_sweep_time_s,
            "fsw_trace_points": config.conversion.fsw_trace_points,
            "impedance_ohm": config.conversion.impedance_ohm,
            "calibration_db": config.conversion.calibration_db,
            "scope_analog_bandwidth_hz": config.scope.analog_bandwidth_hz,
        },
        "parameter_sources": result.parameter_sources,
        "acquisition": {
            "sample_rate_hz": result.sample_rate_hz,
            "input_points": result.input_points,
            "output_points": len(result.time_s),
            "fsw_sweep_time_s": result.fsw_sweep_time_s,
            "fsw_trace_points": result.fsw_trace_points,
            "resampled_to_fsw_axis": result.resampled_to_fsw_axis,
            "time_axis_quality": asdict(result.waveform_quality),
        },
        "algorithm": {
            "digital_downconversion": True,
            "rbw_filter": "gaussian_3db_bandwidth",
            "detector": "rms_power",
            "vbw_filter": "first_order_lowpass" if result.vbw_hz is not None else None,
        },
        "comparison": _comparison_as_dict(result.comparison),
        "config_snapshot": asdict(config),
        "outputs": {
            "zero_span_csv": str(result.output_csv) if result.output_csv else None,
            "plot_png": str(result.output_plot) if result.output_plot else None,
            "comparison_csv": (
                str(result.output_comparison_csv)
                if result.output_comparison_csv
                else None
            ),
        },
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def save_result(
    result: ConversionResult,
    waveform_path: str | Path,
    config: AppConfig,
    *,
    metadata_path: str | Path | None = None,
    reference_fsw_path: str | Path | None = None,
) -> ConversionResult:
    output_dir = Path(config.output.directory)
    output_dir.mkdir(parents=True, exist_ok=True)

    waveform_path = Path(waveform_path)
    metadata_path_obj = Path(metadata_path) if metadata_path else None
    reference_path_obj = Path(reference_fsw_path) if reference_fsw_path else None

    if config.output.save_csv:
        csv_path = output_dir / "zero_span_from_scope.csv"
        pd.DataFrame(
            {
                "time_s": result.time_s,
                "amplitude_dbm": result.amplitude_dbm,
                "envelope_v_rms": result.envelope_v_rms,
            }
        ).to_csv(csv_path, index=False, encoding="utf-8-sig")
        result.output_csv = csv_path

    if (
        config.comparison.enabled
        and reference_path_obj is not None
        and reference_path_obj.exists()
    ):
        ref_time, ref_dbm = load_fsw_zero_span_csv(reference_path_obj)
        result.comparison = compare_zero_span(
            result.time_s,
            result.amplitude_dbm,
            ref_time,
            ref_dbm,
        )
        if config.comparison.save_aligned_csv:
            comparison_csv = output_dir / "comparison_to_fsw.csv"
            pd.DataFrame(
                {
                    "time_s": result.comparison.time_s,
                    "reconstructed_dbm": result.comparison.reconstructed_dbm,
                    "fsw_reference_dbm": result.comparison.reference_dbm,
                    "error_db": result.comparison.error_db,
                }
            ).to_csv(comparison_csv, index=False, encoding="utf-8-sig")
            result.output_comparison_csv = comparison_csv

    t, voltage_v, _ = load_waveform(waveform_path)
    t_rel = t - t[0]

    fig, axes = plt.subplots(2, 1, figsize=(14, 9), constrained_layout=True)
    axes[0].plot(t_rel, voltage_v, linewidth=0.8)
    axes[0].set_title("示波器原始时域波形")
    axes[0].set_xlabel("时间 (s)")
    axes[0].set_ylabel("电压 (V)")
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(
        result.time_s,
        result.amplitude_dbm,
        linewidth=1.0,
        label="示波器恢复",
    )
    if result.comparison is not None:
        axes[1].plot(
            result.comparison.time_s,
            result.comparison.reference_dbm,
            linewidth=1.0,
            label="FSW 实测",
        )
        metrics = (
            f"MAE={result.comparison.mae_db:.3f} dB  "
            f"RMSE={result.comparison.rmse_db:.3f} dB  "
            f"Bias={result.comparison.bias_db:+.3f} dB"
        )
        axes[1].text(
            0.01,
            0.02,
            metrics,
            transform=axes[1].transAxes,
            ha="left",
            va="bottom",
            fontsize=9,
            bbox=dict(boxstyle="round", alpha=0.12),
        )
        axes[1].legend()

    axes[1].set_title(
        "Zero Span 时域恢复 - "
        f"Center {result.center_frequency_hz / 1e6:.3f} MHz / "
        f"RBW {result.rbw_hz / 1e6:.3f} MHz"
    )
    axes[1].set_xlabel("时间 (s)")
    axes[1].set_ylabel("功率 (dBm)")
    axes[1].grid(True, alpha=0.3)

    if config.output.save_plot:
        plot_path = output_dir / "waveform_zero_span_compare.png"
        fig.savefig(plot_path, dpi=160)
        result.output_plot = plot_path

    if config.output.save_conversion_metadata:
        metadata_out = output_dir / "conversion_metadata.json"
        result.output_metadata = metadata_out
        _write_conversion_metadata(
            metadata_out,
            result,
            config,
            waveform_path,
            metadata_path_obj,
            reference_path_obj,
        )

    if config.output.show_plot:
        plt.show()
    else:
        plt.close(fig)

    return result
