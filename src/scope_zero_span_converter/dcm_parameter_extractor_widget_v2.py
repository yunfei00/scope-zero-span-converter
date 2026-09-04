from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem

from .dcm_discontinuous_extractor import (
    DcmDiscontinuousExtractionResult,
    extract_dcm_discontinuous_resonance,
)
from .dcm_parameter_extractor import DcmBasicExtractionResult
from .dcm_parameter_extractor_widget import (
    DcmParameterExtractorWidget as BaseDcmParameterExtractorWidget,
)
from .dcm_ringing_extractor import DcmRingingExtractionResult
from .logging_utils import get_logger


LOGGER = get_logger()


class DcmParameterExtractorWidget(BaseDcmParameterExtractorWidget):
    """第三阶段：基础参数 + 开关沿振铃 + DCM 断续谐振完整逐级反演。"""

    def __init__(self, parent=None) -> None:
        self.dcm_result: DcmDiscontinuousExtractionResult | None = None
        self.dcm_error: str | None = None
        super().__init__(parent)
        self.show_residual_check.setText("显示逐阶段拟合残差 / 分量")
        self.warning_label.setText(
            "当前已实现：基础电平/时间分段 + 上下沿尖峰/寄生振铃 + DCM 断续谐振反演。"
            "所有确定性分量扣除后的最终残差用于估计示波器底噪。"
        )
        self.status_label.setText(
            "加载 time_s / voltage_v CSV 后，工具会按基础轨迹 → 开关沿寄生振铃 → "
            "DCM 断续谐振的顺序逐级反演，并给出最终残差噪声估计。"
        )

    def run_extraction(self) -> None:
        self.dcm_result = None
        self.dcm_error = None
        super().run_extraction()
        if self.result is None or self.time_s is None or self.voltage_v is None:
            return

        try:
            self.dcm_result = extract_dcm_discontinuous_resonance(
                self.time_s,
                self.voltage_v,
                self.result,
                self.ringing_result,
            )
        except Exception as exc:
            self.dcm_error = str(exc)
            LOGGER.exception("DCM 断续谐振提取失败，保留前两阶段结果")

        self._populate_results(self.result, self.ringing_result)
        self._redraw()
        self._update_status(self.result, self.ringing_result)
        LOGGER.info(
            "DCM discontinuous extraction source=%s confidence=%s",
            self.waveform_path or "memory",
            "--" if self.dcm_result is None else f"{self.dcm_result.confidence:.3f}",
        )

    def _populate_results(
        self,
        result: DcmBasicExtractionResult,
        ringing: DcmRingingExtractionResult | None,
    ) -> None:
        super()._populate_results(result, ringing)
        dcm = self.dcm_result
        if dcm is None:
            return

        rows = [
            (
                "【DCM】断续谐振初始振幅",
                f"{dcm.signed_initial_amplitude_v:.9g} V",
                dcm.confidence,
            ),
            (
                "【DCM】断续谐振频率",
                f"{dcm.resonance_frequency_hz/1e6:.9g} MHz",
                dcm.confidence,
            ),
            (
                "【DCM】断续谐振衰减速率",
                f"{dcm.decay_rate_per_s/1e6:.9g} /µs",
                dcm.confidence,
            ),
            (
                "【研究】DCM 拟合相位",
                f"{np.degrees(dcm.phase_rad):.6g}°",
                dcm.confidence,
            ),
            (
                "【研究】DCM 局部拟合 R²",
                f"{dcm.r_squared:.6f}",
                dcm.confidence,
            ),
            (
                "【噪声】最终残差 robust RMS",
                f"{dcm.final_noise_rms_v*1e3:.9g} mV",
                dcm.confidence,
            ),
            (
                "【研究】最终残差整体 RMSE",
                f"{dcm.final_residual_rmse_v*1e3:.9g} mV",
                None,
            ),
        ]

        start_row = self.result_table.rowCount()
        self.result_table.setRowCount(start_row + len(rows))
        for offset, (name, value, confidence) in enumerate(rows):
            row = start_row + offset
            self.result_table.setItem(row, 0, QTableWidgetItem(name))
            self.result_table.setItem(row, 1, QTableWidgetItem(value))
            conf_text = "--" if confidence is None else f"{confidence*100:.0f}%"
            self.result_table.setItem(row, 2, QTableWidgetItem(conf_text))

    def _update_status(
        self,
        result: DcmBasicExtractionResult,
        ringing: DcmRingingExtractionResult | None,
    ) -> None:
        dcm = self.dcm_result
        if dcm is not None and ringing is not None:
            combined = (
                0.35 * result.overall_confidence
                + 0.30 * ringing.overall_confidence
                + 0.35 * dcm.confidence
            )
            self.confidence_label.setText(
                f"综合参考置信度：{combined*100:.1f}% | "
                f"基础 {result.overall_confidence*100:.1f}% | "
                f"尖峰/振铃 {ringing.overall_confidence*100:.1f}% | "
                f"DCM {dcm.confidence*100:.1f}%"
            )
        elif dcm is not None:
            combined = 0.55 * result.overall_confidence + 0.45 * dcm.confidence
            self.confidence_label.setText(
                f"综合参考置信度：{combined*100:.1f}% | "
                f"基础 {result.overall_confidence*100:.1f}% | "
                f"DCM {dcm.confidence*100:.1f}% | 尖峰/振铃未完成"
            )
        else:
            super()._update_status(result, ringing)
            if self.dcm_error:
                self.warning_label.setText(
                    self.warning_label.text() + f"\n• DCM 断续谐振拟合未完成：{self.dcm_error}"
                )
            return

        warnings = list(result.warnings)
        if ringing is not None:
            warnings.extend(ringing.warnings)
        elif self.ringing_error:
            warnings.append(f"尖峰/寄生振铃拟合未完成：{self.ringing_error}")
        if dcm is not None:
            warnings.extend(dcm.warnings)
        elif self.dcm_error:
            warnings.append(f"DCM 断续谐振拟合未完成：{self.dcm_error}")

        if warnings:
            self.warning_label.setText("注意：\n" + "\n".join(f"• {item}" for item in dict.fromkeys(warnings)))
        else:
            self.warning_label.setText(
                "基础分段、开关沿寄生振铃和 DCM 断续谐振均未发现明显低置信度项。"
                "最终残差已用于估计示波器底噪。"
            )

        self.status_label.setText(
            "第三阶段完成："
            f"DCM A={dcm.signed_initial_amplitude_v:.6g} V，"
            f"f={dcm.resonance_frequency_hz/1e6:.6g} MHz，"
            f"α={dcm.decay_rate_per_s/1e6:.6g} /µs，"
            f"最终噪声≈{dcm.final_noise_rms_v*1e3:.6g} mV RMS。"
        )

    def _redraw(self) -> None:
        super()._redraw()
        if (
            self.result is None
            or self.time_s is None
            or self.dcm_result is None
            or not self.figure.axes
        ):
            return

        x_us = self.time_s * 1e6
        dcm = self.dcm_result
        spike = (
            np.zeros_like(self.time_s, dtype=float)
            if self.ringing_result is None
            else self.ringing_result.fitted_spike_component_v
        )
        full_reconstruction = (
            self.result.fitted_ideal_voltage_v
            + spike
            + dcm.fitted_discontinuous_component_v
        )

        main_ax = self.figure.axes[0]
        main_ax.plot(
            x_us,
            full_reconstruction,
            linewidth=1.05,
            alpha=0.9,
            label="基础 + 尖峰/振铃 + DCM 完整拟合",
        )
        main_ax.legend()

        if self.show_residual_check.isChecked() and len(self.figure.axes) >= 2:
            residual_ax = self.figure.axes[1]
            residual_ax.plot(
                x_us,
                dcm.fitted_discontinuous_component_v,
                linewidth=0.9,
                label="DCM 断续谐振拟合分量",
            )
            residual_ax.plot(
                x_us,
                dcm.final_residual_v,
                linewidth=0.65,
                alpha=0.9,
                label="最终残差 ≈ 噪声 + 模型误差",
            )
            residual_ax.set_title(
                "逐阶段残差：基础残差 → 扣除开关沿 → 扣除 DCM → 最终残差"
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
            "algorithm": "dcm_parameter_identification_v3",
            "basic": self.result.to_dict(),
            "edge_ringing": None if self.ringing_result is None else self.ringing_result.to_dict(),
            "discontinuous_resonance": None if self.dcm_result is None else self.dcm_result.to_dict(),
        }
        if self.ringing_error:
            payload["edge_ringing_error"] = self.ringing_error
        if self.dcm_error:
            payload["discontinuous_resonance_error"] = self.dcm_error
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
