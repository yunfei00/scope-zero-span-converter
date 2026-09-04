from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel, QVBoxLayout

from .dcm_sw_generator import DcmSwParameters
from .dcm_sw_generator_widget_v2 import DcmSwGeneratorWidget as HistoricalDcmSwGeneratorWidget


class DcmSwGeneratorWidget(HistoricalDcmSwGeneratorWidget):
    """v3：在生成器中显式保留绝对时间轴起点。"""

    def _build_timing_group(self, parent: QVBoxLayout) -> None:
        axis_group = QGroupBox("时间轴范围")
        axis_form = QFormLayout(axis_group)
        self.time_origin_us = self._double_spin(
            -1e9,
            1e9,
            6,
            0.1,
            slider_min=-100.0,
            slider_max=100.0,
        )
        axis_form.addRow("时间轴起点 (µs)", self.time_origin_us)
        note = QLabel(
            "例如原 CSV 的时间范围为 5~17 µs：时间轴起点=5 µs，总显示时长=12 µs。"
            "开关起始时间继续使用原 CSV 的绝对时间。"
        )
        note.setWordWrap(True)
        axis_form.addRow(note)
        parent.addWidget(axis_group)

        super()._build_timing_group(parent)

    def collect_parameters(self) -> DcmSwParameters:
        parameters = super().collect_parameters()
        parameters.time_origin_s = self.time_origin_us.value() * 1e-6
        return parameters

    def apply_parameters(self, parameters: DcmSwParameters) -> None:
        # 先更新起点，再由基类一次性恢复其它参数并触发最终重建。
        self._updating_controls = True
        try:
            self.time_origin_us.setValue(parameters.time_origin_s * 1e6)
        finally:
            self._updating_controls = False
        super().apply_parameters(parameters)
