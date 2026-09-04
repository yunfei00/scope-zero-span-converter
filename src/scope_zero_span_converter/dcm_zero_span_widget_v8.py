from __future__ import annotations

import math

import numpy as np
from matplotlib.ticker import MaxNLocator

from .dcm_sw_generator import DcmSwWaveform
from .dcm_zero_span_widget_v6 import DcmZeroSpanWidget as ZoomableDcmZeroSpanWidget


class DcmZeroSpanWidget(ZoomableDcmZeroSpanWidget):
    """频域始终自动适配；手工输入只调整当前显示。

    规则：
    - 右上 DCM 完整频域在正常重绘 / DCM 参数变化 / FFT 更新后始终自动适配；
    - 用户修改频域 X/Y Min、Max、Step 时，当前图立即按输入值显示；
    - 手工输入不进入持久“手动模式”，下一次正常数据重绘继续自动适配；
    - 不提供自动/手动模式开关；
    - 鼠标拖框临时放大与 Space 逐级返回继续保留；
    - 左侧 DCM 时域 / Zero Span 坐标规则保持不变。
    """

    def __init__(self, parent=None) -> None:
        # 父类构造阶段会动态调用本类绘图函数，因此标志必须提前建立。
        self._frequency_manual_redraw_once = False
        super().__init__(parent)
        self._redraw(zero_span_error=self.current_zero_span_error)

    @staticmethod
    def _automatic_y_bounds(amplitude_dbv: np.ndarray) -> tuple[float, float]:
        finite = np.asarray(amplitude_dbv, dtype=float)
        finite = finite[np.isfinite(finite)]
        if len(finite) == 0:
            return -200.0, 20.0

        low = float(np.min(finite))
        high = float(np.max(finite))
        if math.isclose(low, high):
            margin = max(abs(high) * 0.05, 5.0)
        else:
            margin = max((high - low) * 0.05, 2.0)
        return low - margin, high + margin

    def _apply_frequency_auto_axis(self, ax) -> None:
        frequency_hz = np.asarray(self.current_spectrum_frequency_hz, dtype=float)
        amplitude_dbv = np.asarray(self.current_spectrum_amplitude_dbv, dtype=float)
        if len(frequency_hz) == 0:
            return

        frequency_mhz = frequency_hz / 1e6
        finite_x = frequency_mhz[np.isfinite(frequency_mhz)]
        if len(finite_x) == 0:
            return

        x_min = float(np.min(finite_x))
        x_max = float(np.max(finite_x))
        if x_max <= x_min:
            x_max = x_min + 1.0
        y_min, y_max = self._automatic_y_bounds(amplitude_dbv)

        # 覆盖 v5 在绘图阶段应用的固定 locator / limits，恢复自动显示。
        ax.xaxis.set_major_locator(MaxNLocator(nbins=10))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=10))
        ax.set_autoscalex_on(True)
        ax.set_autoscaley_on(True)
        ax.set_xlim(x_min, x_max, auto=True)
        ax.set_ylim(y_min, y_max, auto=True)
        ax.grid(True, which="major", alpha=0.25)

    def _on_frequency_axis_changed(self, *_args) -> None:
        # 手工输入只影响当前一次重绘。父类会清除临时频域 zoom，并按输入的
        # Min/Max/Step 重画；下一次正常重绘时本标志已恢复 False，继续自动适配。
        self._frequency_manual_redraw_once = True
        try:
            super()._on_frequency_axis_changed(*_args)
        finally:
            self._frequency_manual_redraw_once = False

    def _draw_frequency_panel(self, ax, waveform: DcmSwWaveform) -> None:
        super()._draw_frequency_panel(ax, waveform)

        # 手工坐标输入触发的这一帧保留 v5 的固定范围；所有其它正常重绘
        # 都覆盖回自动频域坐标。
        if not self._frequency_manual_redraw_once:
            self._apply_frequency_auto_axis(ax)
