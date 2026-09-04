from __future__ import annotations

import math

import numpy as np

from .dcm_zero_span_widget_v8 import DcmZeroSpanWidget as AutoFrequencyDcmZeroSpanWidget


class DcmZeroSpanWidget(AutoFrequencyDcmZeroSpanWidget):
    """频域自动适配后，将实际显示坐标同步回填到左侧输入框。

    规则保持不变：
    - 正常 DCM/FFT 更新后，右上完整频域始终自动适配；
    - 自动适配完成后，把图上实际 X/Y Min、Max、主刻度 Step 回填到输入框；
    - 回填时阻断 Qt 信号，不触发手动坐标重画，也不形成递归；
    - 用户手动输入坐标时，当前帧仍立即按输入值显示；
    - 下一次正常 DCM/FFT 更新继续自动适配，并再次回填最新实际值。
    """

    @staticmethod
    def _major_tick_step(ticks, minimum: float, maximum: float) -> float | None:
        values = np.asarray(ticks, dtype=float)
        values = values[np.isfinite(values)]
        if len(values) < 2:
            return None

        # MaxNLocator 有时会给出视窗边界之外的候选刻度；步长本身仍然有效。
        differences = np.diff(np.sort(np.unique(values)))
        differences = differences[np.isfinite(differences) & (differences > 0)]
        if len(differences) == 0:
            return None

        step = float(np.median(differences))
        if not math.isfinite(step) or step <= 0:
            return None
        return step

    def _sync_frequency_axis_controls_from_plot(self, ax) -> None:
        # 父类构造早期频域控件尚未创建，直接跳过；构造完成后的正常 redraw
        # 会再次调用本函数并完成首次回填。
        required = (
            "freq_x_min",
            "freq_x_max",
            "freq_x_step",
            "freq_y_min",
            "freq_y_max",
            "freq_y_step",
        )
        if not all(hasattr(self, name) for name in required):
            return

        x_min, x_max = map(float, ax.get_xlim())
        y_min, y_max = map(float, ax.get_ylim())
        if not all(math.isfinite(value) for value in (x_min, x_max, y_min, y_max)):
            return
        if x_max <= x_min or y_max <= y_min:
            return

        x_step = self._major_tick_step(ax.get_xticks(), x_min, x_max)
        y_step = self._major_tick_step(ax.get_yticks(), y_min, y_max)
        if x_step is None:
            x_step = self._nice_frequency_step((x_max - x_min) / 10.0)
        if y_step is None:
            y_step = self._nice_frequency_step((y_max - y_min) / 10.0)

        controls_and_values = (
            (self.freq_x_min, x_min),
            (self.freq_x_max, x_max),
            (self.freq_x_step, x_step),
            (self.freq_y_min, y_min),
            (self.freq_y_max, y_max),
            (self.freq_y_step, y_step),
        )

        for control, _value in controls_and_values:
            control.blockSignals(True)
        try:
            for control, value in controls_and_values:
                control.setValue(float(value))
        finally:
            for control, _value in controls_and_values:
                control.blockSignals(False)

    def _apply_frequency_auto_axis(self, ax) -> None:
        super()._apply_frequency_auto_axis(ax)
        self._sync_frequency_axis_controls_from_plot(ax)
