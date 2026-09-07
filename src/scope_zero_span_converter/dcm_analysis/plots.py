from __future__ import annotations

import numpy as np
from matplotlib.ticker import FixedLocator

from ..dcm_sw_generator import DcmSwWaveform
from ..dcm_zero_span_link import DcmZeroSpanResult
from .spectrum import DcmSpectrum


_PHASE_TICKS = np.asarray([-180, -120, -60, 0, 60, 120, 180], dtype=float)


def draw_time_domain_panel(
    ax,
    waveform: DcmSwWaveform | None,
    *,
    error: str | None = None,
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

    x_us = np.asarray(waveform.time_s, dtype=float) * 1e6
    ax.plot(x_us, waveform.voltage_v, linewidth=0.9, label="当前 DCM SW")
    ax.plot(
        x_us,
        waveform.ideal_voltage_v,
        linewidth=0.75,
        alpha=0.75,
        label="理想轨迹",
    )
    ax.set_xlim(float(x_us[0]), float(x_us[-1]))
    ax.set_ylabel("电压 (V)")
    ax.set_title("DCM SW 时域波形")
    ax.tick_params(labelbottom=False)
    ax.legend(loc="best")


def draw_zero_span_panel(
    ax,
    waveform: DcmSwWaveform | None,
    zero_span: DcmZeroSpanResult | None,
    *,
    error: str | None = None,
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

    ax.plot(
        np.asarray(zero_span.time_s, dtype=float) * 1e6,
        zero_span.amplitude_dbm,
        linewidth=0.9,
        label="等效 FSW Zero Span",
    )
    ax.set_title(
        f"Zero Span：Center {zero_span.center_frequency_hz/1e6:.6g} MHz / "
        f"RBW {zero_span.rbw_hz/1e6:.6g} MHz"
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


def draw_magnitude_spectrum_panel(
    ax,
    spectrum: DcmSpectrum | None,
    *,
    center_frequency_hz: float,
    rbw_hz: float,
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
    freq_mhz = frequency_hz / 1e6
    ax.plot(freq_mhz, spectrum.amplitude_dbv, linewidth=0.85, label="DCM FFT")
    ax.set_xlim(float(freq_mhz[0]), float(freq_mhz[-1]))
    ax.set_xlabel("频率 (MHz)")
    ax.set_ylabel("幅度 (dBV)")
    ax.set_title("DCM 幅度频谱（去直流 / Hann FFT）")
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
    freq_mhz = frequency_hz / 1e6
    ax.plot(freq_mhz, spectrum.phase_deg, linewidth=0.8, label="DCM Phase")
    ax.set_xlabel("频率 (MHz)")
    ax.set_ylabel("相位 (°)")
    ax.set_title(
        "DCM 相位频谱（Wrapped；参考=当前记录起点；"
        f"有效幅度 ≥ {spectrum.phase_visibility_threshold_dbv:.1f} dBV）"
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
    "draw_time_domain_panel",
    "draw_zero_span_panel",
    "draw_magnitude_spectrum_panel",
    "draw_phase_spectrum_panel",
]
