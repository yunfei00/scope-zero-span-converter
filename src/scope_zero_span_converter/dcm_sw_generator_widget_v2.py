from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .dcm_sw_generator_widget import DcmSwGeneratorWidget as BaseDcmSwGeneratorWidget
from .dcm_sw_waveform_io import load_saved_dcm_sw_waveform, parameter_sidecar_for
from .logging_utils import get_logger


LOGGER = get_logger()


class DcmSwGeneratorWidget(BaseDcmSwGeneratorWidget):
    """在现有 DCM SW 生成器上增加历史合成波形加载能力。"""

    def _build_action_group(self, parent: QVBoxLayout) -> None:
        load_group = QGroupBox("加载已有合成波形")
        load_layout = QVBoxLayout(load_group)

        load_btn = QPushButton("加载已保存波形 CSV")
        load_btn.setMinimumHeight(36)
        load_btn.clicked.connect(self.load_waveform_dialog)
        load_layout.addWidget(load_btn)

        parent.addWidget(load_group)
        super()._build_action_group(parent)

    def load_waveform_dialog(self) -> None:
        csv_path, _ = QFileDialog.getOpenFileName(
            self,
            "加载已保存的 DCM SW 波形",
            "",
            "CSV (*.csv)",
        )
        if not csv_path:
            return

        csv_path_obj = Path(csv_path)
        parameters_path = parameter_sidecar_for(csv_path_obj)

        if not parameters_path.exists():
            answer = QMessageBox.question(
                self,
                "未找到真值参数",
                "没有在 CSV 同目录找到对应的参数 JSON。\n\n"
                f"期望文件：{parameters_path.name}\n\n"
                "是否手动选择参数 JSON？\n"
                "如果这是普通示波器 CSV，请改到“波形研究”页面加载。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return
            selected_json, _ = QFileDialog.getOpenFileName(
                self,
                "选择该波形对应的 DCM SW 参数 JSON",
                str(csv_path_obj.parent),
                "JSON (*.json)",
            )
            if not selected_json:
                return
            parameters_path = Path(selected_json)

        try:
            waveform, restored_parameters_path = load_saved_dcm_sw_waveform(
                csv_path_obj,
                parameters_path=parameters_path,
            )

            # 恢复参数控件时先关闭自动生成，确保历史 CSV 不会被当前算法覆盖。
            auto_generate = self.auto_generate_check.isChecked()
            self.auto_generate_check.setChecked(False)
            self._auto_timer.stop()
            try:
                self.apply_parameters(waveform.parameters)
                self._auto_timer.stop()
            finally:
                self.auto_generate_check.setChecked(auto_generate)

            self.current_waveform = waveform
            self._redraw(waveform)
            e = waveform.events
            self.status_label.setText(
                "已恢复保存波形："
                f"{csv_path_obj.name} | {waveform.points} 点 | "
                f"Fs={waveform.sample_rate_hz/1e9:.6g} GSa/s | "
                f"参数={restored_parameters_path.name} | "
                f"开关起始={e.rise_start_s*1e6:.6g} µs | "
                f"断续谐振开始={e.freewheel_end_s*1e6:.6g} µs。"
                "当前显示的是 CSV 中保存的原始历史波形；修改任一参数后才会重新生成。"
            )
            LOGGER.info(
                "加载已保存 DCM SW 波形 csv=%s parameters=%s points=%d",
                csv_path_obj,
                restored_parameters_path,
                waveform.points,
            )
        except Exception as exc:
            LOGGER.exception("加载已保存 DCM SW 波形失败")
            QMessageBox.critical(self, "加载 DCM SW 波形失败", str(exc))
