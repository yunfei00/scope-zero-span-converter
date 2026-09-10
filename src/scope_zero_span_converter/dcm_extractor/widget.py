"""Formal, version-free DCM parameter-extractor GUI."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..dcm_discontinuous_extractor import (
    DcmDiscontinuousExtractionResult,
    extract_dcm_discontinuous_resonance,
)
from ..dcm_global_refiner import DcmGlobalRefinementResult
from ..dcm_parameter_extractor import DcmBasicExtractionResult, extract_dcm_basic_parameters
from ..dcm_ringing_extractor import DcmRingingExtractionResult, extract_dcm_edge_ringing
from ..dcm_sw_generator import DcmSwParameters
from ..dcm_unified_fit import (
    DcmUnifiedFitResult,
    evaluate_unified_dcm_fit,
    parameter_dependency_note,
    parameters_from_extraction,
)
from ..linked_parameter_control import LinkedDoubleControl
from ..logging_utils import get_logger
from ..plotting import configure_matplotlib_chinese
from ..waveform_io import load_waveform_csv_checked
from ..waveform_quality import (
    WaveformQualityReport,
    analyze_time_axis,
    require_fft_safe,
    waveform_signature,
)
from .io import build_extraction_payload, save_extraction_json, save_reconstruction_csv
from .presentation import draw_extraction, staged_summary
from .worker import GlobalRefinementWorkerTask


configure_matplotlib_chinese()
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


class DcmParameterExtractorWidget(QWidget):
    """Stable extractor UI backed only by version-free production modules."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.waveform_path: Path | None = None
        self.time_s: np.ndarray | None = None
        self.voltage_v: np.ndarray | None = None
        self.input_quality_report: WaveformQualityReport | None = None
        self.result: DcmBasicExtractionResult | None = None
        self.ringing_result: DcmRingingExtractionResult | None = None
        self.ringing_error: str | None = None
        self.dcm_result: DcmDiscontinuousExtractionResult | None = None
        self.dcm_error: str | None = None
        self.global_result: DcmGlobalRefinementResult | None = None
        self.global_error: str | None = None

        self.current_parameters: DcmSwParameters | None = None
        self.current_fit_result: DcmUnifiedFitResult | None = None
        self.current_fit_error: str | None = None
        self.parameter_controls: dict[str, LinkedDoubleControl] = {}
        self._score_items: dict[str, QTableWidgetItem] = {}
        self._score_regions: dict[str, str] = {}
        self._diagnostic_items: dict[str, QTableWidgetItem] = {}
        self._editor_syncing = False

        self._global_refinement_pool = QThreadPool.globalInstance()
        self._global_refinement_request_seq = 0
        self._global_refinement_active_request_id: int | None = None
        self._global_refinement_task: GlobalRefinementWorkerTask | None = None
        self._global_refinement_active_source_signature: str | None = None
        self._global_refinement_active_inputs: tuple[object, object, object] | None = None
        self._global_refinement_cancel_requested_id: int | None = None
        self._global_refinement_tasks: dict[int, GlobalRefinementWorkerTask] = {}
        self._shutting_down = False

        self._build_ui()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._cancel_global_refinement_for_shutdown)

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        self.splitter = QSplitter(Qt.Horizontal)
        root.addWidget(self.splitter)

        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)
        self.splitter.addWidget(self.left_panel)

        self.input_group = QGroupBox("输入与分析")
        self.input_layout = QVBoxLayout(self.input_group)
        self.file_label = QLabel("尚未加载 CSV")
        self.file_label.setWordWrap(True)
        self.input_layout.addWidget(self.file_label)

        self.load_button = QPushButton("加载 CSV 并自动提取")
        self.load_button.setMinimumHeight(38)
        self.load_button.clicked.connect(self.load_and_extract_dialog)
        self.input_layout.addWidget(self.load_button)

        self.rerun_button = QPushButton("重新分析当前 CSV")
        self.rerun_button.clicked.connect(self.run_extraction)
        self.input_layout.addWidget(self.rerun_button)

        self.global_refine_btn = QPushButton("运行全局联合精修（较慢）")
        self.global_refine_btn.setMinimumHeight(36)
        self.global_refine_btn.setEnabled(False)
        self.global_refine_btn.clicked.connect(self.run_global_refinement)
        self.input_layout.addWidget(self.global_refine_btn)

        self.cancel_global_refine_btn = QPushButton("取消全局联合精修")
        self.cancel_global_refine_btn.setEnabled(False)
        self.cancel_global_refine_btn.clicked.connect(self.cancel_global_refinement)
        self.input_layout.addWidget(self.cancel_global_refine_btn)

        parameter_actions = QHBoxLayout()
        self.restore_all_btn = QPushButton("恢复全部自动提取值")
        self.restore_all_btn.setEnabled(False)
        self.restore_all_btn.clicked.connect(self._restore_all_auto_values)
        parameter_actions.addWidget(self.restore_all_btn)
        self.use_global_all_btn = QPushButton("载入联合精修值到当前参数")
        self.use_global_all_btn.setEnabled(False)
        self.use_global_all_btn.clicked.connect(self._use_global_values)
        parameter_actions.addWidget(self.use_global_all_btn)
        self.input_layout.addLayout(parameter_actions)

        self.save_reconstruction_csv_btn = QPushButton("保存当前重建 CSV")
        self.save_reconstruction_csv_btn.setEnabled(False)
        self.save_reconstruction_csv_btn.clicked.connect(self.save_current_csv_dialog)
        self.input_layout.addWidget(self.save_reconstruction_csv_btn)
        left_layout.addWidget(self.input_group)

        self.result_group = QGroupBox("DCM 参数反演结果")
        result_layout = QVBoxLayout(self.result_group)
        self.result_table = QTableWidget(0, 3)
        self.result_table.setHorizontalHeaderLabels(
            ["参数", "滑块 + 数值输入", "自动置信度 / 当前拟合"]
        )
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.result_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.result_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.result_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.result_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        self.result_table.setColumnWidth(2, 235)
        result_layout.addWidget(self.result_table)
        left_layout.addWidget(self.result_group, 1)

        self.confidence_label = QLabel("总体置信度：--")
        self.confidence_label.setWordWrap(True)
        left_layout.addWidget(self.confidence_label)
        self.warning_label = QLabel(
            "当前参数表与 DCM SW 生成器共享 DcmSwParameters 和确定性正向模型。"
            "自动算法中的相位仅作为内部拟合辅助量。"
        )
        self.warning_label.setWordWrap(True)
        left_layout.addWidget(self.warning_label)
        self.save_result_btn = QPushButton("保存提取结果 JSON")
        self.save_result_btn.clicked.connect(self.save_result_dialog)
        left_layout.addWidget(self.save_result_btn)

        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setSizes([500, 1020])
        self.show_residual_check = QCheckBox("显示逐阶段拟合残差 / 分量")
        self.show_residual_check.setChecked(False)
        self.show_residual_check.stateChanged.connect(self._redraw)
        right_layout.addWidget(self.show_residual_check)

        self.figure = Figure(figsize=(10, 7))
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        right_layout.addWidget(self.toolbar)
        right_layout.addWidget(self.canvas, 1)
        self.status_label = QLabel(
            "加载 time_s / voltage_v CSV 后，工具会按基础轨迹 → 开关沿寄生振铃 → "
            "DCM 断续谐振的顺序逐级反演。"
        )
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)

        self._parameter_timer = QTimer(self)
        self._parameter_timer.setSingleShot(True)
        self._parameter_timer.setInterval(80)
        self._parameter_timer.timeout.connect(self._run_current_model)

    def load_and_extract_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "加载 DCM SW 波形 CSV", "", "CSV (*.csv)"
        )
        if not path:
            return
        try:
            data = load_waveform_csv_checked(
                path, min_points=64, require_named_columns=True
            )
        except Exception as exc:
            QMessageBox.critical(self, "加载 CSV 失败", str(exc))
            return

        self._invalidate_global_refinement()
        self.waveform_path = Path(path)
        self.time_s = data.time_s.copy()
        self.voltage_v = data.voltage_v.copy()
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
        """Set an in-memory waveform through the same quality gate as CSV input."""

        time = np.asarray(time_s, dtype=float)
        voltage = np.asarray(voltage_v, dtype=float)
        if time.ndim != 1 or voltage.ndim != 1 or len(time) != len(voltage):
            raise ValueError("time_s 和 voltage_v 必须是一维且点数一致")
        if len(time) < 64:
            raise ValueError("波形至少需要 64 个点")
        if not np.all(np.isfinite(time)) or not np.all(np.isfinite(voltage)):
            raise ValueError("波形包含 NaN 或 Inf")
        quality = analyze_time_axis(time)
        require_fft_safe(quality)
        order = np.argsort(time)

        self._invalidate_global_refinement()
        self.waveform_path = None
        self.time_s = np.asarray(time[order], dtype=float).copy()
        self.voltage_v = np.asarray(voltage[order], dtype=float).copy()
        self.input_quality_report = quality
        self.file_label.setText(f"{source_name} | 数据质量：{quality.summary()}")
        self.run_extraction()

    def run_extraction(self) -> None:
        if self.time_s is None or self.voltage_v is None:
            QMessageBox.information(self, "尚未加载", "请先加载 time_s, voltage_v CSV。")
            return

        self._invalidate_global_refinement()
        self._clear_analysis_results()
        try:
            self.result = extract_dcm_basic_parameters(self.time_s, self.voltage_v)
        except Exception as exc:
            LOGGER.exception("DCM 基础参数提取失败")
            self._sync_action_state()
            self._redraw()
            QMessageBox.critical(self, "参数提取失败", str(exc))
            return

        try:
            self.ringing_result = extract_dcm_edge_ringing(
                self.time_s, self.voltage_v, self.result
            )
        except Exception as exc:
            self.ringing_error = str(exc)
            LOGGER.exception("DCM 开关沿尖峰/寄生振铃提取失败，保留基础参数结果")
        try:
            self.dcm_result = extract_dcm_discontinuous_resonance(
                self.time_s, self.voltage_v, self.result, self.ringing_result
            )
        except Exception as exc:
            self.dcm_error = str(exc)
            LOGGER.exception("DCM 断续谐振提取失败，保留前级结果")

        self.current_parameters = self._parameters_from_results(None)
        self._build_parameter_table()
        self._update_stage_presentation()
        self._run_current_model()
        self._sync_action_state()
        LOGGER.info(
            "DCM staged extraction complete source=%s basic=%.3f ringing=%s dcm=%s",
            self.waveform_path or "memory",
            self.result.overall_confidence,
            "--" if self.ringing_result is None else f"{self.ringing_result.overall_confidence:.3f}",
            "--" if self.dcm_result is None else f"{self.dcm_result.confidence:.3f}",
        )

    def _clear_analysis_results(self) -> None:
        self.result = None
        self.ringing_result = None
        self.ringing_error = None
        self.dcm_result = None
        self.dcm_error = None
        self.global_result = None
        self.global_error = None
        self.current_parameters = None
        self.current_fit_result = None
        self.current_fit_error = None
        self.parameter_controls.clear()
        self._score_items.clear()
        self._score_regions.clear()
        self._diagnostic_items.clear()
        self.result_table.clearContents()
        self.result_table.setRowCount(0)

    def _parameters_from_results(
        self, global_result: DcmGlobalRefinementResult | None
    ) -> DcmSwParameters:
        assert self.result is not None
        origin = 0.0 if self.time_s is None else float(self.time_s[0])
        return parameters_from_extraction(
            self.result,
            self.ringing_result,
            self.dcm_result,
            global_result,
            time_origin_s=origin,
        )

    def _update_stage_presentation(self) -> None:
        if self.result is None:
            self.confidence_label.setText("总体置信度：--")
            return
        confidence, warning = staged_summary(
            self.result,
            self.ringing_result,
            self.dcm_result,
            self.global_result,
            ringing_error=self.ringing_error,
            discontinuous_error=self.dcm_error,
            global_error=self.global_error,
        )
        self.confidence_label.setText(confidence)
        self.warning_label.setText(warning)

    def _status_with_quality(self, text: str) -> str:
        quality = self.input_quality_report
        if quality is None:
            return text
        return (
            f"{text} | 输入质量：{quality.summary()} | "
            f"Nyquist={quality.nyquist_hz/1e6:.6g} MHz"
        )

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
            if self.time_s is not None and len(self.time_s):
                self._add_readonly_row(
                    "【输入】时间轴起点",
                    f"{float(self.time_s[0])*1e6:.9g} µs",
                    "来自 CSV time_s[0]；保存到 JSON",
                )
                self._add_readonly_row(
                    "【输入】时间轴终点",
                    f"{float(self.time_s[-1])*1e6:.9g} µs",
                    "来自 CSV time_s[-1]",
                )
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
            self._add_readonly_row("【输入】Random Seed", "--", "真实 CSV 反演不适用")
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
        current = self._to_display(key, float(getattr(self.current_parameters, key)))
        minimum, maximum, soft_min, soft_max, decimals, step = self._control_range(
            key, current
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
        control.setValue(current)
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
        if (
            self._shutting_down
            or self._editor_syncing
            or self.current_parameters is None
        ):
            return
        internal_value = self._from_display(key, float(display_value))
        self.current_parameters = replace(self.current_parameters, **{key: internal_value})
        self._parameter_timer.start()

    def _run_current_model(self) -> None:
        if self._shutting_down:
            return
        if (
            self.time_s is None
            or self.voltage_v is None
            or self.result is None
            or self.current_parameters is None
        ):
            self._sync_action_state()
            return
        try:
            self.current_fit_result = evaluate_unified_dcm_fit(
                self.time_s, self.voltage_v, self.current_parameters
            )
            self.current_fit_error = None
        except Exception as exc:
            self.current_fit_result = None
            self.current_fit_error = str(exc)
            self.status_label.setText(
                self._status_with_quality(f"当前参数组合无效：{exc}")
            )
            self._update_current_scores(None)
            self._sync_action_state()
            self._redraw()
            return
        fit = self.current_fit_result
        self._update_current_scores(fit)
        self.status_label.setText(
            self._status_with_quality(
                "生成器同源参数实时校正："
                f"当前匹配度={fit.overall_matching_score*100:.2f}% | "
                f"RMSE={fit.full_rmse_v*1e3:.6g} mV | "
                f"R²={fit.full_r_squared:.7f}。"
                "所有主参数均使用 DCM SW 生成器同一正向模型。"
            )
        )
        self._sync_action_state()
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

    def _restore_all_auto_values(self) -> None:
        if self.result is None:
            return
        self.current_parameters = self._parameters_from_results(None)
        self._build_parameter_table()
        self._run_current_model()

    def _use_global_values(self) -> None:
        if self.result is None or self.global_result is None:
            return
        self.current_parameters = self._parameters_from_results(self.global_result)
        self._build_parameter_table()
        self._run_current_model()

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
        self, key: str, current: float
    ) -> tuple[float, float, float, float, int, float]:
        assert self.time_s is not None
        assert self.voltage_v is not None
        dt = float(np.median(np.diff(self.time_s)))
        duration_us = max(float(self.time_s[-1] - self.time_s[0]) * 1e6, 0.001)
        y_min = float(np.min(self.voltage_v))
        y_max = float(np.max(self.voltage_v))
        span = max(y_max - y_min, 0.1)
        if key in {"baseline_voltage_v", "on_high_voltage_v", "freewheel_low_voltage_v"}:
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
            return (
                0.0,
                duration_us,
                0.0,
                min(duration_us, max(current * 2.0, duration_us * 0.5)),
                6,
                max(duration_us / 10000.0, 1e-6),
            )
        if key in {"rise_time_s", "fall_time_s"}:
            duration_ns = duration_us * 1000.0
            soft_max = min(duration_ns, max(current * 3.0, 500.0, 50.0 * dt * 1e9))
            return 0.0, duration_ns, 0.0, soft_max, 3, max(dt * 1e9 / 4.0, 0.001)
        if key in {"spike_ringing_frequency_hz", "discontinuous_resonance_frequency_hz"}:
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

    def _redraw(self) -> None:
        draw_extraction(
            figure=self.figure,
            canvas=self.canvas,
            show_residual=self.show_residual_check.isChecked(),
            time_s=self.time_s,
            voltage_v=self.voltage_v,
            basic=self.result,
            ringing=self.ringing_result,
            discontinuous=self.dcm_result,
            global_refinement=self.global_result,
            current_fit=self.current_fit_result,
        )

    def _ready_for_global_refinement(self) -> bool:
        return (
            self.time_s is not None
            and self.voltage_v is not None
            and self.result is not None
            and self.ringing_result is not None
            and self.dcm_result is not None
        )

    def _sync_action_state(self) -> None:
        if self._shutting_down:
            for button in (
                self.load_button,
                self.rerun_button,
                self.global_refine_btn,
                self.cancel_global_refine_btn,
                self.restore_all_btn,
                self.use_global_all_btn,
                self.save_reconstruction_csv_btn,
            ):
                button.setEnabled(False)
            return
        busy = self._global_refinement_active_request_id is not None
        cancelling = (
            busy
            and self._global_refinement_cancel_requested_id
            == self._global_refinement_active_request_id
        )
        # Once cancellation has been requested, loading/reanalysis may proceed:
        # invalidation cancels again idempotently and request-id guards reject
        # any late terminal signal from the old task.
        self.load_button.setEnabled((not busy) or cancelling)
        self.rerun_button.setEnabled((not busy) or cancelling)
        self.global_refine_btn.setText(
            "全局联合精修中…" if busy else "重新运行全局联合精修（较慢）"
        )
        self.global_refine_btn.setEnabled((not busy) and self._ready_for_global_refinement())
        self.cancel_global_refine_btn.setText(
            "正在取消全局联合精修…" if cancelling else "取消全局联合精修"
        )
        self.cancel_global_refine_btn.setEnabled(busy and not cancelling)
        self.restore_all_btn.setEnabled((not busy) and self.result is not None)
        self.use_global_all_btn.setEnabled((not busy) and self.global_result is not None)
        self.save_reconstruction_csv_btn.setEnabled(
            (not busy)
            and self.time_s is not None
            and self.voltage_v is not None
            and self.current_parameters is not None
            and self.current_fit_result is not None
        )

    def _set_global_refinement_busy(self, busy: bool) -> None:
        if not busy:
            self._global_refinement_active_request_id = None
            self._global_refinement_cancel_requested_id = None
        self._sync_action_state()

    def _invalidate_global_refinement(self) -> None:
        task = self._global_refinement_task
        if task is not None:
            task.cancel()
        self._global_refinement_active_request_id = None
        self._global_refinement_task = None
        self._global_refinement_active_source_signature = None
        self._global_refinement_active_inputs = None
        self._global_refinement_cancel_requested_id = None
        if hasattr(self, "load_button"):
            self._sync_action_state()

    def run_global_refinement(self) -> None:
        if self._shutting_down:
            return
        if self._global_refinement_active_request_id is not None:
            return
        if not self._ready_for_global_refinement():
            QMessageBox.information(
                self,
                "尚不能联合精修",
                "请先完成基础参数、开关沿寄生振铃和 DCM 断续谐振三个阶段。",
            )
            return
        assert self.time_s is not None
        assert self.voltage_v is not None
        assert self.result is not None
        assert self.ringing_result is not None
        assert self.dcm_result is not None

        self.global_result = None
        self.global_error = None
        self._global_refinement_request_seq += 1
        request_id = self._global_refinement_request_seq
        task = GlobalRefinementWorkerTask(
            request_id=request_id,
            time_s=self.time_s,
            voltage_v=self.voltage_v,
            basic=self.result,
            ringing=self.ringing_result,
            dcm=self.dcm_result,
            max_iterations=8,
            max_optimization_points=18_000,
        )
        task.signals.finished.connect(self._on_global_refinement_finished)
        task.signals.failed.connect(self._on_global_refinement_failed)
        task.signals.cancelled.connect(self._on_global_refinement_cancelled)
        self._global_refinement_active_request_id = request_id
        self._global_refinement_task = task
        self._global_refinement_tasks[request_id] = task
        self._global_refinement_cancel_requested_id = None
        self._global_refinement_active_source_signature = waveform_signature(
            self.time_s, self.voltage_v
        )
        self._global_refinement_active_inputs = (
            self.result,
            self.ringing_result,
            self.dcm_result,
        )
        self._sync_action_state()
        self.status_label.setText(
            self._status_with_quality(
                "全局联合精修已进入后台计算：界面保持响应。"
                "优化使用前三阶段结果为初值，并在完成后自动载入生成器同源参数。"
            )
        )
        self._global_refinement_pool.start(task)

    def cancel_global_refinement(self) -> None:
        request_id = self._global_refinement_active_request_id
        task = self._global_refinement_task
        if request_id is None or task is None:
            return
        if self._global_refinement_cancel_requested_id == request_id:
            return

        self._global_refinement_cancel_requested_id = request_id
        task.cancel()
        self._sync_action_state()
        self.status_label.setText(
            self._status_with_quality("正在取消全局联合精修…")
        )

    def _release_global_refinement_task(self) -> None:
        self._global_refinement_active_request_id = None
        self._global_refinement_task = None
        self._global_refinement_active_source_signature = None
        self._global_refinement_active_inputs = None
        self._global_refinement_cancel_requested_id = None
        if not self._shutting_down:
            self._sync_action_state()

    def _global_refinement_source_is_current(self) -> bool:
        if self.time_s is None or self.voltage_v is None:
            return False
        active_inputs = self._global_refinement_active_inputs
        current_inputs = (self.result, self.ringing_result, self.dcm_result)
        if active_inputs is None or not all(
            active is current
            for active, current in zip(active_inputs, current_inputs, strict=True)
        ):
            return False
        return self._global_refinement_active_source_signature == waveform_signature(
            self.time_s, self.voltage_v
        )

    def _on_global_refinement_finished(
        self, request_id: int, result: DcmGlobalRefinementResult
    ) -> None:
        self._global_refinement_tasks.pop(request_id, None)
        if request_id != self._global_refinement_active_request_id:
            return
        if self._shutting_down:
            self._release_global_refinement_task()
            LOGGER.info("DCM global refinement completed during shutdown")
            return
        if self._global_refinement_cancel_requested_id == request_id:
            self._on_global_refinement_cancelled(request_id)
            return
        if not self._global_refinement_source_is_current():
            self._release_global_refinement_task()
            self.status_label.setText(
                self._status_with_quality(
                    "联合精修结果已丢弃：输入波形或前三阶段结果已更新。"
                )
            )
            return
        self.global_result = result
        self.global_error = None
        self._release_global_refinement_task()
        if self.result is None:
            return
        self.current_parameters = self._parameters_from_results(result)
        self._build_parameter_table()
        self._update_stage_presentation()
        self._run_current_model()
        self.status_label.setText(
            self.status_label.text()
            + " | 全局联合精修完成："
            f"RMSE {result.staged_rmse_v*1e3:.6g} → {result.optimized_rmse_v*1e3:.6g} mV，"
            f"改善 {result.rmse_improvement_percent:.6g}%，"
            "精修值已映射到生成器原生参数，可继续逐项人工校正。"
        )
        LOGGER.info(
            "DCM global refinement worker complete source=%s staged_rmse=%g optimized_rmse=%g improvement=%g%% evaluations=%d",
            self.waveform_path or "memory",
            result.staged_rmse_v,
            result.optimized_rmse_v,
            result.rmse_improvement_percent,
            result.evaluations,
        )

    def _on_global_refinement_failed(self, request_id: int, message: str) -> None:
        self._global_refinement_tasks.pop(request_id, None)
        if request_id != self._global_refinement_active_request_id:
            return
        if self._shutting_down:
            self._release_global_refinement_task()
            LOGGER.warning(
                "DCM global refinement failed during shutdown: %s", message
            )
            return
        if self._global_refinement_cancel_requested_id == request_id:
            self._on_global_refinement_cancelled(request_id)
            return
        if not self._global_refinement_source_is_current():
            self._release_global_refinement_task()
            return
        self.global_result = None
        self.global_error = str(message)
        self._release_global_refinement_task()
        self._update_stage_presentation()
        self.status_label.setText(
            self._status_with_quality(
                "全局联合精修未完成；前三阶段结果和当前生成器同源参数仍然有效。"
            )
        )
        LOGGER.error("DCM global refinement worker failed: %s", message)
        QMessageBox.warning(
            self,
            "全局联合精修未完成",
            f"前三阶段结果仍然有效。\n\n{message}",
        )

    def _on_global_refinement_cancelled(self, request_id: int) -> None:
        self._global_refinement_tasks.pop(request_id, None)
        if request_id != self._global_refinement_active_request_id:
            return
        if self._shutting_down:
            self._release_global_refinement_task()
            LOGGER.info("DCM global refinement cancelled during shutdown")
            return
        if not self._global_refinement_source_is_current():
            self._release_global_refinement_task()
            return

        self._release_global_refinement_task()
        self.status_label.setText(
            self._status_with_quality(
                "全局联合精修已取消；前三阶段结果和当前参数仍可继续使用。"
            )
        )
        LOGGER.info("DCM global refinement cancelled source=%s", self.waveform_path or "memory")

    def has_active_background_tasks(self) -> bool:
        """Return whether any tracked global-refinement task is non-terminal."""

        return bool(self._global_refinement_tasks)

    def begin_shutdown(self) -> None:
        """Stop deferred fits and cooperatively cancel all tracked refinements."""

        if self._shutting_down:
            return
        self._shutting_down = True
        self._parameter_timer.stop()
        for task in tuple(self._global_refinement_tasks.values()):
            task.cancel()
        if self._global_refinement_active_request_id is not None:
            self._global_refinement_cancel_requested_id = (
                self._global_refinement_active_request_id
            )
        self._sync_action_state()

    def _cancel_global_refinement_for_shutdown(self) -> None:
        """Backward-compatible Qt shutdown hook."""

        self.begin_shutdown()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.begin_shutdown()
        super().closeEvent(event)

    def save_result(self, path: str | Path) -> Path:
        if self.result is None:
            raise ValueError("请先完成一次参数提取")
        payload = build_extraction_payload(
            basic=self.result,
            ringing=self.ringing_result,
            discontinuous=self.dcm_result,
            global_refinement=self.global_result,
            current_parameters=self.current_parameters,
            current_fit=self.current_fit_result,
            ringing_error=self.ringing_error,
            discontinuous_error=self.dcm_error,
            global_error=self.global_error,
            current_fit_error=self.current_fit_error,
            source_csv=self.waveform_path,
        )
        return save_extraction_json(path, payload)

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
            self, "保存 DCM 参数提取结果", default_name, "JSON (*.json)"
        )
        if not path:
            return
        try:
            saved = self.save_result(path)
            self.status_label.setText(f"已保存参数提取结果：{saved}")
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))

    def save_current_csv(self, path: str | Path) -> Path:
        if (
            self.time_s is None
            or self.voltage_v is None
            or self.current_parameters is None
            or self.current_fit_result is None
        ):
            raise ValueError("请先完成参数提取并得到当前重建波形")
        return save_reconstruction_csv(
            path,
            time_s=self.time_s,
            source_voltage_v=self.voltage_v,
            parameters=self.current_parameters,
            fit=self.current_fit_result,
        )

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
            self, "保存当前 DCM 重建波形", default_name, "CSV (*.csv)"
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


__all__ = ["DcmParameterExtractorWidget"]
