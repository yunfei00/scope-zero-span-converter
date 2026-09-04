from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .dcm_manual_tuner import DcmManualOnTimeTuningResult, tune_dcm_on_time_manually
from .dcm_parameter_extractor_widget_v3 import (
    DcmParameterExtractorWidget as GlobalDcmParameterExtractorWidget,
)
from .linked_parameter_control import LinkedDoubleControl
from .logging_utils import get_logger


LOGGER = get_logger()


class DcmParameterExtractorWidget(GlobalDcmParameterExtractorWidget):
    """第五层交互：自动反演结果基础上的导通时间人工实时校正。"""

    def __init__(self, parent=None) -> None:
        self.manual_result: DcmManualOnTimeTuningResult | None = None
        self.manual_error: str | None = None
        super().__init__(parent)

        self.manual_group = QGroupBox("人工校正（实时重合观察）")
        manual_layout = QVBoxLayout(self.manual_group)

        help_label = QLabel(
            "只要基础参数提取成功，导通时间即可人工修改，不依赖尖峰/振铃、DCM 谐振或全局联合精修。"
            "拖动滑块或输入精确数值后，下降沿及后续时刻联动移动，拟合曲线与当前匹配度实时刷新。"
        )
        help_label.setWordWrap(True)
        manual_layout.addWidget(help_label)

        self.manual_auto_label = QLabel("自动导通时间：-- | 自动置信度：--")
        self.manual_auto_label.setWordWrap(True)
        manual_layout.addWidget(self.manual_auto_label)

        on_time_row = QHBoxLayout()
        on_time_row.addWidget(QLabel("导通时间 (µs)"))
        self.manual_on_time = LinkedDoubleControl(
            0.0,
            1_000_000.0,
            6,
            0.001,
            slider_min=0.0,
            slider_max=10.0,
            parent=self.manual_group,
        )
        self.manual_on_time.setEnabled(False)
        on_time_row.addWidget(self.manual_on_time, 1)
        manual_layout.addLayout(on_time_row)

        button_row = QHBoxLayout()
        self.manual_reset_btn = QPushButton("恢复自动提取值")
        self.manual_reset_btn.setEnabled(False)
        self.manual_reset_btn.clicked.connect(self._restore_auto_on_time)
        button_row.addWidget(self.manual_reset_btn)

        self.manual_use_global_btn = QPushButton("使用联合精修值")
        self.manual_use_global_btn.setEnabled(False)
        self.manual_use_global_btn.clicked.connect(self._use_global_on_time)
        button_row.addWidget(self.manual_use_global_btn)
        manual_layout.addLayout(button_row)

        self.manual_match_label = QLabel(
            "当前人工匹配度：-- | 下降沿局部 RMSE：-- | 完整波形 R²：--"
        )
        self.manual_match_label.setWordWrap(True)
        manual_layout.addWidget(self.manual_match_label)

        self.manual_note_label = QLabel(
            "说明：“人工匹配度”是基于当前手调参数后的波形重合误差计算的工程指标，"
            "用于判断调参方向；它不会覆盖自动算法原始置信度。"
        )
        self.manual_note_label.setWordWrap(True)
        manual_layout.addWidget(self.manual_note_label)

        input_group = next(
            (group for group in self.findChildren(QGroupBox) if group.title() == "输入与分析"),
            None,
        )
        if input_group is not None and input_group.parentWidget() is not None:
            parent_layout = input_group.parentWidget().layout()
            if parent_layout is not None:
                index = parent_layout.indexOf(input_group)
                parent_layout.insertWidget(index + 1, self.manual_group)

        self._manual_timer = QTimer(self)
        self._manual_timer.setSingleShot(True)
        self._manual_timer.setInterval(70)
        self._manual_timer.timeout.connect(self._run_manual_tuning)
        self.manual_on_time.valueChanged.connect(self._schedule_manual_tuning)

    def run_extraction(self) -> None:
        self.manual_result = None
        self.manual_error = None
        super().run_extraction()

        # 人工导通时间校正只依赖第一阶段基础参数。
        # 不能因为后续尖峰/振铃或 DCM 谐振拟合失败而把滑块锁死。
        ready = self.result is not None
        if not hasattr(self, "manual_on_time"):
            return

        self.manual_on_time.setEnabled(ready)
        self.manual_reset_btn.setEnabled(ready)
        self.manual_use_global_btn.setEnabled(self.global_result is not None)

        if not ready or self.result is None:
            self.manual_auto_label.setText("自动导通时间：-- | 自动置信度：--")
            self.manual_match_label.setText(
                "当前人工匹配度：-- | 下降沿局部 RMSE：-- | 完整波形 R²：--"
            )
            return

        auto_confidence = self.result.confidence.get("on_time")
        confidence_text = "--" if auto_confidence is None else f"{auto_confidence*100:.1f}%"
        self.manual_auto_label.setText(
            f"自动导通时间：{self.result.on_time_s*1e6:.9g} µs | "
            f"自动置信度：{confidence_text}"
        )
        self.manual_on_time.setValue(self.result.on_time_s * 1e6)
        self._run_manual_tuning()

    def run_global_refinement(self) -> None:
        super().run_global_refinement()
        if hasattr(self, "manual_use_global_btn"):
            self.manual_use_global_btn.setEnabled(self.global_result is not None)
        if self.global_result is not None:
            self.manual_note_label.setText(
                "联合精修已完成：可点击“使用联合精修值”把导通时间滑块切到 "
                f"{self.global_result.on_time_s*1e6:.9g} µs，再继续人工微调。"
            )

    def _restore_auto_on_time(self) -> None:
        if self.result is None:
            return
        self.manual_on_time.setValue(self.result.on_time_s * 1e6)
        self._run_manual_tuning()

    def _use_global_on_time(self) -> None:
        if self.global_result is None:
            return
        self.manual_on_time.setValue(self.global_result.on_time_s * 1e6)
        self._run_manual_tuning()

    def _schedule_manual_tuning(self, *_args) -> None:
        if self.result is None:
            return
        self._manual_timer.start()

    def _run_manual_tuning(self) -> None:
        if self.time_s is None or self.voltage_v is None or self.result is None:
            return

        self.manual_error = None
        try:
            self.manual_result = tune_dcm_on_time_manually(
                self.time_s,
                self.voltage_v,
                self.result,
                self.ringing_result,
                self.dcm_result,
                on_time_s=self.manual_on_time.value() * 1e-6,
                global_result=self.global_result,
            )
        except Exception as exc:
            self.manual_result = None
            self.manual_error = str(exc)
            self.manual_match_label.setText(f"当前人工参数无效：{exc}")
            self._redraw()
            return

        tuned = self.manual_result
        mode_text = {
            "global_refinement": "联合精修模型",
            "staged_full_model": "完整分阶段模型",
            "basic_fallback": "基础轨迹模式",
        }.get(tuned.source, tuned.source)
        self.manual_match_label.setText(
            f"当前人工匹配度：{tuned.matching_score*100:.1f}% | "
            f"下降沿局部 RMSE：{tuned.local_rmse_v*1e3:.6g} mV | "
            f"完整波形 R²：{tuned.full_r_squared:.7f} | "
            f"全局 RMSE：{tuned.full_rmse_v*1e3:.6g} mV | {mode_text}"
        )
        self.status_label.setText(
            "人工导通时间实时校正："
            f"Ton={tuned.on_time_s*1e6:.9g} µs，"
            f"匹配度={tuned.matching_score*100:.1f}%，"
            f"人工下降沿开始={tuned.fall_start_s*1e6:.9g} µs。"
            "继续拖动滑块，观察“人工校正重建波形”与 CSV 的重合程度即可。"
        )
        self._redraw()

    def _redraw(self) -> None:
        super()._redraw()
        tuned = self.manual_result
        if tuned is None or self.time_s is None or not self.figure.axes:
            return

        x_us = self.time_s * 1e6
        main_ax = self.figure.axes[0]
        main_ax.plot(
            x_us,
            tuned.reconstruction_v,
            linewidth=1.35,
            alpha=0.95,
            label="人工校正重建波形",
        )
        main_ax.axvline(
            tuned.fall_start_s * 1e6,
            linestyle="--",
            alpha=0.75,
            label="人工下降沿开始",
        )
        main_ax.legend()

        if self.show_residual_check.isChecked() and len(self.figure.axes) >= 2:
            residual_ax = self.figure.axes[1]
            residual_ax.plot(
                x_us,
                tuned.residual_v,
                linewidth=0.8,
                alpha=0.95,
                label="人工校正残差",
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
            "algorithm": "dcm_parameter_identification_v5",
            "basic": self.result.to_dict(),
            "edge_ringing": None if self.ringing_result is None else self.ringing_result.to_dict(),
            "discontinuous_resonance": None if self.dcm_result is None else self.dcm_result.to_dict(),
            "global_refinement": None if self.global_result is None else self.global_result.to_dict(),
            "manual_tuning": None if self.manual_result is None else self.manual_result.to_dict(),
        }
        if self.ringing_error:
            payload["edge_ringing_error"] = self.ringing_error
        if self.dcm_error:
            payload["discontinuous_resonance_error"] = self.dcm_error
        if self.global_error:
            payload["global_refinement_error"] = self.global_error
        if self.manual_error:
            payload["manual_tuning_error"] = self.manual_error
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
