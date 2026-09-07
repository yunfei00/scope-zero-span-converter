from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem

from .dcm_parameter_extractor_widget_v6 import (
    DcmParameterExtractorWidget as ReconstructionDcmParameterExtractorWidget,
)
from .waveform_io import load_waveform_csv_checked
from .waveform_quality import WaveformQualityReport, analyze_time_axis, require_fft_safe


class DcmParameterExtractorWidget(ReconstructionDcmParameterExtractorWidget):
    """v7：保留绝对时间轴，并对参数提取输入执行统一采样质量门禁。"""

    def __init__(self, parent=None) -> None:
        self.input_quality_report: WaveformQualityReport | None = None
        super().__init__(parent)

    def load_and_extract_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "加载 DCM SW 波形 CSV",
            "",
            "CSV (*.csv)",
        )
        if not path:
            return

        try:
            data = load_waveform_csv_checked(
                path,
                min_points=64,
                require_named_columns=True,
            )
        except Exception as exc:
            QMessageBox.critical(self, "加载 CSV 失败", str(exc))
            return

        self.waveform_path = Path(path)
        self.time_s = data.time_s
        self.voltage_v = data.voltage_v
        self.input_quality_report = data.quality
        dropped_note = f"；清理无效行 {data.rows_dropped}" if data.rows_dropped else ""
        self.file_label.setText(
            f"{self.waveform_path}\n数据质量：{data.quality.summary()}{dropped_note}"
        )
        self.run_extraction()

    def set_waveform(
        self,
        time_s: np.ndarray,
        voltage_v: np.ndarray,
        *,
        source_name: str = "内存波形",
    ) -> None:
        """内存波形同样执行统一时间轴门禁，避免绕过 CSV 安全检查。"""

        t = np.asarray(time_s, dtype=float)
        v = np.asarray(voltage_v, dtype=float)
        if t.ndim != 1 or v.ndim != 1 or len(t) != len(v):
            raise ValueError("time_s 和 voltage_v 必须是一维且点数一致")
        if len(t) < 64:
            raise ValueError("波形至少需要 64 个点")
        if not np.all(np.isfinite(t)) or not np.all(np.isfinite(v)):
            raise ValueError("波形包含 NaN 或 Inf")

        quality = analyze_time_axis(t)
        require_fft_safe(quality)
        order = np.argsort(t)

        self.input_quality_report = quality
        super().set_waveform(
            t[order],
            v[order],
            source_name=f"{source_name} | 数据质量：{quality.summary()}",
        )

    def run_extraction(self) -> None:
        super().run_extraction()
        if self.input_quality_report is None or self.time_s is None:
            return
        # 父类每次分析都会重建状态文字，因此在最后追加质量摘要不会重复累积。
        self.status_label.setText(
            f"{self.status_label.text()} | 输入质量：{self.input_quality_report.summary()} | "
            f"Nyquist={self.input_quality_report.nyquist_hz/1e6:.6g} MHz"
        )

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
