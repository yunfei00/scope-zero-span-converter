from __future__ import annotations

from dataclasses import replace

from PySide6.QtWidgets import QTableWidgetItem

from .dcm_parameter_extractor_widget_v6 import (
    DcmParameterExtractorWidget as ReconstructionDcmParameterExtractorWidget,
)


class DcmParameterExtractorWidget(ReconstructionDcmParameterExtractorWidget):
    """v7：保留原始 CSV 的绝对时间轴起点/终点，并写入生成器参数。"""

    def _build_parameter_table(self) -> None:
        # v5/v6 的自动提取参数只知道“时间跨度”，这里把当前 CSV 的绝对起点
        # 写回统一的 DcmSwParameters。后续 JSON 保存、实时重建、生成器加载都使用它。
        if self.current_parameters is not None and self.time_s is not None and len(self.time_s):
            self.current_parameters = replace(
                self.current_parameters,
                time_origin_s=float(self.time_s[0]),
            )

        super()._build_parameter_table()

        if self.time_s is None or not len(self.time_s):
            return

        start_s = float(self.time_s[0])
        end_s = float(self.time_s[-1])

        self.result_table.insertRow(0)
        self.result_table.setItem(0, 0, QTableWidgetItem("【输入】时间轴起点"))
        self.result_table.setItem(0, 1, QTableWidgetItem(f"{start_s*1e6:.9g} µs"))
        self.result_table.setItem(0, 2, QTableWidgetItem("来自 CSV time_s[0]；保存到 JSON"))
        self.result_table.setRowHeight(0, 36)

        self.result_table.insertRow(1)
        self.result_table.setItem(1, 0, QTableWidgetItem("【输入】时间轴终点"))
        self.result_table.setItem(1, 1, QTableWidgetItem(f"{end_s*1e6:.9g} µs"))
        self.result_table.setItem(1, 2, QTableWidgetItem("来自 CSV time_s[-1]"))
        self.result_table.setRowHeight(1, 36)
