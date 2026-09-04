from __future__ import annotations

import math

import numpy as np
from matplotlib.ticker import MaxNLocator
from PySide6.QtWidgets import QCheckBox, QFormLayout

from .dcm_sw_generator import DcmSwWaveform
from .dcm_zero_span_widget_v6 import DcmZeroSpanWidget as ZoomableDcmZeroSpanWidget


class DcmZeroSpanWidget(ZoomableDcmZeroSpanWidget):
    """频域默认自动坐标；手工输入坐标后自动切换为固定模式。

    规则：
    - 右上 DCM 完整频域默认自动调整 X/Y 范围和主刻度；
    - 修改任一频域 X/Y Min/Max/Step，自动关闭自动模式并应用手工设置；
    - 可随时重新勾选“频域坐标自动调整”回到自动模式；
    - 鼠标拖框临时放大与 Space 逐级返回继续保留；
    - 左侧 DCM 时域 / Zero Span 坐标规则保持不变。
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_frequency_auto_mode_control()
        self._redraw(zero_span_error=self.current_zero_span_error)

    def _build_frequency_auto_mode_control(self) -> None:
        form = self.axis_display_panel.layout()
        if not isinstance(form, QFormLayout):
            raise RuntimeError("图表显示设置面板布局不是 QFormLayout")

        self.freq_auto_axis = QCheckBox("自动调整完整频域坐标")
        self.freq_auto_axis.setChecked(True)
        self.freq_auto_axis.setToolTip(
            "默认自动根据当前 FFT 数据调整右上频域图。"
            "手动修改任一频域 X/Y Min、Max 或 Step 后会自动切换到手动模式。"
        )
        self.freq_auto_axis.toggled.connect(self._on_frequency_auto_axis_toggled)

        # 放在频域参数之前更符合客户操作顺序。QFormLayout 前 6 行为原有
        # DCM / Zero Span 显示参数，因此从第 6 行插入模式开关。
        insert_row = min(6, form.rowCount())
        form.insertRow(insert_row, "DCM 完整频域", self.freq_auto_axis)

    def _on_frequency_auto_axis_toggled(self, checked: bool) -> None:
        # 切换模式时退出临时频域拖框放大，避免自动/手动基础范围和临时 zoom
        # 同时叠加造成用户无法判断当前坐标来源。
        self._clear_zoom_target("frequency")
        self._redraw(zero_span_error=self.current_zero_span_error)

    def _on_frequency_axis_changed(self, *_args) -> None:
        # 用户修改任一频域坐标参数，即明确表示要使用手动范围。
        if hasattr(self, "freq_auto_axis") and self.freq_auto_axis.isChecked():
            self.freq_auto_axis.blockSignals(True)
            try:
                self.freq_auto_axis.setChecked(False)
            finally:
                self.freq_auto_axis.blockSignals(False)
        super()._on_frequency_axis_changed(*_args)

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

        # 覆盖 v5 的固定 locator / fixed limits，恢复真正的自动显示模式。
        ax.xaxis.set_major_locator(MaxNLocator(nbins=10))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=10))
        ax.set_autoscalex_on(True)
        ax.set_autoscaley_on(True)
        ax.set_xlim(x_min, x_max, auto=True)
        ax.set_ylim(y_min, y_max, auto=True)
        ax.grid(True, which="major", alpha=0.25)

    def _draw_frequency_panel(self, ax, waveform: DcmSwWaveform) -> None:
        super()._draw_frequency_panel(ax, waveform)

        # 父类构造阶段本控件尚未建立；完成构造后的首次 redraw 才启用自动模式。
        if not hasattr(self, "freq_auto_axis"):
            return
        if self.freq_auto_axis.isChecked():
            self._apply_frequency_auto_axis(ax)
