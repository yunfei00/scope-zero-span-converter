from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
)

from .dcm_parameter_extractor_widget_v3 import (
    DcmParameterExtractorWidget as GlobalDcmParameterExtractorWidget,
)
from .dcm_sw_generator import DcmSwParameters, event_times
from .dcm_unified_fit import (
    DcmUnifiedFitResult,
    evaluate_unified_dcm_fit,
    parameter_dependency_note,
    parameters_from_extraction,
)
from .linked_parameter_control import LinkedDoubleControl
from .logging_utils import get_logger


LOGGER = get_logger()


_PARAMETER_ROWS = (
    ("baseline_voltage_v", "【电平】基线电压", "V", "baseline"),
    ("on_high_voltage_v", "【电平】开通高电平电压", "V", "high"),
    ("freewheel_low_voltage_v", "【电平】续流低电平电压", "V", "freewheel"),
    ("switching_start_s", "【时间】开关起始时间", "µs", "rise_edge"),
    ("rise_time_s", "【时间】上升沿时间", "ns", "rise_edge"),
    ("on_time_s", "【时间】导通时间", "µs", "fall_edge"),
    ("fall_time_s", "【时间】下降沿时间", "ns", "fall_edge"),
    ("freewheel_time_s", "【时间】续流时间", "µs", "dcm"),
    ("rise_spike_amplitude_v", "【尖峰】上升沿尖峰电压", "V", "rise_edge"),
    ("fall_spike_amplitude_v", "【尖峰】下降沿尖峰电压", "V", "fall_edge"),
    ("spike_ringing_frequency_hz", "【振铃】尖峰寄生振铃频率", "MHz", "edges"),
    ("spike_decay_rate_per_s", "【振铃】尖峰寄生振铃衰减速率", "/µs", "edges"),
    ("discontinuous_initial_amplitude_v", "【DCM】断续谐振初始振幅", "V", "dcm"),
    ("discontinuous_resonance_frequency_hz", "【DCM】断续谐振频率", "MHz", "dcm"),
    ("discontinuous_decay_rate_per_s", "【DCM】断续谐振衰减速率", "/µs", "dcm"),
)


class DcmParameterExtractorWidget(GlobalDcmParameterExtractorWidget):
    """自动反演 + 与 DCM SW 生成器完全同源的参数人工校正。"""

    def __init__(self, parent=None) -> None:
        self.current_parameters: DcmSwParameters | None = None
        self.current_fit_result: DcmUnifiedFitResult | None = None
        self.current_fit_error: str | None = None
        self.parameter_controls: dict[str, LinkedDoubleControl] = {}
        self._score_items: dict[str, QTableWidgetItem] = {}
        self._score_regions: dict[str, str] = {}
        self._diagnostic_items: dict[str, QTableWidgetItem] = {}
        self._editor_syncing = False
        super().__init__(parent)

        self.result_table.setHorizontalHeaderLabels(
            ["参数", "滑块 + 数值输入", "自动置信度 / 当前拟合"]
        )
        self.result_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.result_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.result_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.result_table.setColumnWidth(2, 235)

        self.restore_all_btn = QPushButton("恢复全部自动提取值")
        self.restore_all_btn.setEnabled(False)
        self.restore_all_btn.clicked.connect(self._restore_all_auto_values)

        self.use_global_all_btn = QPushButton("载入联合精修值到当前参数")
        self.use_global_all_btn.setEnabled(False)
        self.use_global_all_btn.clicked.connect(self._use_global_values)

        input_group = next(
            (group for group in self.findChildren(QGroupBox) if group.title() == "输入与分析"),
            None,
        )
        if input_group is not None and input_group.layout() is not None:
            row = QHBoxLayout()
            row.addWidget(self.restore_all_btn)
            row.addWidget(self.use_global_all_btn)
            input_group.layout().addLayout(row)

        self._parameter_timer = QTimer(self)
        self._parameter_timer.setSingleShot(True)
        self._parameter_timer.setInterval(80)
        self._parameter_timer.timeout.connect(self._run_current_model)

        self.warning_label.setText(
            "当前参数表已与“DCM SW 生成器”统一：同一 DcmSwParameters、同一确定性正向模型、"
            "同一参数语义。自动算法中的相位仅作为内部拟合辅助量，不再作为客户主参数。"
            "频率/衰减在对应振幅为 0 时数学上不会影响波形，界面会明确提示依赖关系。"
        )

    def run_extraction(self) -> None:
        self.current_parameters = None
        self.current_fit_result = None
        self.current_fit_error = None
        super().run_extraction()
        if self.result is None:
            self.restore_all_btn.setEnabled(False)
            return

        self.current_parameters = parameters_from_extraction(
            self.result,
            self.ringing_result,
            self.dcm_result,
            None,
        )
        self.restore_all_btn.setEnabled(True)
        self.use_global_all_btn.setEnabled(False)
        self._build_parameter_table()
        self._run_current_model()

    def run_global_refinement(self) -> None:
        super().run_global_refinement()
        self.use_global_all_btn.setEnabled(self.global_result is not None)
        if self.global_result is None or self.result is None:
            return
        self.current_parameters = parameters_from_extraction(
            self.result,
            self.ringing_result,
            self.dcm_result,
            self.global_result,
        )
        self._build_parameter_table()
        self._run_current_model()
        self.status_label.setText(
            self.status_label.text()
            + " 联合精修值已映射到生成器原生参数，可继续逐项人工校正。"
        )

    def _restore_all_auto_values(self) -> None:
        if self.result is None:
            return
        self.current_parameters = parameters_from_extraction(
            self.result,
            self.ringing_result,
            self.dcm_result,
            None,
        )
        self._build_parameter_table()
        self._run_current_model()

    def _use_global_values(self) -> None:
        if self.result is None or self.global_result is None:
            return
        self.current_parameters = parameters_from_extraction(
            self.result,
            self.ringing_result,
            self.dcm_result,
            self.global_result,
        )
        self._build_parameter_table()
        self._run_current_model()

    def _build_parameter_table(self) -> None:
        if self.result is None or self.current_parameters is None:
            return

        self._editor_syncing = True
        try:
            self.parameter_controls.clear()
            self._score_items.clear()
            self._score_regions.clear()
            self._diagnostic_items.clear()
            self.result_table.clearContents()
            self.result_table.setRowCount(0)

            self._add_readonly_row(
                "【输入】总显示时长",
                f"{self.result.total_duration_s*1e6:.9g} µs",
                "来自 CSV 时间轴",
            )
            self._add_readonly_row(
                "【输入】采样率",
                f"{self.result.sample_rate_hz/1e9:.9g} GSa/s",
                "来自 CSV 时间轴",
            )

            for key, label, unit, score_region in _PARAMETER_ROWS:
                self._add_parameter_row(key, label, unit, score_region)

            self._add_readonly_row(
                "【噪声】Noise RMS",
                f"{self.current_parameters.noise_rms_v*1e3:.9g} mV",
                "自动估计；重建不重新注入随机噪声",
            )
            self._add_readonly_row(
                "【输入】Random Seed",
                "--",
                "真实 CSV 反演不适用",
            )
            self._add_readonly_row(
                "【派生】上升时间 10%~90%",
                f"{self.result.rise_time_10_90_s*1e9:.9g} ns",
                "自动测量",
            )
            self._add_readonly_row(
                "【派生】下降时间 10%~90%",
                f"{self.result.fall_time_10_90_s*1e9:.9g} ns",
                "自动测量",
            )

            for key, label in (
                ("overall_match", "【当前】完整模型匹配度"),
                ("full_rmse", "【当前】完整模型 RMSE"),
                ("full_r2", "【当前】完整波形 R²"),
                ("residual_noise", "【当前】残差 robust RMS"),
            ):
                row = self.result_table.rowCount()
                self.result_table.insertRow(row)
                self.result_table.setItem(row, 0, QTableWidgetItem(label))
                value_item = QTableWidgetItem("--")
                self.result_table.setItem(row, 1, value_item)
                self.result_table.setItem(row, 2, QTableWidgetItem("实时更新"))
                self._diagnostic_items[key] = value_item

            if self.global_result is not None:
                self._add_readonly_row(
                    "【联合】精修 RMSE 改善",
                    f"{self.global_result.rmse_improvement_percent:.6g}%",
                    "参考",
                )

            for row in range(self.result_table.rowCount()):
                self.result_table.setRowHeight(row, 36)
        finally:
            self._editor_syncing = False

    def _add_parameter_row(self, key: str, label: str, unit: str, score_region: str) -> None:
        assert self.current_parameters is not None
        row = self.result_table.rowCount()
        self.result_table.insertRow(row)
        self.result_table.setItem(row, 0, QTableWidgetItem(f"{label} ({unit})"))

        current_internal = float(getattr(self.current_parameters, key))
        current_display = self._to_display(key, current_internal)
        minimum, maximum, soft_min, soft_max, decimals, step = self._control_range(
            key,
            current_display,
        )
        control = LinkedDoubleControl(
            minimum,
            maximum,
            decimals,
            step,
            slider_min=soft_min,
            slider_max=soft_max,
            parent=self.result_table,
        )
        control.setValue(current_display)
        control.valueChanged.connect(
            lambda value, name=key: self._on_parameter_changed(name, value)
        )
        self.parameter_controls[key] = control
        self.result_table.setCellWidget(row, 1, control)

        confidence = self._auto_confidence(key)
        auto_text = "--" if confidence is None else f"{confidence*100:.1f}%"
        item = QTableWidgetItem(f"自动 {auto_text} | 当前 --")
        self.result_table.setItem(row, 2, item)
        self._score_items[key] = item
        self._score_regions[key] = score_region

    def _add_readonly_row(self, name: str, value: str, note: str) -> None:
        row = self.result_table.rowCount()
        self.result_table.insertRow(row)
        self.result_table.setItem(row, 0, QTableWidgetItem(name))
        self.result_table.setItem(row, 1, QTableWidgetItem(value))
        self.result_table.setItem(row, 2, QTableWidgetItem(note))

    def _on_parameter_changed(self, key: str, display_value: float) -> None:
        if self._editor_syncing or self.current_parameters is None:
            return
        internal_value = self._from_display(key, float(display_value))
        self.current_parameters = replace(self.current_parameters, **{key: internal_value})
        self._parameter_timer.start()

    def _run_current_model(self) -> None:
        if (
            self.time_s is None
            or self.voltage_v is None
            or self.result is None
            or self.current_parameters is None
        ):
            return
        try:
            self.current_fit_result = evaluate_unified_dcm_fit(
                self.time_s,
                self.voltage_v,
                self.current_parameters,
            )
            self.current_fit_error = None
        except Exception as exc:
            self.current_fit_result = None
            self.current_fit_error = str(exc)
            self.status_label.setText(f"当前参数组合无效：{exc}")
            self._update_current_scores(None)
            self._redraw()
            return

        fit = self.current_fit_result
        self._update_current_scores(fit)
        self.status_label.setText(
            "生成器同源参数实时校正："
            f"当前匹配度={fit.overall_matching_score*100:.2f}% | "
            f"RMSE={fit.full_rmse_v*1e3:.6g} mV | "
            f"R²={fit.full_r_squared:.7f}。"
            "所有主参数均使用 DCM SW 生成器同一正向模型；直接观察重建波形与 CSV 是否重合。"
        )
        self._redraw()

    def _update_current_scores(self, fit: DcmUnifiedFitResult | None) -> None:
        for key, item in self._score_items.items():
            confidence = self._auto_confidence(key)
            auto_text = "--" if confidence is None else f"{confidence*100:.1f}%"
            dependency = (
                None
                if self.current_parameters is None
                else parameter_dependency_note(self.current_parameters, key)
            )
            if dependency:
                current_text = dependency
            elif fit is None:
                current_text = "当前 --"
            else:
                region = self._score_regions.get(key, "overall")
                current = fit.region_scores.get(region, fit.overall_matching_score)
                current_text = f"当前 {current*100:.2f}%"
            item.setText(f"自动 {auto_text} | {current_text}")

        if fit is None:
            for item in self._diagnostic_items.values():
                item.setText("--")
            return
        self._diagnostic_items["overall_match"].setText(
            f"{fit.overall_matching_score*100:.3f}%"
        )
        self._diagnostic_items["full_rmse"].setText(f"{fit.full_rmse_v*1e3:.9g} mV")
        self._diagnostic_items["full_r2"].setText(f"{fit.full_r_squared:.9f}")
        self._diagnostic_items["residual_noise"].setText(
            f"{fit.final_noise_rms_v*1e3:.9g} mV"
        )

    def _redraw(self) -> None:
        super()._redraw()
        fit = self.current_fit_result
        if fit is None or self.time_s is None or not self.figure.axes:
            return

        x_us = self.time_s * 1e6
        main_ax = self.figure.axes[0]
        main_ax.plot(
            x_us,
            fit.reconstruction_v,
            linewidth=1.45,
            alpha=0.95,
            label="生成器同源当前重建波形",
        )
        events = event_times(fit.parameters)
        main_ax.axvline(
            events.rise_start_s * 1e6,
            linestyle=":",
            alpha=0.55,
            label="当前开关起始",
        )
        main_ax.axvline(
            events.high_end_s * 1e6,
            linestyle=":",
            alpha=0.55,
            label="当前下降沿开始",
        )
        main_ax.axvline(
            events.freewheel_end_s * 1e6,
            linestyle=":",
            alpha=0.55,
            label="当前 DCM 起点",
        )
        main_ax.legend()

        if self.show_residual_check.isChecked() and len(self.figure.axes) >= 2:
            residual_ax = self.figure.axes[1]
            residual_ax.plot(
                x_us,
                fit.residual_v,
                linewidth=0.8,
                alpha=0.95,
                label="生成器同源当前残差",
            )
            residual_ax.legend()

        self.figure.tight_layout()
        self.canvas.draw()

    def _auto_confidence(self, key: str) -> float | None:
        if self.result is None:
            return None
        basic_map = {
            "baseline_voltage_v": "baseline_voltage",
            "on_high_voltage_v": "on_high_voltage",
            "freewheel_low_voltage_v": "freewheel_low_voltage",
            "switching_start_s": "switching_start",
            "rise_time_s": "rise_time",
            "on_time_s": "on_time",
            "fall_time_s": "fall_time",
            "freewheel_time_s": "freewheel_time",
        }
        if key in basic_map:
            return self.result.confidence.get(basic_map[key])
        if key == "rise_spike_amplitude_v":
            return None if self.ringing_result is None else self.ringing_result.rise.confidence
        if key == "fall_spike_amplitude_v":
            return None if self.ringing_result is None else self.ringing_result.fall.confidence
        if key in {"spike_ringing_frequency_hz", "spike_decay_rate_per_s"}:
            return None if self.ringing_result is None else self.ringing_result.overall_confidence
        if key in {
            "discontinuous_initial_amplitude_v",
            "discontinuous_resonance_frequency_hz",
            "discontinuous_decay_rate_per_s",
        }:
            return None if self.dcm_result is None else self.dcm_result.confidence
        return None

    def _control_range(
        self,
        key: str,
        current: float,
    ) -> tuple[float, float, float, float, int, float]:
        assert self.time_s is not None
        assert self.voltage_v is not None
        dt = float(np.median(np.diff(self.time_s)))
        duration_us = max(float(self.time_s[-1] - self.time_s[0]) * 1e6, 0.001)
        y_min = float(np.min(self.voltage_v))
        y_max = float(np.max(self.voltage_v))
        span = max(y_max - y_min, 0.1)

        if key in {
            "baseline_voltage_v",
            "on_high_voltage_v",
            "freewheel_low_voltage_v",
        }:
            return (
                y_min - 3 * span,
                y_max + 3 * span,
                y_min - 0.5 * span,
                y_max + 0.5 * span,
                6,
                max(span / 1000.0, 1e-6),
            )
        if key in {
            "rise_spike_amplitude_v",
            "fall_spike_amplitude_v",
            "discontinuous_initial_amplitude_v",
        }:
            hard = max(10.0 * span, abs(current) * 5.0, 1.0)
            soft = max(2.0 * span, abs(current) * 2.0, 0.5)
            return -hard, hard, -soft, soft, 6, max(span / 1000.0, 1e-6)
        if key == "switching_start_s":
            start_us = float(self.time_s[0]) * 1e6
            end_us = float(self.time_s[-1]) * 1e6
            return start_us, end_us, start_us, end_us, 6, max(duration_us / 10000.0, 1e-6)
        if key in {"on_time_s", "freewheel_time_s"}:
            return 0.0, duration_us, 0.0, min(duration_us, max(current * 2.0, duration_us * 0.5)), 6, max(duration_us / 10000.0, 1e-6)
        if key in {"rise_time_s", "fall_time_s"}:
            duration_ns = duration_us * 1000.0
            soft_max = min(duration_ns, max(current * 3.0, 500.0, 50.0 * dt * 1e9))
            return 0.0, duration_ns, 0.0, soft_max, 3, max(dt * 1e9 / 4.0, 0.001)
        if key in {
            "spike_ringing_frequency_hz",
            "discontinuous_resonance_frequency_hz",
        }:
            max_mhz = max(0.45 / dt / 1e6, 0.001)
            default_soft = 100.0 if key == "spike_ringing_frequency_hz" else 20.0
            soft_max = min(max_mhz, max(current * 2.0, default_soft))
            return 0.0, max_mhz, 0.0, soft_max, 6, max(soft_max / 10000.0, 0.001)
        if key in {"spike_decay_rate_per_s", "discontinuous_decay_rate_per_s"}:
            hard = max(1000.0, current * 10.0, 10.0)
            default_soft = 20.0 if key == "spike_decay_rate_per_s" else 5.0
            soft = min(hard, max(current * 2.0, default_soft))
            return 0.0, hard, 0.0, soft, 6, max(soft / 10000.0, 0.0001)
        return -1e9, 1e9, current - 1.0, current + 1.0, 6, 0.001

    @staticmethod
    def _to_display(key: str, value: float) -> float:
        if key in {"switching_start_s", "on_time_s", "freewheel_time_s"}:
            return value * 1e6
        if key in {"rise_time_s", "fall_time_s"}:
            return value * 1e9
        if key in {
            "spike_ringing_frequency_hz",
            "discontinuous_resonance_frequency_hz",
            "spike_decay_rate_per_s",
            "discontinuous_decay_rate_per_s",
        }:
            return value / 1e6
        return value

    @staticmethod
    def _from_display(key: str, value: float) -> float:
        if key in {"switching_start_s", "on_time_s", "freewheel_time_s"}:
            return value * 1e-6
        if key in {"rise_time_s", "fall_time_s"}:
            return value * 1e-9
        if key in {
            "spike_ringing_frequency_hz",
            "discontinuous_resonance_frequency_hz",
            "spike_decay_rate_per_s",
            "discontinuous_decay_rate_per_s",
        }:
            return value * 1e6
        return value

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
            "algorithm": "dcm_parameter_identification_v5_generator_unified",
            "source_model": "single_event_dcm_sw_v2_signed_spikes",
            "basic": self.result.to_dict(),
            "edge_ringing": None if self.ringing_result is None else self.ringing_result.to_dict(),
            "discontinuous_resonance": None if self.dcm_result is None else self.dcm_result.to_dict(),
            "global_refinement": None if self.global_result is None else self.global_result.to_dict(),
            "current_generator_parameters": None
            if self.current_parameters is None
            else asdict(self.current_parameters),
            "current_generator_fit": None
            if self.current_fit_result is None
            else self.current_fit_result.to_dict(),
            "note": (
                "current_generator_parameters 与 DCM SW 生成器 DcmSwParameters 字段完全一致；"
                "相位仅保留在内部自动拟合诊断中，不属于当前生成器主模型。"
            ),
        }
        if self.ringing_error:
            payload["edge_ringing_error"] = self.ringing_error
        if self.dcm_error:
            payload["discontinuous_resonance_error"] = self.dcm_error
        if self.global_error:
            payload["global_refinement_error"] = self.global_error
        if self.current_fit_error:
            payload["current_generator_fit_error"] = self.current_fit_error
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
