from __future__ import annotations

import numpy as np
from matplotlib.ticker import FixedLocator

from .dcm_sw_generator import DcmSwWaveform
from .dcm_zero_span_widget_v9 import DcmZeroSpanWidget as SyncedFrequencyDcmZeroSpanWidget


class DcmZeroSpanWidget(SyncedFrequencyDcmZeroSpanWidget):
    """四格联动页：右下增加与右上同一 FFT 对应的相位频谱。

    布局：
    - 左上：DCM SW 时域波形；
    - 左下：Zero Span；
    - 右上：DCM 幅度频谱（dBV）；
    - 右下：DCM 相位频谱（degree）。

    幅度和相位来自同一次去直流 + Hann 窗的单边复数 FFT，使用完全相同的
    frequency bins。右上/右下共享频率 X 轴；右上频率拖框放大时右下同步。
    幅度低于 PHASE_VISIBLE_FLOOR_DBV 的 bin 相位没有实际分析价值，显示为 NaN。
    """

    PHASE_VISIBLE_FLOOR_DBV = -120.0

    def __init__(self, parent=None) -> None:
        # 父类构造阶段会动态调用本类绘图方法，因此相位缓存必须提前建立。
        self.current_spectrum_phase_deg = np.asarray([], dtype=float)
        super().__init__(parent)
        self._redraw(zero_span_error=self.current_zero_span_error)

    def _compute_frequency_spectrum_with_phase(
        self,
        waveform: DcmSwWaveform,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """一次复数 FFT 同时得到频率、幅度 dBV 和 wrapped phase degree。"""
        t = np.asarray(waveform.time_s, dtype=float)
        v = np.asarray(waveform.voltage_v, dtype=float)
        if len(t) < 2 or len(t) != len(v):
            empty = np.asarray([], dtype=float)
            return empty, empty, empty

        dt = float(np.median(np.diff(t)))
        if not np.isfinite(dt) or dt <= 0:
            empty = np.asarray([], dtype=float)
            return empty, empty, empty

        n = len(v)
        ac = v - float(np.mean(v))
        window = np.hanning(n)
        coherent_sum = float(np.sum(window))
        if coherent_sum <= 0:
            empty = np.asarray([], dtype=float)
            return empty, empty, empty

        complex_spectrum = np.fft.rfft(ac * window)
        amplitude_peak_v = 2.0 * np.abs(complex_spectrum) / coherent_sum
        if len(amplitude_peak_v):
            amplitude_peak_v[0] *= 0.5
            if n % 2 == 0 and len(amplitude_peak_v) > 1:
                amplitude_peak_v[-1] *= 0.5

        floor_v = 10.0 ** (self.SPECTRUM_FLOOR_DBV / 20.0)
        amplitude_dbv = 20.0 * np.log10(np.maximum(amplitude_peak_v, floor_v))
        frequency_hz = np.fft.rfftfreq(n, d=dt)

        phase_deg = np.angle(complex_spectrum, deg=True).astype(float, copy=False)
        phase_deg = np.asarray(phase_deg, dtype=float).copy()
        phase_deg[amplitude_dbv < self.PHASE_VISIBLE_FLOOR_DBV] = np.nan
        return frequency_hz, amplitude_dbv, phase_deg

    def _draw_frequency_panel(self, ax, waveform: DcmSwWaveform) -> None:
        """绘制右上幅度频谱，并缓存同一次 FFT 得到的相位。"""
        frequency_hz, amplitude_dbv, phase_deg = self._compute_frequency_spectrum_with_phase(
            waveform
        )
        self.current_spectrum_frequency_hz = frequency_hz
        self.current_spectrum_amplitude_dbv = amplitude_dbv
        self.current_spectrum_phase_deg = phase_deg

        if len(frequency_hz) == 0:
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

        freq_mhz = frequency_hz / 1e6
        ax.plot(freq_mhz, amplitude_dbv, linewidth=0.85, label="DCM FFT")
        ax.set_xlim(float(freq_mhz[0]), float(freq_mhz[-1]))
        ax.set_xlabel("频率 (MHz)")
        ax.set_ylabel("幅度 (dBV)")
        ax.set_title("DCM 幅度频谱（去直流 / Hann FFT）")
        ax.grid(True, alpha=0.25)

        center_mhz = self.profile.center_frequency_hz / 1e6
        half_rbw_mhz = self.profile.rbw_hz / 2.0 / 1e6
        nyquist_mhz = float(freq_mhz[-1])
        lower = center_mhz - half_rbw_mhz
        upper = center_mhz + half_rbw_mhz

        if 0.0 <= center_mhz <= nyquist_mhz:
            ax.axvline(center_mhz, linestyle="--", linewidth=0.9, label="Zero Span Center")
        if upper >= 0.0 and lower <= nyquist_mhz:
            visible_lower = max(0.0, lower)
            visible_upper = min(nyquist_mhz, upper)
            if visible_upper > visible_lower:
                ax.axvspan(
                    visible_lower,
                    visible_upper,
                    alpha=0.12,
                    label="RBW",
                )

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

        ax.legend(loc="best")

        # 保持 v5/v8/v9 已确定的语义：手工输入只影响当前帧，正常 FFT 更新自动适配，
        # 且自动后的实际坐标会由 v9 回填左侧输入框。
        if hasattr(self, "freq_x_min"):
            self._apply_fixed_axis(
                ax,
                x_min=self.freq_x_min.value(),
                x_max=self.freq_x_max.value(),
                x_step=self.freq_x_step.value(),
                y_min=self.freq_y_min.value(),
                y_max=self.freq_y_max.value(),
                y_step=self.freq_y_step.value(),
            )

        if not getattr(self, "_frequency_manual_redraw_once", False):
            self._apply_frequency_auto_axis(ax)

    def _draw_reserved_panel(self, ax) -> None:
        """右下：绘制与右上完全同频点的 wrapped phase。"""
        frequency_hz = np.asarray(self.current_spectrum_frequency_hz, dtype=float)
        phase_deg = np.asarray(self.current_spectrum_phase_deg, dtype=float)

        if len(frequency_hz) == 0 or len(frequency_hz) != len(phase_deg):
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
            ax.set_ylim(-180.0, 180.0)
            ax.grid(True, alpha=0.25)
            return

        freq_mhz = frequency_hz / 1e6
        ax.plot(freq_mhz, phase_deg, linewidth=0.8, label="DCM Phase")
        ax.set_xlabel("频率 (MHz)")
        ax.set_ylabel("相位 (°)")
        ax.set_title(
            f"DCM 相位频谱（幅度 < {self.PHASE_VISIBLE_FLOOR_DBV:.0f} dBV 隐藏）"
        )
        ax.set_ylim(-180.0, 180.0, auto=False)
        ax.yaxis.set_major_locator(
            FixedLocator(np.asarray([-180, -120, -60, 0, 60, 120, 180], dtype=float))
        )
        ax.set_autoscaley_on(False)
        ax.grid(True, which="major", alpha=0.25)

        center_mhz = self.profile.center_frequency_hz / 1e6
        half_rbw_mhz = self.profile.rbw_hz / 2.0 / 1e6
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
        ax.legend(loc="best")

    def _redraw(
        self,
        *,
        zero_span_error: str | None = None,
        dcm_error: str | None = None,
    ) -> None:
        # v6 会在 super 内完成拖框缩放状态恢复；随后把右下与右上建立 sharex，
        # 并显式同步一次当前 xlim，确保本次 redraw 中已有的频率 zoom 也立即传递。
        super()._redraw(
            zero_span_error=zero_span_error,
            dcm_error=dcm_error,
        )
        if len(self.figure.axes) >= 4:
            ax_frequency = self.figure.axes[1]
            ax_phase = self.figure.axes[3]
            try:
                ax_phase.sharex(ax_frequency)
            except ValueError:
                # 新建 figure axes 正常不会进入；防御已经共享的情况。
                pass
            ax_phase.set_xlim(ax_frequency.get_xlim(), auto=False)
            self.canvas.draw_idle()
