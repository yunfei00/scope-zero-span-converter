from __future__ import annotations

import numpy as np

from .dcm_sw_generator import DcmSwWaveform
from .dcm_zero_span_widget_v3 import DcmZeroSpanWidget as LockedAxisDcmZeroSpanWidget


class DcmZeroSpanWidget(LockedAxisDcmZeroSpanWidget):
    """DCM → Zero Span 四格研究布局。

    布局：
    - 左上：DCM 时域波形；
    - 左下：Zero Span，和左上严格共享绝对时间 X 轴；
    - 右上：当前 DCM 波形的完整单边频域；
    - 右下：预留后续时频/ROI/指标分析。

    频域当前采用去直流后的 Hann 窗单边 FFT，纵轴为幅度 dBV。
    这张图用于观察当前 DCM 参数变化引起的频率成分变化，不把有限记录
    的 FFT bin 直接冒充频谱仪 RBW 功率。Zero Span 仍由原有已验证算法计算。
    """

    SPECTRUM_FLOOR_DBV = -300.0

    def __init__(self, parent=None) -> None:
        self.current_spectrum_frequency_hz = np.asarray([], dtype=float)
        self.current_spectrum_amplitude_dbv = np.asarray([], dtype=float)
        super().__init__(parent)
        # Base 初始化阶段已经通过动态分派调用本类 _redraw；再画一次确保
        # 最终四格布局和当前所有控件状态完全同步。
        self._redraw(zero_span_error=self.current_zero_span_error)

    @classmethod
    def _compute_frequency_spectrum(
        cls,
        waveform: DcmSwWaveform,
    ) -> tuple[np.ndarray, np.ndarray]:
        """计算去直流 Hann 窗单边幅度频谱，返回 Hz / dBV。"""
        t = np.asarray(waveform.time_s, dtype=float)
        v = np.asarray(waveform.voltage_v, dtype=float)
        if len(t) < 2 or len(t) != len(v):
            return np.asarray([], dtype=float), np.asarray([], dtype=float)

        dt = float(np.median(np.diff(t)))
        if not np.isfinite(dt) or dt <= 0:
            return np.asarray([], dtype=float), np.asarray([], dtype=float)

        n = len(v)
        ac = v - float(np.mean(v))
        window = np.hanning(n)
        coherent_sum = float(np.sum(window))
        if coherent_sum <= 0:
            return np.asarray([], dtype=float), np.asarray([], dtype=float)

        spectrum = np.fft.rfft(ac * window)
        amplitude_peak_v = 2.0 * np.abs(spectrum) / coherent_sum
        # 单边频谱中 DC 和偶数点的 Nyquist bin 不应翻倍。
        if len(amplitude_peak_v):
            amplitude_peak_v[0] *= 0.5
            if n % 2 == 0 and len(amplitude_peak_v) > 1:
                amplitude_peak_v[-1] *= 0.5

        floor_v = 10.0 ** (cls.SPECTRUM_FLOOR_DBV / 20.0)
        amplitude_dbv = 20.0 * np.log10(np.maximum(amplitude_peak_v, floor_v))
        frequency_hz = np.fft.rfftfreq(n, d=dt)
        return frequency_hz, amplitude_dbv

    def _draw_frequency_panel(self, ax, waveform: DcmSwWaveform) -> None:
        frequency_hz, amplitude_dbv = self._compute_frequency_spectrum(waveform)
        self.current_spectrum_frequency_hz = frequency_hz
        self.current_spectrum_amplitude_dbv = amplitude_dbv

        if len(frequency_hz) == 0:
            ax.text(
                0.5,
                0.5,
                "当前波形无法计算频域",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
            ax.set_title("DCM 完整频域")
            ax.set_xlabel("频率 (MHz)")
            ax.set_ylabel("幅度 (dBV)")
            ax.grid(True, alpha=0.25)
            return

        freq_mhz = frequency_hz / 1e6
        ax.plot(freq_mhz, amplitude_dbv, linewidth=0.85, label="DCM FFT")
        ax.set_xlim(float(freq_mhz[0]), float(freq_mhz[-1]))
        ax.set_xlabel("频率 (MHz)")
        ax.set_ylabel("幅度 (dBV)")
        ax.set_title("DCM 完整频域（去直流 / Hann FFT）")
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

    @staticmethod
    def _draw_reserved_panel(ax) -> None:
        ax.text(
            0.5,
            0.5,
            "预留分析区\n后续可放时频图 / ROI 频谱 / 指标",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        ax.set_title("预留分析区")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(False)

    def _redraw(
        self,
        *,
        zero_span_error: str | None = None,
        dcm_error: str | None = None,
    ) -> None:
        self.figure.clear()

        # 2×2 四格。左上和左下共享 X 轴，保证时域与 Zero Span 的
        # 绘图区宽度、左右边界、绝对时间刻度严格上下对齐。
        ax_time = self.figure.add_subplot(221)
        ax_freq = self.figure.add_subplot(222)
        ax_zero = self.figure.add_subplot(223, sharex=ax_time)
        ax_reserved = self.figure.add_subplot(224)

        waveform = self.current_waveform
        zero = self.current_zero_span

        if waveform is None:
            self.current_spectrum_frequency_hz = np.asarray([], dtype=float)
            self.current_spectrum_amplitude_dbv = np.asarray([], dtype=float)
            ax_time.text(
                0.5,
                0.5,
                "DCM 波形当前不可生成" + (f"\n{dcm_error}" if dcm_error else ""),
                ha="center",
                va="center",
                transform=ax_time.transAxes,
            )
            ax_time.set_title("DCM SW 时域波形")
            ax_time.set_ylabel("电压 (V)")

            ax_zero.text(
                0.5,
                0.5,
                "等待有效 DCM 波形",
                ha="center",
                va="center",
                transform=ax_zero.transAxes,
            )
            ax_zero.set_title("Zero Span")
            ax_zero.set_xlabel("绝对时间 (µs)")
            ax_zero.set_ylabel("功率 (dBm)")

            ax_freq.text(
                0.5,
                0.5,
                "等待有效 DCM 波形",
                ha="center",
                va="center",
                transform=ax_freq.transAxes,
            )
            ax_freq.set_title("DCM 完整频域")
            ax_freq.set_xlabel("频率 (MHz)")
            ax_freq.set_ylabel("幅度 (dBV)")
            self._draw_reserved_panel(ax_reserved)
            self._apply_axis_controls_if_ready(ax_time, ax_zero)
            self.figure.tight_layout()
            self.canvas.draw_idle()
            return

        x_us = waveform.time_s * 1e6
        ax_time.plot(x_us, waveform.voltage_v, linewidth=0.9, label="当前 DCM SW")
        ax_time.plot(
            x_us,
            waveform.ideal_voltage_v,
            linewidth=0.75,
            alpha=0.75,
            label="理想轨迹",
        )
        ax_time.set_ylabel("电压 (V)")
        ax_time.set_title("DCM SW 时域波形")
        ax_time.legend(loc="best")
        ax_time.tick_params(labelbottom=False)

        if zero is None:
            message = "Zero Span 当前不可计算"
            if zero_span_error:
                message += f"\n{zero_span_error}"
            ax_zero.text(
                0.5,
                0.5,
                message,
                ha="center",
                va="center",
                wrap=True,
                transform=ax_zero.transAxes,
            )
            ax_zero.set_xlim(float(x_us[0]), float(x_us[-1]))
            ax_zero.set_title("Zero Span（等待有效转换参数）")
        else:
            ax_zero.plot(
                zero.time_s * 1e6,
                zero.amplitude_dbm,
                linewidth=0.9,
                label="等效 FSW Zero Span",
            )
            ax_zero.set_title(
                f"Zero Span：Center {zero.center_frequency_hz/1e6:.6g} MHz / "
                f"RBW {zero.rbw_hz/1e6:.6g} MHz"
            )
            ax_zero.legend(loc="best")

        ax_zero.set_xlabel("绝对时间 (µs)")
        ax_zero.set_ylabel("功率 (dBm)")

        # 左列必须始终锁为同一个绝对时间窗口。
        ax_time.set_xlim(float(x_us[0]), float(x_us[-1]))
        ax_zero.set_xlim(float(x_us[0]), float(x_us[-1]))

        self._draw_frequency_panel(ax_freq, waveform)
        self._draw_reserved_panel(ax_reserved)

        # 沿用 v0.5 已确定的纵轴硬锁定规则；只作用于原来的左侧两张图。
        self._apply_axis_controls_if_ready(ax_time, ax_zero)

        self.figure.tight_layout()
        self.canvas.draw_idle()
