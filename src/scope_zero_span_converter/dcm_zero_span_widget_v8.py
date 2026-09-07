from __future__ import annotations

import numpy as np
from matplotlib.ticker import MaxNLocator

from .dcm_analysis.axis import automatic_bounds
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
        # 兼容历史调用；正式策略已迁移到 dcm_analysis.axis。
        return automatic_bounds(
            amplitude_dbv,
            fallback=(-200.0, 20.0),
            relative_margin=0.05,
            minimum_margin=2.0,
        )

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

        # 覆盖固定 locator / limits，恢复当前 FFT 数据的自动显示。
        ax.xaxis.set_major_locator(MaxNLocator(nbins=10))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=10))
        ax.set_autoscalex_on(True)
        ax.set_autoscaley_on(True)
        ax.set_xlim(x_min, x_max, auto=True)
        ax.set_ylim(y_min, y_max, auto=True)
        ax.grid(True, which="major", alpha=0.25)

    def _on_frequency_axis_changed(self, *_args) -> None:
        # 手工输入只影响当前一次重绘。下一次正常数据重绘继续自动适配。
        self._frequency_manual_redraw_once = True
        try:
            super()._on_frequency_axis_changed(*_args)
        finally:
            self._frequency_manual_redraw_once = False

    def _draw_frequency_panel(self, ax, waveform: DcmSwWaveform) -> None:
        super()._draw_frequency_panel(ax, waveform)

        if not self._frequency_manual_redraw_once:
            self._apply_frequency_auto_axis(ax)
