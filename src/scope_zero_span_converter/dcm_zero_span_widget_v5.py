from __future__ import annotations

import math

import numpy as np
from matplotlib.ticker import FixedLocator
from PySide6.QtWidgets import QFormLayout

from .dcm_sw_generator import DcmSwWaveform
from .dcm_zero_span_widget_v4 import DcmZeroSpanWidget as FourPanelDcmZeroSpanWidget


class DcmZeroSpanWidget(FourPanelDcmZeroSpanWidget):
    """四格联动页：为右上 DCM 完整频域增加固定 X/Y 轴范围和步进。"""

    def __init__(self, parent=None) -> None:
        # 父类初始化过程中会通过动态分派调用本类 _draw_frequency_panel；
        # 此时频域坐标控件尚不存在，下面的 guard 会保持原有自适应显示。
        super().__init__(parent)
        self._build_frequency_axis_controls()
        self._initialize_frequency_axis_values()
        self._redraw(zero_span_error=self.current_zero_span_error)

    def _build_frequency_axis_controls(self) -> None:
        self.axis_display_toggle.setText("图表坐标轴显示设置（范围 / 方格步进）")
        form = self.axis_display_panel.layout()
        if not isinstance(form, QFormLayout):
            raise RuntimeError("图表显示设置面板布局不是 QFormLayout")

        self.freq_x_min = self._axis_spin(-1e9, 1e9, 6, 10.0)
        self.freq_x_max = self._axis_spin(-1e9, 1e9, 6, 10.0)
        self.freq_x_step = self._axis_spin(1e-9, 1e9, 6, 10.0)
        self.freq_y_min = self._axis_spin(-1e9, 1e9, 6, 10.0)
        self.freq_y_max = self._axis_spin(-1e9, 1e9, 6, 10.0)
        self.freq_y_step = self._axis_spin(1e-9, 1e9, 6, 10.0)

        form.addRow("频域 X 最小值 (MHz)", self.freq_x_min)
        form.addRow("频域 X 最大值 (MHz)", self.freq_x_max)
        form.addRow("频域 X 每格步进 (MHz)", self.freq_x_step)
        form.addRow("频域 Y 最小值 (dBV)", self.freq_y_min)
        form.addRow("频域 Y 最大值 (dBV)", self.freq_y_max)
        form.addRow("频域 Y 每格步进 (dB)", self.freq_y_step)

        for spin in (
            self.freq_x_min,
            self.freq_x_max,
            self.freq_x_step,
            self.freq_y_min,
            self.freq_y_max,
            self.freq_y_step,
        ):
            spin.valueChanged.connect(self._on_frequency_axis_changed)

    def _initialize_frequency_axis_values(self) -> None:
        frequency_mhz = self.current_spectrum_frequency_hz / 1e6
        amplitude_dbv = self.current_spectrum_amplitude_dbv

        if len(frequency_mhz):
            x_min = float(frequency_mhz[0])
            x_max = float(frequency_mhz[-1])
        else:
            x_min, x_max = 0.0, 1000.0

        # 初始每格约分成 10 格；用户一旦修改后就完全固定。
        span_x = max(x_max - x_min, 1.0)
        x_step = self._nice_frequency_step(span_x / 10.0)

        finite_y = np.asarray(amplitude_dbv, dtype=float)
        finite_y = finite_y[np.isfinite(finite_y)]
        if len(finite_y):
            raw_min = float(np.min(finite_y))
            raw_max = float(np.max(finite_y))
            y_step = 20.0
            y_min = math.floor(raw_min / y_step) * y_step
            y_max = math.ceil(raw_max / y_step) * y_step
            if y_max <= y_min:
                y_max = y_min + y_step
        else:
            y_min, y_max, y_step = -200.0, 20.0, 20.0

        spins = (
            self.freq_x_min,
            self.freq_x_max,
            self.freq_x_step,
            self.freq_y_min,
            self.freq_y_max,
            self.freq_y_step,
        )
        for spin in spins:
            spin.blockSignals(True)
        try:
            self.freq_x_min.setValue(x_min)
            self.freq_x_max.setValue(x_max)
            self.freq_x_step.setValue(x_step)
            self.freq_y_min.setValue(y_min)
            self.freq_y_max.setValue(y_max)
            self.freq_y_step.setValue(y_step)
        finally:
            for spin in spins:
                spin.blockSignals(False)

    @staticmethod
    def _nice_frequency_step(value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            return 1.0
        exponent = math.floor(math.log10(value))
        scale = 10.0 ** exponent
        normalized = value / scale
        if normalized <= 1.0:
            nice = 1.0
        elif normalized <= 2.0:
            nice = 2.0
        elif normalized <= 5.0:
            nice = 5.0
        else:
            nice = 10.0
        return nice * scale

    def _on_frequency_axis_changed(self, *_args) -> None:
        # 坐标轴显示设置只重画，不重新生成 DCM、不重新做 FFT/Zero Span。
        self._redraw(zero_span_error=self.current_zero_span_error)

    def _apply_fixed_axis(
        self,
        ax,
        *,
        x_min: float,
        x_max: float,
        x_step: float,
        y_min: float,
        y_max: float,
        y_step: float,
    ) -> None:
        valid_x = math.isfinite(x_min) and math.isfinite(x_max) and x_max > x_min
        valid_y = math.isfinite(y_min) and math.isfinite(y_max) and y_max > y_min

        if valid_x:
            ax.set_autoscalex_on(False)
            x_ticks = self._fixed_ticks(x_min, x_max, x_step)
            if len(x_ticks):
                ax.xaxis.set_major_locator(FixedLocator(x_ticks))

        if valid_y:
            ax.set_autoscaley_on(False)
            y_ticks = self._fixed_ticks(y_min, y_max, y_step)
            if len(y_ticks):
                ax.yaxis.set_major_locator(FixedLocator(y_ticks))

        for line in ax.lines:
            line.set_clip_on(True)
        for patch in ax.patches:
            patch.set_clip_on(True)

        # 必须在 locator 和标记线/阴影完成后最后锁定，防止 Matplotlib 自动扩轴。
        if valid_x:
            ax.set_xlim(float(x_min), float(x_max), auto=False)
            ax.set_autoscalex_on(False)
        if valid_y:
            ax.set_ylim(float(y_min), float(y_max), auto=False)
            ax.set_autoscaley_on(False)

        ax.grid(True, which="major", alpha=0.25)

    def _draw_frequency_panel(self, ax, waveform: DcmSwWaveform) -> None:
        super()._draw_frequency_panel(ax, waveform)

        # 父类初始化第一次绘图时控件尚不存在。
        if not hasattr(self, "freq_x_min"):
            return

        self._apply_fixed_axis(
            ax,
            x_min=self.freq_x_min.value(),
            x_max=self.freq_x_max.value(),
            x_step=self.freq_x_step.value(),
            y_min=self.freq_y_min.value(),
            y_max=self.freq_y_max.value(),
            y_step=self.freq_y_step.value(),
        )
