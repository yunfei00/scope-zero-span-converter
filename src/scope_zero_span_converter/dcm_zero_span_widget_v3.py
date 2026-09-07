from __future__ import annotations

from .dcm_analysis.axis import apply_fixed_y_axis, fixed_ticks
from .dcm_zero_span_widget_v2 import DcmZeroSpanWidget as AxisConfigDcmZeroSpanWidget


class DcmZeroSpanWidget(AxisConfigDcmZeroSpanWidget):
    """纵轴硬锁定版：数据越界时只裁剪显示，不允许自动扩展纵轴。"""

    # 兼容旧测试和历史内部调用；实现已经迁移到正式 dcm_analysis.axis 模块。
    _fixed_ticks = staticmethod(fixed_ticks)

    def _apply_y_axis_settings(self, ax, minimum: float, maximum: float, step: float) -> None:
        """严格固定纵轴范围与主网格，超出范围的数据仅裁剪显示。"""
        apply_fixed_y_axis(ax, minimum, maximum, step)
