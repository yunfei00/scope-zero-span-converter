from __future__ import annotations

import math

import numpy as np
from matplotlib.ticker import FixedLocator

from .dcm_zero_span_widget_v2 import DcmZeroSpanWidget as AxisConfigDcmZeroSpanWidget


class DcmZeroSpanWidget(AxisConfigDcmZeroSpanWidget):
    """纵轴硬锁定版：数据越界时只裁剪显示，不允许自动扩展纵轴。"""

    @staticmethod
    def _fixed_ticks(minimum: float, maximum: float, step: float) -> np.ndarray:
        if not (math.isfinite(minimum) and math.isfinite(maximum) and math.isfinite(step)):
            return np.asarray([], dtype=float)
        if maximum <= minimum or step <= 0:
            return np.asarray([], dtype=float)

        span = maximum - minimum
        count = int(math.floor(span / step + 1e-12)) + 1
        # 防止极端小步进造成海量 tick，GUI 直接卡死。
        count = min(count, 10_001)
        ticks = minimum + np.arange(count, dtype=float) * step
        tolerance = max(abs(maximum), abs(minimum), 1.0) * 1e-12
        return ticks[ticks <= maximum + tolerance]

    def _apply_y_axis_settings(self, ax, minimum: float, maximum: float, step: float) -> None:
        """严格固定纵轴范围与主网格。

        规则：
        - minimum/maximum 一旦有效，就作为硬显示窗口；
        - 数据超过窗口只由 Matplotlib clip，不触发 autoscale；
        - 主刻度从 minimum 开始按 step 递增，且不会生成到 maximum 之外；
        - 最后再次 set_ylim，避免 locator/tick 更新改变视图范围。
        """
        valid_range = (
            math.isfinite(minimum)
            and math.isfinite(maximum)
            and maximum > minimum
        )

        if valid_range:
            ax.set_autoscaley_on(False)
            ax.margins(y=0.0)

        ticks = self._fixed_ticks(minimum, maximum, step)
        if len(ticks):
            ax.yaxis.set_major_locator(FixedLocator(ticks))

        # 所有曲线保持 clip_on，超过固定纵轴窗口的部分直接不可见。
        for line in ax.lines:
            line.set_clip_on(True)

        if valid_range:
            # 必须放在 locator 设置之后：最终视图边界严格等于用户输入值。
            ax.set_ylim(float(minimum), float(maximum), auto=False)
            ax.set_autoscaley_on(False)

        ax.grid(True, which="major", alpha=0.25)
