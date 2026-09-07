from __future__ import annotations

import numpy as np
from matplotlib.ticker import FixedLocator

from .dcm_analysis.spectrum import compute_dcm_spectrum
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
    相位采用绝对门限 + 相对峰值动态范围联合判定，避免噪声底相位被误认为
    有效相位；相位参考明确为当前 FFT 记录起点。
    """

    PHASE_VISIBLE_FLOOR_DBV = -120.0
    PHASE_DYNAMIC_RANGE_DB = 60.0

    def __init__(self, parent=None) -> None:
        # 父类构造阶段会动态调用本类绘图方法，因此相位缓存必须提前建立。
        self.current_spectrum_phase_deg = np.asarray([], dtype=float)
        self.current_phase_visibility_threshold_dbv = self.PHASE_VISIBLE_FLOOR_DBV
        super().__init__(parent)
        self._redraw(zero_span_error=self.current_zero_span_error)

    def _compute_frequency_spectrum_with_phase(
        self,
        waveform: DcmSwWaveform,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """通过正式纯算法模块一次得到频率、幅度和 wrapped phase。"""
        spectrum = compute_dcm_spectrum(
            waveform.time_s,
            waveform.voltage_v,
            amplitude_floor_dbv=self.SPECTRUM_FLOOR_DBV,
            phase_visible_floor_dbv=self.PHASE_VISIBLE_FLOOR_DBV,
            phase_dynamic_range_db=self.PHASE_DYNAMIC_RANGE_DB,
        )
        self.current_phase_visibility_threshold_dbv = (
            spectrum.phase_visibility_threshold_dbv
        )
        return spectrum.frequency_hz, spectrum.amplitude_dbv, spectrum.phase_deg

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
            "DCM 相位频谱（Wrapped；参考=当前记录起点；"
            f"有效幅度 ≥ {self.current_phase_visibility_threshold_dbv:.1f} dBV）"
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
