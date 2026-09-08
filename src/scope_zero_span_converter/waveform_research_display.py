from __future__ import annotations

import numpy as np
from matplotlib.widgets import SpanSelector

from .dcm_analysis.plots import display_indices_for_range


TIME_SCALES = {
    "ns": 1e9,
    "us": 1e6,
    "ms": 1e3,
    "s": 1.0,
}
TIME_LABELS = {
    "ns": "ns",
    "us": "µs",
    "ms": "ms",
    "s": "s",
}
_DISPLAY_SUFFIX = "（显示抽样；分析/保存仍用全数据）"


def _visible_count(x: np.ndarray, x_range: tuple[float, float] | None) -> int:
    if x_range is None:
        return len(x)
    low, high = sorted(map(float, x_range))
    return max(
        0,
        int(np.searchsorted(x, high, side="right"))
        - int(np.searchsorted(x, low, side="left")),
    )


def redraw_waveform_research(window) -> None:
    """Render the legacy research page without plotting every large-data sample.

    This function changes display data only. ``window.waveform_time``, ROI arrays,
    Zero Span conversion input, saved CSV and all analysis results remain full
    resolution. When the customer zooms to the selected ROI, reduction is applied
    only inside that viewport so local detail automatically comes back.
    """

    if window.waveform_time is None:
        window._draw_empty_figure()
        return

    unit = window.time_unit_combo.currentText()
    scale = TIME_SCALES[unit]
    label = TIME_LABELS[unit]

    window.figure.clear()
    ax1 = window.figure.add_subplot(211)
    ax2 = window.figure.add_subplot(212)

    time_s = np.asarray(window.waveform_time, dtype=float)
    voltage_v = np.asarray(window.waveform_voltage, dtype=float)
    x = time_s * scale

    display_range: tuple[float, float] | None = None
    if window.current_region is not None and window._zoom_to_region:
        start_x = window.current_region.start_time_s * scale
        end_x = window.current_region.end_time_s * scale
        margin = max((end_x - start_x) * 0.05, 1e-15)
        display_range = (start_x - margin, end_x + margin)

    indices = display_indices_for_range(x, voltage_v, display_range)
    reduced = len(indices) < _visible_count(x, display_range)
    ax1.plot(x[indices], voltage_v[indices], linewidth=0.8)
    ax1.set_title(
        "原始时域波形 - 拖动鼠标选择研究区域"
        + (_DISPLAY_SUFFIX if reduced else "")
    )
    ax1.set_xlabel(f"时间 ({label})")
    ax1.set_ylabel("电压 (V)")
    ax1.grid(True, alpha=0.3)

    if window.current_region is not None:
        start_x = window.current_region.start_time_s * scale
        end_x = window.current_region.end_time_s * scale
        ax1.axvspan(start_x, end_x, alpha=0.16)
        if window._zoom_to_region:
            margin = max((end_x - start_x) * 0.05, 1e-15)
            ax1.set_xlim(start_x - margin, end_x + margin)

    if window.region_conversion is not None:
        result, origin_s = window.region_conversion
        converted_x = (origin_s + np.asarray(result.time_s, dtype=float)) * scale
        converted_y = np.asarray(result.amplitude_dbm, dtype=float)
        converted_indices = display_indices_for_range(
            converted_x,
            converted_y,
            display_range,
        )
        converted_reduced = len(converted_indices) < _visible_count(
            converted_x,
            display_range,
        )
        ax2.plot(
            converted_x[converted_indices],
            converted_y[converted_indices],
            linewidth=1.0,
        )
        scope_text = "当前研究区域" if window.current_region is not None else "完整波形"
        ax2.set_title(
            f"{scope_text}联动转换 - Center {result.center_frequency_hz/1e6:.3f} MHz / "
            f"RBW {result.rbw_hz/1e6:.3f} MHz"
            + (_DISPLAY_SUFFIX if converted_reduced else "")
        )
        if window.current_region is not None and window._zoom_to_region:
            start_x = window.current_region.start_time_s * scale
            end_x = window.current_region.end_time_s * scale
            margin = max((end_x - start_x) * 0.05, 1e-15)
            ax2.set_xlim(start_x - margin, end_x + margin)
    else:
        ax2.set_title("研究区域对应的转换波形（等待 metadata 或刷新）")

    ax2.set_xlabel(f"时间 ({label})")
    ax2.set_ylabel("功率 (dBm)")
    ax2.grid(True, alpha=0.3)

    window.figure.tight_layout()
    window.canvas.draw()

    window._span_selector = SpanSelector(
        ax1,
        window._on_span_select,
        "horizontal",
        useblit=True,
        props={"alpha": 0.18},
        interactive=True,
        drag_from_anywhere=True,
    )


__all__ = ["redraw_waveform_research"]
