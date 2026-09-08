from __future__ import annotations

from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import pandas as pd

from .comparison import compare_zero_span, load_fsw_zero_span_csv
from .config import AppConfig
from .converter import ConversionResult, _write_conversion_metadata, load_waveform


def save_result_headless(
    result: ConversionResult,
    waveform_path: str | Path,
    config: AppConfig,
    *,
    metadata_path: str | Path | None = None,
    reference_fsw_path: str | Path | None = None,
) -> ConversionResult:
    """Save conversion outputs without creating a GUI Matplotlib manager.

    This mirrors the file semantics of ``converter.save_result`` for worker and
    batch execution. The figure is backed directly by Agg, so it can be rendered
    safely outside the Qt GUI thread. ``show_plot`` is intentionally ignored;
    worker code must never open an interactive plot window.
    """

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

    if config.output.save_plot:
        t, voltage_v, _ = load_waveform(waveform_path)
        t_rel = t - t[0]

        fig = Figure(figsize=(14, 9), layout="constrained")
        FigureCanvasAgg(fig)
        axes = fig.subplots(2, 1)
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

        plot_path = output_dir / "waveform_zero_span_compare.png"
        fig.savefig(plot_path, dpi=160)
        result.output_plot = plot_path
        fig.clear()

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

    return result


__all__ = ["save_result_headless"]
