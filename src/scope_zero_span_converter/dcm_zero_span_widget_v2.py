from __future__ import annotations

import math

import numpy as np
from matplotlib.ticker import MultipleLocator
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QGroupBox, QToolButton

from .dcm_zero_span_widget import DcmZeroSpanWidget as BaseDcmZeroSpanWidget


class DcmZeroSpanWidget(BaseDcmZeroSpanWidget):
    """DCM → Zero Span 联动页：增加两幅图独立纵轴范围与方格步进。"""

    def __init__(self, parent=None) -> None:
        # Base __init__ 会先触发一次 _redraw；此时纵轴控件尚未创建，
        # _redraw 中会自动退化为 Matplotlib 自适应范围。
        super().__init__(parent)
        self._build_axis_display_fold()
        self._initialize_axis_values_from_current_data()
        self._redraw(zero_span_error=self.current_zero_span_error)

    def _build_axis_display_fold(self) -> None:
        self.axis_display_toggle = QToolButton()
        self.axis_display_toggle.setText("图表纵轴显示（最小值 / 最大值 / 方格步进）")
        self.axis_display_toggle.setCheckable(True)
        self.axis_display_toggle.setChecked(False)
        self.axis_display_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.axis_display_toggle.setArrowType(Qt.RightArrow)
        self.axis_display_toggle.toggled.connect(self._toggle_axis_display_panel)

        self.axis_display_panel = QGroupBox()
        self.axis_display_panel.setVisible(False)
        form = QFormLayout(self.axis_display_panel)

        self.dcm_y_min = self._axis_spin(-1e9, 1e9, 6, 1.0)
        self.dcm_y_max = self._axis_spin(-1e9, 1e9, 6, 1.0)
        self.dcm_y_step = self._axis_spin(1e-9, 1e9, 6, 1.0)

        self.zero_y_min = self._axis_spin(-1e9, 1e9, 6, 10.0)
        self.zero_y_max = self._axis_spin(-1e9, 1e9, 6, 10.0)
        self.zero_y_step = self._axis_spin(1e-9, 1e9, 6, 10.0)

        form.addRow("DCM 纵轴最小值 (V)", self.dcm_y_min)
        form.addRow("DCM 纵轴最大值 (V)", self.dcm_y_max)
        form.addRow("DCM 每格步进 (V)", self.dcm_y_step)
        form.addRow("Zero Span 纵轴最小值 (dBm)", self.zero_y_min)
        form.addRow("Zero Span 纵轴最大值 (dBm)", self.zero_y_max)
        form.addRow("Zero Span 每格步进 (dB)", self.zero_y_step)

        for spin in (
            self.dcm_y_min,
            self.dcm_y_max,
            self.dcm_y_step,
            self.zero_y_min,
            self.zero_y_max,
            self.zero_y_step,
        ):
            spin.valueChanged.connect(self._on_axis_display_changed)

        # Base 页面最后一个 item 是 stretch；把显示设置插到 stretch 前面。
        insert_at = max(0, self.left_layout.count() - 1)
        self.left_layout.insertWidget(insert_at, self.axis_display_toggle)
        self.left_layout.insertWidget(insert_at + 1, self.axis_display_panel)

    @staticmethod
    def _axis_spin(minimum: float, maximum: float, decimals: int, step: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setKeyboardTracking(True)
        spin.setMinimumWidth(150)
        return spin

    def _toggle_axis_display_panel(self, checked: bool) -> None:
        self.axis_display_panel.setVisible(checked)
        self.axis_display_toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)

    @staticmethod
    def _nice_bounds(values: np.ndarray, step: float) -> tuple[float, float]:
        finite = np.asarray(values, dtype=float)
        finite = finite[np.isfinite(finite)]
        if len(finite) == 0:
            return -step, step
        low = float(np.min(finite))
        high = float(np.max(finite))
        if math.isclose(low, high):
            low -= step
            high += step
        margin = max((high - low) * 0.08, step * 0.5)
        low = math.floor((low - margin) / step) * step
        high = math.ceil((high + margin) / step) * step
        if high <= low:
            high = low + step
        return low, high

    def _initialize_axis_values_from_current_data(self) -> None:
        # 首次打开按当前数据给一个合理范围；之后完全由用户输入值控制。
        dcm_step = 2.0
        zero_step = 10.0
        if self.current_waveform is not None:
            dcm_min, dcm_max = self._nice_bounds(self.current_waveform.voltage_v, dcm_step)
        else:
            dcm_min, dcm_max = -10.0, 20.0
        if self.current_zero_span is not None:
            zero_min, zero_max = self._nice_bounds(self.current_zero_span.amplitude_dbm, zero_step)
        else:
            zero_min, zero_max = -120.0, 20.0

        for spin in (
            self.dcm_y_min,
            self.dcm_y_max,
            self.dcm_y_step,
            self.zero_y_min,
            self.zero_y_max,
            self.zero_y_step,
        ):
            spin.blockSignals(True)
        try:
            self.dcm_y_min.setValue(dcm_min)
            self.dcm_y_max.setValue(dcm_max)
            self.dcm_y_step.setValue(dcm_step)
            self.zero_y_min.setValue(zero_min)
            self.zero_y_max.setValue(zero_max)
            self.zero_y_step.setValue(zero_step)
        finally:
            for spin in (
                self.dcm_y_min,
                self.dcm_y_max,
                self.dcm_y_step,
                self.zero_y_min,
                self.zero_y_max,
                self.zero_y_step,
            ):
                spin.blockSignals(False)

    def _on_axis_display_changed(self, *_args) -> None:
        # 这里只改变显示，不重新生成 DCM，也不重新执行 Zero Span FFT 转换。
        self._redraw(zero_span_error=self.current_zero_span_error)

    def _apply_y_axis_settings(self, ax, minimum: float, maximum: float, step: float) -> None:
        if maximum > minimum:
            ax.set_ylim(minimum, maximum)
        if step > 0:
            ax.yaxis.set_major_locator(MultipleLocator(step))
        ax.grid(True, which="major", alpha=0.25)

    def _redraw(
        self,
        *,
        zero_span_error: str | None = None,
        dcm_error: str | None = None,
    ) -> None:
        self.figure.clear()
        ax1 = self.figure.add_subplot(211)
        ax2 = self.figure.add_subplot(212, sharex=ax1)

        waveform = self.current_waveform
        zero = self.current_zero_span

        if waveform is None:
            ax1.text(
                0.5,
                0.5,
                "DCM 波形当前不可生成" + (f"\n{dcm_error}" if dcm_error else ""),
                ha="center",
                va="center",
                transform=ax1.transAxes,
            )
            ax1.set_title("DCM SW 时域波形")
            ax1.set_ylabel("电压 (V)")
            ax2.text(
                0.5,
                0.5,
                "等待有效 DCM 波形",
                ha="center",
                va="center",
                transform=ax2.transAxes,
            )
            ax2.set_title("Zero Span")
            ax2.set_xlabel("绝对时间 (µs)")
            ax2.set_ylabel("功率 (dBm)")
            self._apply_axis_controls_if_ready(ax1, ax2)
            self.figure.tight_layout()
            self.canvas.draw_idle()
            return

        x_us = waveform.time_s * 1e6
        ax1.plot(x_us, waveform.voltage_v, linewidth=0.9, label="当前 DCM SW")
        ax1.plot(x_us, waveform.ideal_voltage_v, linewidth=0.75, alpha=0.75, label="理想轨迹")
        ax1.set_ylabel("电压 (V)")
        ax1.set_title("DCM SW 时域波形")
        ax1.legend(loc="best")

        if zero is None:
            message = "Zero Span 当前不可计算"
            if zero_span_error:
                message += f"\n{zero_span_error}"
            ax2.text(
                0.5,
                0.5,
                message,
                ha="center",
                va="center",
                wrap=True,
                transform=ax2.transAxes,
            )
            ax2.set_xlim(float(x_us[0]), float(x_us[-1]))
            ax2.set_title("Zero Span（等待有效转换参数）")
        else:
            ax2.plot(zero.time_s * 1e6, zero.amplitude_dbm, linewidth=0.9, label="等效 FSW Zero Span")
            ax2.set_title(
                f"Zero Span：Center {zero.center_frequency_hz/1e6:.6g} MHz / "
                f"RBW {zero.rbw_hz/1e6:.6g} MHz"
            )
            ax2.legend(loc="best")

        ax2.set_xlabel("绝对时间 (µs)")
        ax2.set_ylabel("功率 (dBm)")
        self._apply_axis_controls_if_ready(ax1, ax2)
        self.figure.tight_layout()
        self.canvas.draw_idle()

    def _apply_axis_controls_if_ready(self, ax1, ax2) -> None:
        # Base __init__ 首次调用 _redraw 时这些控件还不存在。
        if not hasattr(self, "dcm_y_min"):
            ax1.grid(True, alpha=0.25)
            ax2.grid(True, alpha=0.25)
            return

        self._apply_y_axis_settings(
            ax1,
            self.dcm_y_min.value(),
            self.dcm_y_max.value(),
            self.dcm_y_step.value(),
        )
        self._apply_y_axis_settings(
            ax2,
            self.zero_y_min.value(),
            self.zero_y_max.value(),
            self.zero_y_step.value(),
        )
