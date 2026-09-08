from __future__ import annotations

import numpy as np
from matplotlib.ticker import FixedLocator

from ..dcm_sw_generator import DcmSwWaveform
from ..dcm_zero_span_link import DcmZeroSpanResult
from .spectrum import DcmSpectrum


_PHASE_TICKS = np.asarray([-180, -120, -60, 0, 60, 120, 180], dtype=float)
MAX_DISPLAY_POINTS = 20_000


def display_indices_preserve_extrema(
    values: np.ndarray,
    *,
    max_points: int = MAX_DISPLAY_POINTS,
) -> np.ndarray:
    """Return sorted display indices while preserving local extrema.

    This is a rendering-only reduction. Algorithms, Marker lookup and exports keep
    the complete customer data. Each bucket contributes its local minimum and
    maximum so a narrow switching spike is not silently lost by simple stride
    decimation.
    """

    y = np.asarray(values, dtype=float)
    if y.ndim != 1:
        raise ValueError("display values must be one-dimensional")
    n = len(y)
    limit = max(4, int(max_points))
    if n <= limit:
        return np.arange(n, dtype=int)
    if n == 0:
        return np.empty(0, dtype=int)

    # Two extrema per bucket plus both endpoints. Choosing floor here guarantees
    # the result does not exceed max_points even before de-duplication.
    bucket_count = max(1, (limit - 2) // 2)
    edges = np.linspace(0, n, bucket_count + 1, dtype=int)
    selected: list[int] = [0, n - 1]

    for left, right in zip(edges[:-1], edges[1:], strict=True):
        if right <= left:
            continue
        segment = y[left:right]
        finite = np.isfinite(segment)
        if not np.any(finite):
            selected.append(left)
            continue
        finite_positions = np.flatnonzero(finite)
        finite_values = segment[finite]
        selected.append(left + int(finite_positions[int(np.argmin(finite_values))]))
        selected.append(left + int(finite_positions[int(np.argmax(finite_values))]))

    indices = np.unique(np.asarray(selected, dtype=int))
    if len(indices) > limit:
        keep = np.linspace(0, len(indices) - 1, limit).astype(int)
        indices = indices[keep]
    return indices


def display_indices_for_range(
    x_values: np.ndarray,
    y_values: np.ndarray,
    x_range: tuple[float, float] | None,
    *,
    max_points: int = MAX_DISPLAY_POINTS,
) -> np.ndarray:
    """Reduce only the currently visible X range, restoring detail on Zoom.

    X must be monotonically increasing, which is true for validated waveform time
    and FFT frequency axes. One sample outside each visible edge is retained when
    possible so line continuity at the viewport boundary is not visually broken.
    """

    x = np.asarray(x_values, dtype=float)
    y = np.asarray(y_values, dtype=float)
    if x.ndim != 1 or y.ndim != 1 or len(x) != len(y):
        raise ValueError("display x/y must be one-dimensional and equally sized")
    if len(x) == 0:
        return np.empty(0, dtype=int)
    if x_range is None:
        return display_indices_preserve_extrema(y, max_points=max_points)

    low, high = map(float, x_range)
    if high < low:
        low, high = high, low
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        return display_indices_preserve_extrema(y, max_points=max_points)

    start = int(np.searchsorted(x, low, side="left"))
    stop = int(np.searchsorted(x, high, side="right"))
    start = max(0, start - 1)
    stop = min(len(x), stop + 1)
    if stop <= start:
        nearest = int(np.clip(np.searchsorted(x, low), 0, len(x) - 1))
        return np.asarray([nearest], dtype=int)

    local = display_indices_preserve_extrema(
        y[start:stop],
        max_points=max_points,
    )
    return start + local


def _display_suffix(reduced: bool) -> str:
    return "（显示抽样；分析/导出仍用全数据）" if reduced else ""


def draw_time_domain_panel(
    ax,
    waveform: DcmSwWaveform | None,
    *,
    error: str | None = None,
    display_time_range_us: tuple[float, float] | None = None,
) -> None:
    """Draw the DCM time-domain panel without applying GUI axis policy."""

    if waveform is None:
        message = "DCM 波形当前不可生成"
        if error:
            message += f"\n{error}"
        ax.text(0.5, 0.5, message, ha="center", va="center", transform=ax.transAxes)
        ax.set_title("DCM SW 时域波形")
        ax.set_ylabel("电压 (V)")
        return

    time_s = np.asarray(waveform.time_s, dtype=float)
    voltage_v = np.asarray(waveform.voltage_v, dtype=float)
    ideal_v = np.asarray(waveform.ideal_voltage_v, dtype=float)
    x_us = time_s * 1e6
    indices = display_indices_for_range(
        x_us,
        voltage_v,
        display_time_range_us,
    )
    visible_count = (
        len(time_s)
        if display_time_range_us is None
        else max(
            0,
            int(np.searchsorted(x_us, max(display_time_range_us), side="right"))
            - int(np.searchsorted(x_us, min(display_time_range_us), side="left")),
        )
    )
    reduced = len(indices) < visible_count

    ax.plot(x_us[indices], voltage_v[indices], linewidth=0.9, label="当前 DCM SW")
    ax.plot(
        x_us[indices],
        ideal_v[indices],
        linewidth=0.75,
        alpha=0.75,
        label="理想轨迹",
    )
    ax.set_xlim(float(x_us[0]), float(x_us[-1]))
    ax.set_ylabel("电压 (V)")
    ax.set_title(f"DCM SW 时域波形{_display_suffix(reduced)}")
    ax.tick_params(labelbottom=False)
    ax.legend(loc="best")


def draw_zero_span_panel(
    ax,
    waveform: DcmSwWaveform | None,
    zero_span: DcmZeroSpanResult | None,
    *,
    error: str | None = None,
    display_time_range_us: tuple[float, float] | None = None,
) -> None:
    """Draw fixed-center Zero Span power-versus-time data."""

    ax.set_xlabel("绝对时间 (µs)")
    ax.set_ylabel("功率 (dBm)")

    if waveform is None:
        ax.text(
            0.5,
            0.5,
            "等待有效 DCM 波形",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        ax.set_title("Zero Span")
        return

    x_us = np.asarray(waveform.time_s, dtype=float) * 1e6
    ax.set_xlim(float(x_us[0]), float(x_us[-1]))

    if zero_span is None:
        message = "Zero Span 当前不可计算"
        if error:
            message += f"\n{error}"
        ax.text(
            0.5,
            0.5,
            message,
            ha="center",
            va="center",
            wrap=True,
            transform=ax.transAxes,
        )
        ax.set_title("Zero Span（等待有效转换参数）")
        return

    zero_time_us = np.asarray(zero_span.time_s, dtype=float) * 1e6
    amplitude_dbm = np.asarray(zero_span.amplitude_dbm, dtype=float)
    indices = display_indices_for_range(
        zero_time_us,
        amplitude_dbm,
        display_time_range_us,
    )
    visible_count = (
        len(zero_time_us)
        if display_time_range_us is None
        else max(
            0,
            int(np.searchsorted(zero_time_us, max(display_time_range_us), side="right"))
            - int(np.searchsorted(zero_time_us, min(display_time_range_us), side="left")),
        )
    )
    reduced = len(indices) < visible_count
    ax.plot(
        zero_time_us[indices],
        amplitude_dbm[indices],
        linewidth=0.9,
        label="等效 FSW Zero Span",
    )
    ax.set_title(
        f"Zero Span：Center {zero_span.center_frequency_hz/1e6:.6g} MHz / "
        f"RBW {zero_span.rbw_hz/1e6:.6g} MHz{_display_suffix(reduced)}"
    )
    ax.legend(loc="best")


def _draw_center_rbw_reference(
    ax,
    frequency_hz: np.ndarray,
    *,
    center_frequency_hz: float,
    rbw_hz: float,
) -> None:
    if len(frequency_hz) == 0:
        return

    freq_mhz = np.asarray(frequency_hz, dtype=float) / 1e6
    center_mhz = float(center_frequency_hz) / 1e6
    half_rbw_mhz = float(rbw_hz) / 2.0 / 1e6
    nyquist_mhz = float(freq_mhz[-1])
    lower = center_mhz - half_rbw_mhz
    upper = center_mhz + half_rbw_mhz

    if 0.0 <= center_mhz <= nyquist_mhz:
        ax.axvline(center_mhz, linestyle="--", linewidth=0.9, label="Zero Span Center")
    if upper >= 0.0 and lower <= nyquist_mhz:
        visible_lower = max(0.0, lower)
        visible_upper = min(nyquist_mhz, upper)
        if visible_upper > visible_lower:
            ax.axvspan(visible_lower, visible_upper, alpha=0.12, label="RBW")

    if center_mhz > nyquist_mhz:
        ax.text(
            0.98,
            0.96,
            f"Center {center_mhz:.6g} MHz 超出当前 Nyquist {nyquist_mhz:.6g} MHz",
            ha="right",
            va="top",
            transform=ax.transAxes,
            fontsize="small",
        )


def _spectrum_display_indices(
    spectrum: DcmSpectrum,
    display_frequency_range_mhz: tuple[float, float] | None,
) -> np.ndarray:
    # Magnitude drives the shared display indices so magnitude and wrapped phase
    # use exactly the same X samples after rendering reduction.
    frequency_mhz = np.asarray(spectrum.frequency_hz, dtype=float) / 1e6
    return display_indices_for_range(
        frequency_mhz,
        spectrum.amplitude_dbv,
        display_frequency_range_mhz,
    )


def _visible_frequency_count(
    frequency_mhz: np.ndarray,
    display_range: tuple[float, float] | None,
) -> int:
    if display_range is None:
        return len(frequency_mhz)
    low, high = sorted(map(float, display_range))
    return max(
        0,
        int(np.searchsorted(frequency_mhz, high, side="right"))
        - int(np.searchsorted(frequency_mhz, low, side="left")),
    )


def draw_magnitude_spectrum_panel(
    ax,
    spectrum: DcmSpectrum | None,
    *,
    center_frequency_hz: float,
    rbw_hz: float,
    display_frequency_range_mhz: tuple[float, float] | None = None,
) -> None:
    """Draw DCM FFT magnitude and Zero Span Center/RBW references."""

    if spectrum is None or spectrum.points == 0:
        ax.text(
            0.5,
            0.5,
            "当前波形无法计算频域",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        ax.set_title("DCM 幅度频谱")
        ax.set_xlabel("频率 (MHz)")
        ax.set_ylabel("幅度 (dBV)")
        ax.grid(True, alpha=0.25)
        return

    frequency_hz = np.asarray(spectrum.frequency_hz, dtype=float)
    amplitude_dbv = np.asarray(spectrum.amplitude_dbv, dtype=float)
    freq_mhz = frequency_hz / 1e6
    indices = _spectrum_display_indices(spectrum, display_frequency_range_mhz)
    reduced = len(indices) < _visible_frequency_count(freq_mhz, display_frequency_range_mhz)
    ax.plot(freq_mhz[indices], amplitude_dbv[indices], linewidth=0.85, label="DCM FFT")
    ax.set_xlim(float(freq_mhz[0]), float(freq_mhz[-1]))
    ax.set_xlabel("频率 (MHz)")
    ax.set_ylabel("幅度 (dBV)")
    ax.set_title(f"DCM 幅度频谱（去直流 / Hann FFT）{_display_suffix(reduced)}")
    ax.grid(True, alpha=0.25)
    _draw_center_rbw_reference(
        ax,
        frequency_hz,
        center_frequency_hz=center_frequency_hz,
        rbw_hz=rbw_hz,
    )
    ax.legend(loc="best")


def draw_phase_spectrum_panel(
    ax,
    spectrum: DcmSpectrum | None,
    *,
    center_frequency_hz: float,
    rbw_hz: float,
    display_frequency_range_mhz: tuple[float, float] | None = None,
) -> None:
    """Draw wrapped phase using the exact same frequency bins as magnitude."""

    if spectrum is None or spectrum.points == 0:
        ax.text(
            0.5,
            0.5,
            "等待有效 DCM 频域",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        ax.set_title("DCM 相位频谱")
        ax.set_xlabel("频率 (MHz)")
        ax.set_ylabel("相位 (°)")
        ax.set_ylim(-180.0, 180.0, auto=False)
        ax.yaxis.set_major_locator(FixedLocator(_PHASE_TICKS))
        ax.grid(True, alpha=0.25)
        return

    frequency_hz = np.asarray(spectrum.frequency_hz, dtype=float)
    phase_deg = np.asarray(spectrum.phase_deg, dtype=float)
    freq_mhz = frequency_hz / 1e6
    indices = _spectrum_display_indices(spectrum, display_frequency_range_mhz)
    reduced = len(indices) < _visible_frequency_count(freq_mhz, display_frequency_range_mhz)
    ax.plot(freq_mhz[indices], phase_deg[indices], linewidth=0.8, label="DCM Phase")
    ax.set_xlabel("频率 (MHz)")
    ax.set_ylabel("相位 (°)")
    ax.set_title(
        "DCM 相位频谱（Wrapped；参考=当前记录起点；"
        f"有效幅度 ≥ {spectrum.phase_visibility_threshold_dbv:.1f} dBV）"
        f"{_display_suffix(reduced)}"
    )
    ax.set_ylim(-180.0, 180.0, auto=False)
    ax.yaxis.set_major_locator(FixedLocator(_PHASE_TICKS))
    ax.set_autoscaley_on(False)
    ax.grid(True, which="major", alpha=0.25)
    _draw_center_rbw_reference(
        ax,
        frequency_hz,
        center_frequency_hz=center_frequency_hz,
        rbw_hz=rbw_hz,
    )
    ax.legend(loc="best")


__all__ = [
    "MAX_DISPLAY_POINTS",
    "display_indices_preserve_extrema",
    "display_indices_for_range",
    "draw_time_domain_panel",
    "draw_zero_span_panel",
    "draw_magnitude_spectrum_panel",
    "draw_phase_spectrum_panel",
]
