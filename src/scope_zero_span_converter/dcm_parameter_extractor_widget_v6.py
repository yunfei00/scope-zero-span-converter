from __future__ import annotations

from pathlib import Path

import pandas as pd
from PySide6.QtWidgets import QFileDialog, QGroupBox, QHBoxLayout, QMessageBox, QPushButton

from .dcm_parameter_extractor_widget_v5 import (
    DcmParameterExtractorWidget as UnifiedDcmParameterExtractorWidget,
)
from .dcm_sw_generator import evaluate_dcm_sw_deterministic_components


class DcmParameterExtractorWidget(UnifiedDcmParameterExtractorWidget):
    """v6：生成器同源参数提取 + 当前重建波形 CSV 保存。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.save_reconstruction_csv_btn = QPushButton("保存当前重建 CSV")
        self.save_reconstruction_csv_btn.setEnabled(False)
        self.save_reconstruction_csv_btn.clicked.connect(self.save_current_csv_dialog)

        input_group = next(
            (group for group in self.findChildren(QGroupBox) if group.title() == "输入与分析"),
            None,
        )
        if input_group is not None and input_group.layout() is not None:
            row = QHBoxLayout()
            row.addWidget(self.save_reconstruction_csv_btn)
            input_group.layout().addLayout(row)

    def run_extraction(self) -> None:
        super().run_extraction()
        self._sync_save_csv_enabled()

    def run_global_refinement(self) -> None:
        super().run_global_refinement()
        self._sync_save_csv_enabled()

    def _run_current_model(self) -> None:
        super()._run_current_model()
        self._sync_save_csv_enabled()

    def _sync_save_csv_enabled(self) -> None:
        if hasattr(self, "save_reconstruction_csv_btn"):
            self.save_reconstruction_csv_btn.setEnabled(
                self.time_s is not None
                and self.voltage_v is not None
                and self.current_parameters is not None
                and self.current_fit_result is not None
            )

    def save_current_csv(self, path: str | Path) -> Path:
        """保存当前生成器同源重建波形及原始/残差/分量对照。"""

        if (
            self.time_s is None
            or self.voltage_v is None
            or self.current_parameters is None
            or self.current_fit_result is None
        ):
            raise ValueError("请先完成参数提取并得到当前重建波形")

        path = Path(path)
        if path.suffix.lower() != ".csv":
            path = path.with_suffix(".csv")
        path.parent.mkdir(parents=True, exist_ok=True)

        components = evaluate_dcm_sw_deterministic_components(
            self.time_s,
            self.current_parameters,
        )
        pd.DataFrame(
            {
                # 前两列保持标准波形格式，可直接送入普通 waveform 研究流程。
                "time_s": self.time_s,
                "voltage_v": self.current_fit_result.reconstruction_v,
                # 下面保留研究对照信息。
                "source_voltage_v": self.voltage_v,
                "residual_v": self.current_fit_result.residual_v,
                "ideal_voltage_v": components.ideal_voltage_v,
                "spike_component_v": components.spike_component_v,
                "discontinuous_component_v": components.discontinuous_component_v,
            }
        ).to_csv(path, index=False, encoding="utf-8-sig")
        return path

    def save_current_csv_dialog(self) -> None:
        if self.current_fit_result is None:
            QMessageBox.information(self, "没有重建波形", "请先完成一次 DCM 参数提取。")
            return

        default_name = (
            f"{self.waveform_path.stem}_dcm_reconstructed.csv"
            if self.waveform_path is not None
            else "dcm_reconstructed.csv"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存当前 DCM 重建波形",
            default_name,
            "CSV (*.csv)",
        )
        if not path:
            return

        try:
            saved = self.save_current_csv(path)
            self.status_label.setText(
                f"已保存当前重建 CSV：{saved}。time_s/voltage_v 为当前重建波形，"
                "同时保留原始波形、残差与各确定性分量。"
            )
        except Exception as exc:
            QMessageBox.critical(self, "保存 CSV 失败", str(exc))
