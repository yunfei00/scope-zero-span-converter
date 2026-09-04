from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .dcm_sw_generator import DcmSwWaveform
from .dcm_sw_generator_widget import DcmSwGeneratorWidget as BaseDcmSwGeneratorWidget
from .dcm_sw_waveform_io import load_saved_dcm_sw_waveform, parameter_sidecar_for
from .logging_utils import get_logger


LOGGER = get_logger()


class DcmSwGeneratorWidget(BaseDcmSwGeneratorWidget):
    """在现有 DCM SW 生成器上增加历史加载与按需真值分析显示。"""

    def _build_action_group(self, parent: QVBoxLayout) -> None:
        load_group = QGroupBox("加载已有合成波形")
        load_layout = QVBoxLayout(load_group)

        load_btn = QPushButton("加载已保存波形 CSV")
        load_btn.setMinimumHeight(36)
        load_btn.clicked.connect(self.load_waveform_dialog)
        load_layout.addWidget(load_btn)

        parent.addWidget(load_group)

        display_group = QGroupBox("显示设置")
        display_layout = QVBoxLayout(display_group)
        self.show_truth_components_check = QCheckBox("显示真值分量分析")
        self.show_truth_components_check.setChecked(False)
        self.show_truth_components_check.setToolTip(
            "默认只显示较大的 DCM SW 主波形；勾选后增加尖峰/振铃、断续谐振和底噪真值分量图。"
        )
        self.show_truth_components_check.stateChanged.connect(
            self._on_truth_components_changed
        )
        display_layout.addWidget(self.show_truth_components_check)
        parent.addWidget(display_group)

        super()._build_action_group(parent)

    def _on_truth_components_changed(self) -> None:
        if self.current_waveform is not None:
            self._redraw(self.current_waveform)

    def _redraw(self, waveform: DcmSwWaveform) -> None:
        """默认给主 SW 波形最大显示空间，真值分量按需展开。"""

        show_truth = (
            hasattr(self, "show_truth_components_check")
            and self.show_truth_components_check.isChecked()
        )
        if show_truth:
            super()._redraw(waveform)
            return

        self.figure.clear()
        ax = self.figure.add_subplot(111)
        x_us = waveform.time_s * 1e6

        ax.plot(x_us, waveform.voltage_v, linewidth=0.9, label="最终 SW 波形")
        ax.plot(
            x_us,
            waveform.ideal_voltage_v,
            linewidth=0.8,
            alpha=0.8,
            label="理想开关轨迹",
        )

        event_lines = (
            waveform.events.rise_start_s,
            waveform.events.rise_end_s,
            waveform.events.high_end_s,
            waveform.events.fall_end_s,
            waveform.events.freewheel_end_s,
        )
        for x_s in event_lines:
            ax.axvline(x_s * 1e6, linestyle="--", alpha=0.25)

        ax.set_title("DCM 模式 SW 合成波形（已知真值）")
        ax.set_xlabel("时间 (µs)")
        ax.set_ylabel("电压 (V)")
        ax.grid(True, alpha=0.3)
        ax.legend()

        self.figure.tight_layout()
        self.canvas.draw()

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
