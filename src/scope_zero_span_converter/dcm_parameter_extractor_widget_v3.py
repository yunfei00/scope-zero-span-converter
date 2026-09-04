from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import QApplication, QFileDialog, QGroupBox, QMessageBox, QPushButton, QTableWidgetItem

from .dcm_global_refiner import DcmGlobalRefinementResult, refine_dcm_parameters_globally
from .dcm_parameter_extractor import DcmBasicExtractionResult
from .dcm_parameter_extractor_widget_v2 import (
    DcmParameterExtractorWidget as StagedDcmParameterExtractorWidget,
)
from .dcm_ringing_extractor import DcmRingingExtractionResult
from .logging_utils import get_logger


LOGGER = get_logger()


class DcmParameterExtractorWidget(StagedDcmParameterExtractorWidget):
    """第四阶段：在逐阶段反演基础上增加全局联合精修。"""

    def __init__(self, parent=None) -> None:
        self.global_result: DcmGlobalRefinementResult | None = None
        self.global_error: str | None = None
        super().__init__(parent)

        self.global_refine_btn = QPushButton("运行全局联合精修（较慢）")
        self.global_refine_btn.setMinimumHeight(36)
        self.global_refine_btn.setEnabled(False)
        self.global_refine_btn.clicked.connect(self.run_global_refinement)

        input_group = next(
            (group for group in self.findChildren(QGroupBox) if group.title() == "输入与分析"),
            None,
        )
        if input_group is not None and input_group.layout() is not None:
            input_group.layout().addWidget(self.global_refine_btn)

        self.warning_label.setText(
            "前三阶段加载 CSV 后自动完成；全局联合精修属于较重的第四阶段，"
            "需要时点击“运行全局联合精修”。它会以前三阶段参数为初值，在有限范围内"
            "联合降低整条波形及关键瞬态区域的拟合误差。"
        )

    def run_extraction(self) -> None:
        self.global_result = None
        self.global_error = None
        super().run_extraction()
        ready = (
            self.result is not None
            and self.ringing_result is not None
            and self.dcm_result is not None
        )
        if hasattr(self, "global_refine_btn"):
            self.global_refine_btn.setEnabled(ready)
        if ready:
            self.status_label.setText(
                self.status_label.text()
                + " 前三阶段已完成，可继续点击“运行全局联合精修”获得最终推荐参数。"
            )

    def run_global_refinement(self) -> None:
        if (
            self.time_s is None
            or self.voltage_v is None
            or self.result is None
            or self.ringing_result is None
            or self.dcm_result is None
        ):
            QMessageBox.information(
                self,
                "尚不能联合精修",
                "请先完成基础参数、开关沿寄生振铃和 DCM 断续谐振三个阶段。",
            )
            return

        self.global_result = None
        self.global_error = None
        self.global_refine_btn.setEnabled(False)
        self.global_refine_btn.setText("全局联合精修中…")
        self.status_label.setText(
            "正在运行全局联合精修：使用分层抽样搜索非线性参数，并在最终结果上重建完整时间轴。"
        )
        QApplication.processEvents()

        try:
            self.global_result = refine_dcm_parameters_globally(
                self.time_s,
                self.voltage_v,
                self.result,
                self.ringing_result,
                self.dcm_result,
                max_iterations=8,
                max_optimization_points=18_000,
            )
        except Exception as exc:
            self.global_error = str(exc)
            LOGGER.exception("DCM 全局联合精修失败，保留前三阶段结果")
            QMessageBox.warning(
                self,
                "全局联合精修未完成",
                f"前三阶段结果仍然有效。\n\n{exc}",
            )
        finally:
            self.global_refine_btn.setText("重新运行全局联合精修（较慢）")
            self.global_refine_btn.setEnabled(True)

        self._populate_results(self.result, self.ringing_result)
        self._redraw()
        self._update_status(self.result, self.ringing_result)
        if self.global_result is not None:
            LOGGER.info(
                "DCM global refinement source=%s staged_rmse=%g optimized_rmse=%g improvement=%g%% evaluations=%d",
                self.waveform_path or "memory",
                self.global_result.staged_rmse_v,
                self.global_result.optimized_rmse_v,
                self.global_result.rmse_improvement_percent,
                self.global_result.evaluations,
            )

    def _populate_results(
        self,
        result: DcmBasicExtractionResult,
        ringing: DcmRingingExtractionResult | None,
    ) -> None:
        super()._populate_results(result, ringing)
        refined = self.global_result
        if refined is None:
            return

        rows = [
            ("【联合】基线电压", f"{refined.baseline_voltage_v:.9g} V", None),
            ("【联合】开通高电平电压", f"{refined.on_high_voltage_v:.9g} V", None),
            ("【联合】续流低电平电压", f"{refined.freewheel_low_voltage_v:.9g} V", None),
            ("【联合】开关起始时间", f"{refined.switching_start_s*1e6:.9g} µs", None),
            ("【联合】上升时间", f"{refined.rise_time_s*1e9:.9g} ns", None),
            ("【联合】导通时间", f"{refined.on_time_s*1e6:.9g} µs", None),
            ("【联合】下降时间", f"{refined.fall_time_s*1e9:.9g} ns", None),
            ("【联合】续流时间", f"{refined.freewheel_time_s*1e6:.9g} µs", None),
            ("【联合】上升沿尖峰电压", f"{refined.rise_spike_amplitude_v:.9g} V", None),
            ("【联合】下降沿尖峰电压", f"{refined.fall_spike_amplitude_v:.9g} V", None),
            ("【联合】寄生振铃频率", f"{refined.ringing_frequency_hz/1e6:.9g} MHz", None),
            ("【联合】寄生振铃衰减", f"{refined.ringing_decay_rate_per_s/1e6:.9g} /µs", None),
            ("【联合】DCM 初始振幅", f"{refined.dcm_initial_amplitude_v:.9g} V", None),
            ("【联合】DCM 谐振频率", f"{refined.dcm_frequency_hz/1e6:.9g} MHz", None),
            ("【联合】DCM 衰减速率", f"{refined.dcm_decay_rate_per_s/1e6:.9g} /µs", None),
            ("【联合】最终残差 robust RMS", f"{refined.final_noise_rms_v*1e3:.9g} mV", None),
            ("【联合】完整波形 R²", f"{refined.full_r_squared:.8f}", None),
            ("【联合】精修前 RMSE", f"{refined.staged_rmse_v*1e3:.9g} mV", None),
            ("【联合】精修后 RMSE", f"{refined.optimized_rmse_v*1e3:.9g} mV", None),
            ("【联合】RMSE 改善", f"{refined.rmse_improvement_percent:.6g}%", None),
            (
                "【联合】优化状态",
                f"{'已收敛' if refined.converged else '达到迭代上限'} | "
                f"{refined.iterations} 轮 / {refined.evaluations} 次评估 / {refined.optimized_points} 优化点",
                None,
            ),
        ]

        start_row = self.result_table.rowCount()
        self.result_table.setRowCount(start_row + len(rows))
        for offset, (name, value, confidence) in enumerate(rows):
            row = start_row + offset
            self.result_table.setItem(row, 0, QTableWidgetItem(name))
            self.result_table.setItem(row, 1, QTableWidgetItem(value))
            self.result_table.setItem(row, 2, QTableWidgetItem("--"))

    def _update_status(
        self,
        result: DcmBasicExtractionResult,
        ringing: DcmRingingExtractionResult | None,
    ) -> None:
        super()._update_status(result, ringing)
        refined = self.global_result
        if refined is None:
            if self.dcm_result is not None:
                suffix = " 可运行全局联合精修，比较优化前后 RMSE 并得到最终推荐参数。"
                if suffix.strip() not in self.status_label.text():
                    self.status_label.setText(self.status_label.text() + suffix)
            if self.global_error:
                self.warning_label.setText(
                    self.warning_label.text() + f"\n• 全局联合精修未完成：{self.global_error}"
                )
            return

        warnings = list(refined.warnings)
        if warnings:
            existing = self.warning_label.text()
            self.warning_label.setText(
                existing + "\n联合精修：\n" + "\n".join(f"• {item}" for item in warnings)
            )

        self.status_label.setText(
            "第四阶段完成：全局联合精修已把前三阶段参数作为初值重新优化。"
            f"RMSE {refined.staged_rmse_v*1e3:.6g} → {refined.optimized_rmse_v*1e3:.6g} mV，"
            f"改善 {refined.rmse_improvement_percent:.6g}%，完整波形 R²={refined.full_r_squared:.7f}。"
        )

    def _redraw(self) -> None:
        super()._redraw()
        refined = self.global_result
        if refined is None or self.time_s is None or not self.figure.axes:
            return

        x_us = self.time_s * 1e6
        main_ax = self.figure.axes[0]
        main_ax.plot(
            x_us,
            refined.optimized_reconstruction_v,
            linewidth=1.25,
            alpha=0.95,
            label="全局联合精修重建波形",
        )
        main_ax.legend()

        if self.show_residual_check.isChecked() and len(self.figure.axes) >= 2:
            residual_ax = self.figure.axes[1]
            residual_ax.plot(
                x_us,
                refined.final_residual_v,
                linewidth=0.75,
                alpha=0.95,
                label="联合精修最终残差",
            )
            residual_ax.set_title(
                "逐阶段残差 + 全局联合精修：最终残差用于判断模型遗漏与示波器底噪"
            )
            residual_ax.legend()

        self.figure.tight_layout()
        self.canvas.draw()

    def save_result_dialog(self) -> None:
        if self.result is None:
            QMessageBox.information(self, "没有结果", "请先完成一次参数提取。")
            return
        default_name = (
            f"{self.waveform_path.stem}_dcm_parameters.json"
            if self.waveform_path is not None
            else "dcm_extracted_parameters.json"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存 DCM 参数提取结果",
            default_name,
            "JSON (*.json)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"

        payload = {
            "algorithm": "dcm_parameter_identification_v4",
            "basic": self.result.to_dict(),
            "edge_ringing": None if self.ringing_result is None else self.ringing_result.to_dict(),
            "discontinuous_resonance": None if self.dcm_result is None else self.dcm_result.to_dict(),
            "global_refinement": None if self.global_result is None else self.global_result.to_dict(),
        }
        if self.ringing_error:
            payload["edge_ringing_error"] = self.ringing_error
        if self.dcm_error:
            payload["discontinuous_resonance_error"] = self.dcm_error
        if self.global_error:
            payload["global_refinement_error"] = self.global_error
        if self.waveform_path is not None:
            payload["source_csv"] = str(self.waveform_path)

        try:
            Path(path).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self.status_label.setText(f"已保存参数提取结果：{path}")
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
