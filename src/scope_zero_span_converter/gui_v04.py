from __future__ import annotations

import sys
from pathlib import Path

from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector
from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .batch import discover_batch_jobs, run_batch
from .config import AppConfig, load_config, save_config
from .converter import convert, load_waveform, save_result
from .logging_utils import get_logger, log_directory
from .plotting import configure_matplotlib_chinese
from .templates import (
    delete_template,
    list_templates,
    load_template,
    save_template,
    template_directory,
)
from .waveform_research import (
    WaveformRegion,
    convert_waveform_region,
    crop_waveform,
    save_waveform_region,
)


configure_matplotlib_chinese()
LOGGER = get_logger()

TIME_SCALES = {
    "ns": 1e9,
    "us": 1e6,
    "ms": 1e3,
    "s": 1.0,
}
TIME_LABELS = {
    "ns": "ns",
    "us": "µs",
    "ms": "ms",
    "s": "s",
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Scope Zero Span Converter v0.4 - 波形研究")
        self.resize(1540, 960)
        self.config = AppConfig()

        self.waveform_time = None
        self.waveform_voltage = None
        self.waveform_sample_rate = None
        self.current_region: WaveformRegion | None = None
        self.region_conversion = None
        self._region_time = None
        self._region_voltage = None
        self._span_selector = None
        self._zoom_to_region = False
        self._updating_roi_controls = False

        self._conversion_timer = QTimer(self)
        self._conversion_timer.setSingleShot(True)
        self._conversion_timer.setInterval(250)
        self._conversion_timer.timeout.connect(self.update_region_conversion)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.research_tab = QWidget()
        self.batch_tab = QWidget()
        self.tabs.addTab(self.research_tab, "波形研究")
        self.tabs.addTab(self.batch_tab, "批量转换")

        self._build_research_tab()
        self._build_batch_tab()
        self.apply_config(self.config)
        self.refresh_templates()

        LOGGER.info("GUI 启动 v0.4 waveform research")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_research_tab(self) -> None:
        root_layout = QVBoxLayout(self.research_tab)
        splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(splitter, 1)

        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        self._build_input_group(left_layout)
        self._build_waveform_research_group(left_layout)
        self._build_signal_group(left_layout)
        self._build_conversion_group(left_layout)
        self._build_output_group(left_layout)
        self._build_template_group(left_layout)
        self._build_config_buttons(left_layout)

        self.convert_button = QPushButton("执行原有完整转换并保存")
        self.convert_button.setMinimumHeight(42)
        self.convert_button.clicked.connect(self.run_full_conversion)
        left_layout.addWidget(self.convert_button)
        left_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left_container)
        splitter.addWidget(scroll)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        splitter.addWidget(right)
        splitter.setSizes([520, 1020])

        self.figure = Figure(figsize=(9, 7))
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        right_layout.addWidget(self.toolbar)
        right_layout.addWidget(self.canvas, 1)

        help_label = QLabel(
            "操作提示：在上方原始波形上按住鼠标左键横向拖动即可选择研究区域；"
            "选择结束后，下方转换波形会按当前区域自动重新计算。"
        )
        help_label.setWordWrap(True)
        right_layout.addWidget(help_label)

        self.parameter_source_label = QLabel("有效参数：尚未转换")
        self.parameter_source_label.setWordWrap(True)
        right_layout.addWidget(self.parameter_source_label)

        self.status_label = QLabel("请选择 waveform.csv，然后在波形上框选研究区域")
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)

        self._draw_empty_figure()

    def _build_batch_tab(self) -> None:
        layout = QVBoxLayout(self.batch_tab)

        settings_group = QGroupBox("批量任务设置")
        form = QFormLayout(settings_group)

        self.batch_source_edit = QLineEdit()
        form.addRow(
            "输入根目录",
            self._file_row(self.batch_source_edit, self.browse_batch_source),
        )

        self.batch_output_edit = QLineEdit()
        form.addRow(
            "批量输出目录",
            self._file_row(self.batch_output_edit, self.browse_batch_output),
        )

        self.batch_waveform_name = QLineEdit("waveform.csv")
        self.batch_metadata_name = QLineEdit("metadata.json")
        self.batch_reference_name = QLineEdit()
        self.batch_reference_name.setPlaceholderText("可选，例如 fsw_zero_span.csv")
        self.batch_recursive_check = QCheckBox("递归扫描子目录")
        self.batch_continue_check = QCheckBox("单个任务失败后继续")
        self.batch_summary_csv_check = QCheckBox("保存 batch_summary.csv")
        self.batch_summary_json_check = QCheckBox("保存 batch_summary.json")

        form.addRow("Waveform 文件名", self.batch_waveform_name)
        form.addRow("Metadata 文件名", self.batch_metadata_name)
        form.addRow("FSW 实测文件名", self.batch_reference_name)
        form.addRow(self.batch_recursive_check)
        form.addRow(self.batch_continue_check)
        form.addRow(self.batch_summary_csv_check)
        form.addRow(self.batch_summary_json_check)
        layout.addWidget(settings_group)

        buttons = QHBoxLayout()
        self.scan_batch_button = QPushButton("扫描任务")
        self.run_batch_button = QPushButton("开始批量转换")
        self.scan_batch_button.clicked.connect(self.scan_batch_jobs)
        self.run_batch_button.clicked.connect(self.run_batch_conversion)
        buttons.addWidget(self.scan_batch_button)
        buttons.addWidget(self.run_batch_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.batch_status_label = QLabel("尚未扫描")
        self.batch_status_label.setWordWrap(True)
        layout.addWidget(self.batch_status_label)

        self.batch_table = QTableWidget(0, 7)
        self.batch_table.setHorizontalHeaderLabels(
            ["任务", "状态", "Center (MHz)", "RBW (MHz)", "MAE (dB)", "输出目录", "错误"]
        )
        self.batch_table.setAlternatingRowColors(True)
        layout.addWidget(self.batch_table, 1)

    def _file_row(self, line_edit: QLineEdit, callback) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(line_edit)
        btn = QPushButton("浏览")
        btn.clicked.connect(callback)
        row.addWidget(btn)
        return row

    def _build_input_group(self, parent: QVBoxLayout) -> None:
        group = QGroupBox("输入文件")
        layout = QFormLayout(group)

        self.waveform_edit = QLineEdit()
        layout.addRow("Waveform CSV", self._file_row(self.waveform_edit, self.browse_waveform))

        self.metadata_edit = QLineEdit()
        layout.addRow("Metadata JSON", self._file_row(self.metadata_edit, self.browse_metadata))

        self.fsw_reference_edit = QLineEdit()
        self.fsw_reference_edit.setPlaceholderText("可选：原有 FSW Zero Span 实测 CSV")
        layout.addRow(
            "FSW 实测 CSV",
            self._file_row(self.fsw_reference_edit, self.browse_fsw_reference),
        )

        load_btn = QPushButton("加载波形并进入研究模式")
        load_btn.clicked.connect(self.load_waveform_from_ui)
        layout.addRow(load_btn)
        parent.addWidget(group)

    def _spin(self, minimum: float, maximum: float, decimals: int = 6) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(minimum, maximum)
        box.setDecimals(decimals)
        box.setKeyboardTracking(False)
        return box

    def _build_waveform_research_group(self, parent: QVBoxLayout) -> None:
        group = QGroupBox("波形研究区域（ROI）")
        layout = QVBoxLayout(group)

        form = QFormLayout()
        self.extraction_mode_combo = QComboBox()
        self.extraction_mode_combo.addItem("手动框选", "manual")
        form.addRow("提取模式", self.extraction_mode_combo)

        self.time_unit_combo = QComboBox()
        self.time_unit_combo.addItems(["ns", "us", "ms", "s"])
        self.time_unit_combo.currentTextChanged.connect(self._on_time_unit_changed)
        form.addRow("时间单位", self.time_unit_combo)

        self.roi_start_spin = self._spin(-1e12, 1e12, 9)
        self.roi_end_spin = self._spin(-1e12, 1e12, 9)
        self.roi_start_spin.valueChanged.connect(self._schedule_roi_from_controls)
        self.roi_end_spin.valueChanged.connect(self._schedule_roi_from_controls)
        form.addRow("研究区起点", self.roi_start_spin)
        form.addRow("研究区终点", self.roi_end_spin)

        self.auto_update_roi_check = QCheckBox("研究区域变化后自动更新下方转换波形")
        self.save_region_metadata_check = QCheckBox("保存截取 CSV 时同时保存 region.json")
        self.reset_saved_time_check = QCheckBox("保存截取 CSV 时将时间轴从 0 开始")
        form.addRow(self.auto_update_roi_check)
        form.addRow(self.save_region_metadata_check)
        form.addRow(self.reset_saved_time_check)
        layout.addLayout(form)

        self.roi_info_label = QLabel("当前研究区域：未选择")
        self.roi_info_label.setWordWrap(True)
        layout.addWidget(self.roi_info_label)

        row1 = QHBoxLayout()
        apply_btn = QPushButton("应用数值区域")
        zoom_btn = QPushButton("放大到选区")
        restore_btn = QPushButton("恢复全波形")
        apply_btn.clicked.connect(self.apply_roi_from_controls)
        zoom_btn.clicked.connect(self.zoom_to_current_region)
        restore_btn.clicked.connect(self.restore_full_waveform_view)
        row1.addWidget(apply_btn)
        row1.addWidget(zoom_btn)
        row1.addWidget(restore_btn)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        clear_btn = QPushButton("清除选区")
        save_btn = QPushButton("保存截取波形 CSV")
        refresh_btn = QPushButton("立即刷新转换")
        clear_btn.clicked.connect(self.clear_current_region)
        save_btn.clicked.connect(self.save_current_region)
        refresh_btn.clicked.connect(self.update_region_conversion)
        row2.addWidget(clear_btn)
        row2.addWidget(save_btn)
        row2.addWidget(refresh_btn)
        layout.addLayout(row2)

        note = QLabel(
            "当前先实现通用手动研究区域。DCM SW 的自动识别/自动提取参数将在后续加入，"
            "不会改变现有 ROI、保存和联动转换接口。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        parent.addWidget(group)

    def _build_signal_group(self, parent: QVBoxLayout) -> None:
        group = QGroupBox("Zero Span 转换参数（当前算法保持不变）")
        layout = QFormLayout(group)

        self.center_mhz = self._spin(0.001, 100000.0, 6)
        self.rbw_mhz = self._spin(0.000001, 10000.0, 6)
        self.vbw_mhz = self._spin(0.000001, 10000.0, 6)
        self.span_mhz = self._spin(0.0, 0.0, 6)
        self.span_mhz.setEnabled(False)

        layout.addRow("Center (MHz)", self.center_mhz)
        layout.addRow("Span (MHz)", self.span_mhz)
        layout.addRow("RBW (MHz)", self.rbw_mhz)
        layout.addRow("VBW (MHz)", self.vbw_mhz)

        self.use_metadata_check = QCheckBox("优先使用 metadata 中的 FSW 参数")
        layout.addRow(self.use_metadata_check)
        parent.addWidget(group)

    def _build_conversion_group(self, parent: QVBoxLayout) -> None:
        group = QGroupBox("转换设置")
        layout = QFormLayout(group)

        self.detector_combo = QComboBox()
        self.detector_combo.addItems(["rms"])
        self.rbw_filter_combo = QComboBox()
        self.rbw_filter_combo.addItems(["gaussian"])
        self.impedance_ohm = self._spin(0.001, 1000000.0, 3)
        self.calibration_db = self._spin(-200.0, 200.0, 3)
        self.scope_bw_mhz = self._spin(0.001, 100000.0, 3)
        self.vbw_enabled_check = QCheckBox("启用 VBW")
        self.resample_check = QCheckBox("正式完整转换时重采样到 FSW Sweep Time / Points")
        self.comparison_enabled_check = QCheckBox("完整转换时有 FSW CSV 则自动对比")
        self.save_comparison_csv_check = QCheckBox("保存对齐后的对比 CSV")

        layout.addRow("Detector", self.detector_combo)
        layout.addRow("RBW Filter", self.rbw_filter_combo)
        layout.addRow("阻抗 (Ω)", self.impedance_ohm)
        layout.addRow("校准 (dB)", self.calibration_db)
        layout.addRow("示波器模拟带宽 (MHz)", self.scope_bw_mhz)
        layout.addRow(self.vbw_enabled_check)
        layout.addRow(self.resample_check)
        layout.addRow(self.comparison_enabled_check)
        layout.addRow(self.save_comparison_csv_check)
        parent.addWidget(group)

    def _build_output_group(self, parent: QVBoxLayout) -> None:
        group = QGroupBox("完整转换输出")
        layout = QFormLayout(group)

        self.output_edit = QLineEdit()
        layout.addRow("输出目录", self._file_row(self.output_edit, self.browse_output))
        self.save_csv_check = QCheckBox("保存 Zero Span CSV")
        self.save_plot_check = QCheckBox("保存 PNG")
        self.save_metadata_check = QCheckBox("保存 conversion_metadata.json")
        self.show_plot_check = QCheckBox("CLI 模式弹出独立图窗")
        layout.addRow(self.save_csv_check)
        layout.addRow(self.save_plot_check)
        layout.addRow(self.save_metadata_check)
        layout.addRow(self.show_plot_check)
        parent.addWidget(group)

    def _build_template_group(self, parent: QVBoxLayout) -> None:
        group = QGroupBox("配置模板")
        layout = QVBoxLayout(group)

        row = QHBoxLayout()
        self.template_combo = QComboBox()
        load_btn = QPushButton("加载")
        save_btn = QPushButton("另存为模板")
        delete_btn = QPushButton("删除")
        refresh_btn = QPushButton("刷新")
        load_btn.clicked.connect(self.load_selected_template)
        save_btn.clicked.connect(self.save_current_template)
        delete_btn.clicked.connect(self.delete_selected_template)
        refresh_btn.clicked.connect(self.refresh_templates)
        row.addWidget(self.template_combo, 1)
        row.addWidget(load_btn)
        row.addWidget(save_btn)
        row.addWidget(delete_btn)
        row.addWidget(refresh_btn)
        layout.addLayout(row)

        folder_row = QHBoxLayout()
        folder_btn = QPushButton("打开模板目录")
        log_btn = QPushButton("打开日志目录")
        folder_btn.clicked.connect(self.open_template_directory)
        log_btn.clicked.connect(self.open_log_directory)
        folder_row.addWidget(folder_btn)
        folder_row.addWidget(log_btn)
        folder_row.addStretch(1)
        layout.addLayout(folder_row)
        parent.addWidget(group)

    def _build_config_buttons(self, parent: QVBoxLayout) -> None:
        row = QHBoxLayout()
        load_btn = QPushButton("加载 JSON")
        save_btn = QPushButton("保存 JSON")
        default_btn = QPushButton("恢复默认")
        load_btn.clicked.connect(self.load_config_dialog)
        save_btn.clicked.connect(self.save_config_dialog)
        default_btn.clicked.connect(self.restore_defaults)
        row.addWidget(load_btn)
        row.addWidget(save_btn)
        row.addWidget(default_btn)
        parent.addLayout(row)

    # ------------------------------------------------------------------
    # Waveform loading / ROI
    # ------------------------------------------------------------------
    def browse_waveform(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 waveform.csv", "", "CSV (*.csv)")
        if path:
            self.waveform_edit.setText(path)
            self.load_waveform_from_ui()

    def browse_metadata(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 metadata.json", "", "JSON (*.json)")
        if path:
            self.metadata_edit.setText(path)
            self._schedule_region_conversion()

    def browse_fsw_reference(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 FSW Zero Span 实测 CSV", "", "CSV (*.csv)")
        if path:
            self.fsw_reference_edit.setText(path)

    def browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.output_edit.setText(path)

    def load_waveform_from_ui(self) -> None:
        try:
            path = Path(self.waveform_edit.text().strip())
            if not path.exists():
                raise FileNotFoundError(f"找不到波形文件：{path}")

            t, v, fs = load_waveform(path)
            self.waveform_time = t
            self.waveform_voltage = v
            self.waveform_sample_rate = fs
            self.region_conversion = None
            self._zoom_to_region = False

            saved_start = self.config.waveform_research.selection_start_s
            saved_end = self.config.waveform_research.selection_end_s
            self.current_region = None
            self._region_time = None
            self._region_voltage = None
            if saved_start is not None and saved_end is not None:
                try:
                    rt, rv, region = crop_waveform(
                        t,
                        v,
                        saved_start,
                        saved_end,
                        min_points=self.config.waveform_research.min_points,
                    )
                    self.current_region = region
                    self._region_time = rt
                    self._region_voltage = rv
                except Exception:
                    LOGGER.info("已保存 ROI 不适用于当前波形，忽略")

            self._sync_roi_controls()
            self._redraw_waveform_and_conversion()
            self.status_label.setText(
                f"波形已加载：{len(t)} 点 | Fs={fs/1e6:.6g} MSa/s | "
                "可在上图拖动鼠标选择研究区域"
            )
            LOGGER.info("加载研究波形 %s points=%d", path, len(t))
            self._schedule_region_conversion()
        except Exception as exc:
            LOGGER.exception("加载研究波形失败")
            QMessageBox.critical(self, "波形加载失败", str(exc))

    def _current_scale(self) -> float:
        return TIME_SCALES[self.time_unit_combo.currentText()]

    def _sync_roi_controls(self) -> None:
        self._updating_roi_controls = True
        try:
            scale = self._current_scale()
            if self.current_region is None:
                if self.waveform_time is not None:
                    self.roi_start_spin.setValue(float(self.waveform_time[0]) * scale)
                    self.roi_end_spin.setValue(float(self.waveform_time[-1]) * scale)
                self.roi_info_label.setText("当前研究区域：未选择（下方可显示完整波形转换）")
            else:
                self.roi_start_spin.setValue(self.current_region.start_time_s * scale)
                self.roi_end_spin.setValue(self.current_region.end_time_s * scale)
                self.roi_info_label.setText(
                    "当前研究区域："
                    f"{self.current_region.start_time_s * scale:.9g} ~ "
                    f"{self.current_region.end_time_s * scale:.9g} {TIME_LABELS[self.time_unit_combo.currentText()]} | "
                    f"时长 {self.current_region.duration_s * scale:.9g} {TIME_LABELS[self.time_unit_combo.currentText()]} | "
                    f"{self.current_region.points} 点"
                )
        finally:
            self._updating_roi_controls = False

    def _on_span_select(self, xmin: float, xmax: float) -> None:
        if self.waveform_time is None:
            return
        scale = self._current_scale()
        try:
            rt, rv, region = crop_waveform(
                self.waveform_time,
                self.waveform_voltage,
                xmin / scale,
                xmax / scale,
                min_points=self.collect_config().waveform_research.min_points,
            )
            self.current_region = region
            self._region_time = rt
            self._region_voltage = rv
            self._sync_roi_controls()
            self._redraw_waveform_and_conversion()
            self._schedule_region_conversion()
        except Exception as exc:
            self.status_label.setText(f"研究区域无效：{exc}")

    def _schedule_roi_from_controls(self) -> None:
        if self._updating_roi_controls or self.waveform_time is None:
            return
        QTimer.singleShot(180, self.apply_roi_from_controls_silent)

    def apply_roi_from_controls_silent(self) -> None:
        try:
            self.apply_roi_from_controls(show_error=False)
        except Exception:
            pass

    def apply_roi_from_controls(self, checked: bool = False, *, show_error: bool = True) -> None:
        del checked
        if self.waveform_time is None:
            if show_error:
                QMessageBox.information(self, "研究区域", "请先加载 waveform.csv")
            return
        try:
            scale = self._current_scale()
            rt, rv, region = crop_waveform(
                self.waveform_time,
                self.waveform_voltage,
                self.roi_start_spin.value() / scale,
                self.roi_end_spin.value() / scale,
                min_points=self.collect_config().waveform_research.min_points,
            )
            self.current_region = region
            self._region_time = rt
            self._region_voltage = rv
            self._sync_roi_controls()
            self._redraw_waveform_and_conversion()
            self._schedule_region_conversion()
        except Exception as exc:
            if show_error:
                QMessageBox.warning(self, "研究区域无效", str(exc))

    def zoom_to_current_region(self) -> None:
        if self.current_region is None:
            QMessageBox.information(self, "放大研究区域", "请先框选研究区域")
            return
        self._zoom_to_region = True
        self._redraw_waveform_and_conversion()

    def restore_full_waveform_view(self) -> None:
        self._zoom_to_region = False
        self._redraw_waveform_and_conversion()
        self.status_label.setText("已恢复全波形视图，可重新框选研究区域")

    def clear_current_region(self) -> None:
        self.current_region = None
        self._region_time = None
        self._region_voltage = None
        self.region_conversion = None
        self._zoom_to_region = False
        self._sync_roi_controls()
        self._redraw_waveform_and_conversion()
        self._schedule_region_conversion()

    def save_current_region(self) -> None:
        if self.current_region is None or self._region_time is None:
            QMessageBox.information(self, "保存截取波形", "请先选择研究区域")
            return

        default_name = "waveform_region.csv"
        source = self.waveform_edit.text().strip()
        if source:
            default_name = f"{Path(source).stem}_region.csv"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存截取波形",
            default_name,
            "CSV (*.csv)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"

        try:
            csv_path, metadata_path = save_waveform_region(
                path,
                self._region_time,
                self._region_voltage,
                self.current_region,
                source_waveform=source or None,
                reset_time_to_zero=self.reset_saved_time_check.isChecked(),
                save_metadata=self.save_region_metadata_check.isChecked(),
            )
            text = f"研究区域已保存：{csv_path}"
            if metadata_path is not None:
                text += f"；参数记录：{metadata_path.name}"
            self.status_label.setText(text)
            LOGGER.info("保存研究区域 %s", csv_path)
        except Exception as exc:
            LOGGER.exception("保存研究区域失败")
            QMessageBox.critical(self, "保存失败", str(exc))

    def _on_time_unit_changed(self) -> None:
        self._sync_roi_controls()
        self._redraw_waveform_and_conversion()

    def _schedule_region_conversion(self) -> None:
        if not self.auto_update_roi_check.isChecked():
            return
        self._conversion_timer.start()

    def update_region_conversion(self) -> None:
        if self.waveform_time is None:
            return
        metadata = Path(self.metadata_edit.text().strip())
        if not metadata.exists():
            self.region_conversion = None
            self._redraw_waveform_and_conversion()
            self.status_label.setText("已选择研究区域；选择 metadata.json 后可联动更新下方转换波形")
            return

        try:
            cfg = self.collect_config()
            if self.current_region is None:
                t = self.waveform_time
                v = self.waveform_voltage
                origin_s = float(t[0])
            else:
                t = self._region_time
                v = self._region_voltage
                origin_s = self.current_region.start_time_s

            result = convert_waveform_region(t, v, metadata, cfg)
            self.region_conversion = (result, origin_s)
            self._redraw_waveform_and_conversion()

            sources = result.parameter_sources
            self.parameter_source_label.setText(
                "联动转换参数："
                f"Center {result.center_frequency_hz/1e6:.6g} MHz "
                f"[{self._source_text(sources['center_frequency_hz'])}]；"
                f"RBW {result.rbw_hz/1e6:.6g} MHz "
                f"[{self._source_text(sources['rbw_hz'])}]；"
                f"VBW {(result.vbw_hz/1e6 if result.vbw_hz is not None else 0):.6g} MHz"
            )
            if self.current_region is not None:
                self.status_label.setText(
                    f"研究区联动转换完成：{self.current_region.points} 点 | "
                    f"时长 {self.current_region.duration_s:.9g} s"
                )
        except Exception as exc:
            LOGGER.exception("研究区域联动转换失败")
            self.region_conversion = None
            self._redraw_waveform_and_conversion()
            self.status_label.setText(f"研究区域转换失败：{exc}")

    def _draw_empty_figure(self) -> None:
        self.figure.clear()
        ax1 = self.figure.add_subplot(211)
        ax2 = self.figure.add_subplot(212)
        ax1.set_title("原始时域波形 / 研究区域")
        ax1.set_xlabel("时间")
        ax1.set_ylabel("电压 (V)")
        ax1.grid(True, alpha=0.3)
        ax2.set_title("研究区域对应的转换波形")
        ax2.set_xlabel("时间")
        ax2.set_ylabel("功率 (dBm)")
        ax2.grid(True, alpha=0.3)
        self.figure.tight_layout()
        self.canvas.draw()

    def _redraw_waveform_and_conversion(self) -> None:
        if self.waveform_time is None:
            self._draw_empty_figure()
            return

        unit = self.time_unit_combo.currentText()
        scale = TIME_SCALES[unit]
        label = TIME_LABELS[unit]

        self.figure.clear()
        ax1 = self.figure.add_subplot(211)
        ax2 = self.figure.add_subplot(212)

        x = self.waveform_time * scale
        ax1.plot(x, self.waveform_voltage, linewidth=0.8)
        ax1.set_title("原始时域波形 - 拖动鼠标选择研究区域")
        ax1.set_xlabel(f"时间 ({label})")
        ax1.set_ylabel("电压 (V)")
        ax1.grid(True, alpha=0.3)

        if self.current_region is not None:
            start_x = self.current_region.start_time_s * scale
            end_x = self.current_region.end_time_s * scale
            ax1.axvspan(start_x, end_x, alpha=0.16)
            if self._zoom_to_region:
                margin = max((end_x - start_x) * 0.05, 1e-15)
                ax1.set_xlim(start_x - margin, end_x + margin)

        if self.region_conversion is not None:
            result, origin_s = self.region_conversion
            converted_x = (origin_s + result.time_s) * scale
            ax2.plot(converted_x, result.amplitude_dbm, linewidth=1.0)
            scope_text = "当前研究区域" if self.current_region is not None else "完整波形"
            ax2.set_title(
                f"{scope_text}联动转换 - Center {result.center_frequency_hz/1e6:.3f} MHz / "
                f"RBW {result.rbw_hz/1e6:.3f} MHz"
            )
            if self.current_region is not None and self._zoom_to_region:
                start_x = self.current_region.start_time_s * scale
                end_x = self.current_region.end_time_s * scale
                margin = max((end_x - start_x) * 0.05, 1e-15)
                ax2.set_xlim(start_x - margin, end_x + margin)
        else:
            ax2.set_title("研究区域对应的转换波形（等待 metadata 或刷新）")

        ax2.set_xlabel(f"时间 ({label})")
        ax2.set_ylabel("功率 (dBm)")
        ax2.grid(True, alpha=0.3)

        self.figure.tight_layout()
        self.canvas.draw()

        self._span_selector = SpanSelector(
            ax1,
            self._on_span_select,
            "horizontal",
            useblit=True,
            props={"alpha": 0.18},
            interactive=True,
            drag_from_anywhere=True,
        )

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def collect_config(self) -> AppConfig:
        cfg = AppConfig()
        cfg.input.waveform_file = self.waveform_edit.text().strip()
        cfg.input.metadata_file = self.metadata_edit.text().strip()
        cfg.input.fsw_reference_file = self.fsw_reference_edit.text().strip()

        cfg.signal.center_frequency_hz = self.center_mhz.value() * 1e6
        cfg.signal.span_hz = 0.0
        cfg.signal.rbw_hz = self.rbw_mhz.value() * 1e6
        cfg.signal.vbw_hz = self.vbw_mhz.value() * 1e6

        cfg.conversion.detector = self.detector_combo.currentText()
        cfg.conversion.rbw_filter = self.rbw_filter_combo.currentText()
        cfg.conversion.vbw_enabled = self.vbw_enabled_check.isChecked()
        cfg.conversion.resample_to_fsw_axis = self.resample_check.isChecked()
        cfg.conversion.use_metadata_parameters = self.use_metadata_check.isChecked()
        cfg.conversion.impedance_ohm = self.impedance_ohm.value()
        cfg.conversion.calibration_db = self.calibration_db.value()

        cfg.comparison.enabled = self.comparison_enabled_check.isChecked()
        cfg.comparison.save_aligned_csv = self.save_comparison_csv_check.isChecked()

        cfg.waveform_research.extraction_mode = "manual"
        cfg.waveform_research.auto_update_conversion = self.auto_update_roi_check.isChecked()
        cfg.waveform_research.time_unit = self.time_unit_combo.currentText()
        cfg.waveform_research.save_region_metadata = self.save_region_metadata_check.isChecked()
        cfg.waveform_research.reset_saved_time_to_zero = self.reset_saved_time_check.isChecked()
        if self.current_region is not None:
            cfg.waveform_research.selection_start_s = self.current_region.start_time_s
            cfg.waveform_research.selection_end_s = self.current_region.end_time_s

        cfg.scope.analog_bandwidth_hz = self.scope_bw_mhz.value() * 1e6
        cfg.output.directory = self.output_edit.text().strip() or "output"
        cfg.output.save_csv = self.save_csv_check.isChecked()
        cfg.output.save_plot = self.save_plot_check.isChecked()
        cfg.output.save_conversion_metadata = self.save_metadata_check.isChecked()
        cfg.output.show_plot = self.show_plot_check.isChecked()

        cfg.batch.source_directory = self.batch_source_edit.text().strip()
        cfg.batch.output_directory = self.batch_output_edit.text().strip() or "batch_output"
        cfg.batch.recursive = self.batch_recursive_check.isChecked()
        cfg.batch.waveform_filename = self.batch_waveform_name.text().strip()
        cfg.batch.metadata_filename = self.batch_metadata_name.text().strip()
        cfg.batch.fsw_reference_filename = self.batch_reference_name.text().strip()
        cfg.batch.continue_on_error = self.batch_continue_check.isChecked()
        cfg.batch.save_summary_csv = self.batch_summary_csv_check.isChecked()
        cfg.batch.save_summary_json = self.batch_summary_json_check.isChecked()

        cfg.validate()
        return cfg

    def apply_config(self, cfg: AppConfig) -> None:
        self.waveform_edit.setText(cfg.input.waveform_file)
        self.metadata_edit.setText(cfg.input.metadata_file)
        self.fsw_reference_edit.setText(cfg.input.fsw_reference_file)
        self.center_mhz.setValue(cfg.signal.center_frequency_hz / 1e6)
        self.span_mhz.setValue(0.0)
        self.rbw_mhz.setValue(cfg.signal.rbw_hz / 1e6)
        self.vbw_mhz.setValue(cfg.signal.vbw_hz / 1e6)
        self.detector_combo.setCurrentText(cfg.conversion.detector)
        self.rbw_filter_combo.setCurrentText(cfg.conversion.rbw_filter)
        self.vbw_enabled_check.setChecked(cfg.conversion.vbw_enabled)
        self.resample_check.setChecked(cfg.conversion.resample_to_fsw_axis)
        self.use_metadata_check.setChecked(cfg.conversion.use_metadata_parameters)
        self.impedance_ohm.setValue(cfg.conversion.impedance_ohm)
        self.calibration_db.setValue(cfg.conversion.calibration_db)
        self.comparison_enabled_check.setChecked(cfg.comparison.enabled)
        self.save_comparison_csv_check.setChecked(cfg.comparison.save_aligned_csv)
        self.scope_bw_mhz.setValue(cfg.scope.analog_bandwidth_hz / 1e6)

        self.time_unit_combo.setCurrentText(cfg.waveform_research.time_unit)
        self.auto_update_roi_check.setChecked(cfg.waveform_research.auto_update_conversion)
        self.save_region_metadata_check.setChecked(cfg.waveform_research.save_region_metadata)
        self.reset_saved_time_check.setChecked(cfg.waveform_research.reset_saved_time_to_zero)

        self.output_edit.setText(cfg.output.directory)
        self.save_csv_check.setChecked(cfg.output.save_csv)
        self.save_plot_check.setChecked(cfg.output.save_plot)
        self.save_metadata_check.setChecked(cfg.output.save_conversion_metadata)
        self.show_plot_check.setChecked(cfg.output.show_plot)

        self.batch_source_edit.setText(cfg.batch.source_directory)
        self.batch_output_edit.setText(cfg.batch.output_directory)
        self.batch_recursive_check.setChecked(cfg.batch.recursive)
        self.batch_waveform_name.setText(cfg.batch.waveform_filename)
        self.batch_metadata_name.setText(cfg.batch.metadata_filename)
        self.batch_reference_name.setText(cfg.batch.fsw_reference_filename)
        self.batch_continue_check.setChecked(cfg.batch.continue_on_error)
        self.batch_summary_csv_check.setChecked(cfg.batch.save_summary_csv)
        self.batch_summary_json_check.setChecked(cfg.batch.save_summary_json)

        self.config = cfg
        if self.waveform_time is not None:
            start = cfg.waveform_research.selection_start_s
            end = cfg.waveform_research.selection_end_s
            if start is not None and end is not None:
                try:
                    rt, rv, region = crop_waveform(
                        self.waveform_time,
                        self.waveform_voltage,
                        start,
                        end,
                        min_points=cfg.waveform_research.min_points,
                    )
                    self.current_region = region
                    self._region_time = rt
                    self._region_voltage = rv
                except Exception:
                    self.current_region = None
            self._sync_roi_controls()
            self._redraw_waveform_and_conversion()
            self._schedule_region_conversion()

    def load_config_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "加载配置", "", "JSON (*.json)")
        if not path:
            return
        try:
            self.apply_config(load_config(path))
            self.status_label.setText(f"已加载配置：{path}")
        except Exception as exc:
            LOGGER.exception("加载配置失败")
            QMessageBox.critical(self, "加载失败", str(exc))

    def save_config_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "保存配置", "converter-config.json", "JSON (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            cfg = self.collect_config()
            save_config(cfg, path)
            self.config = cfg
            self.status_label.setText(f"已保存配置：{path}")
        except Exception as exc:
            LOGGER.exception("保存配置失败")
            QMessageBox.critical(self, "保存失败", str(exc))

    def restore_defaults(self) -> None:
        self.current_region = None
        self._region_time = None
        self._region_voltage = None
        self.region_conversion = None
        self.apply_config(AppConfig())
        self._sync_roi_controls()
        self._redraw_waveform_and_conversion()
        self.status_label.setText("已恢复默认参数")

    # ------------------------------------------------------------------
    # Templates / folders
    # ------------------------------------------------------------------
    def refresh_templates(self) -> None:
        current = self.template_combo.currentText() if self.template_combo.count() else ""
        self.template_combo.clear()
        self.template_combo.addItems(list_templates())
        if current:
            index = self.template_combo.findText(current)
            if index >= 0:
                self.template_combo.setCurrentIndex(index)

    def save_current_template(self) -> None:
        name, ok = QInputDialog.getText(self, "保存模板", "模板名称：")
        if not ok or not name.strip():
            return
        try:
            save_template(name, self.collect_config(), overwrite=True)
            self.refresh_templates()
            self.template_combo.setCurrentText(name.strip())
            self.status_label.setText(f"已保存模板：{name.strip()}")
        except Exception as exc:
            QMessageBox.critical(self, "模板保存失败", str(exc))

    def load_selected_template(self) -> None:
        name = self.template_combo.currentText().strip()
        if not name:
            QMessageBox.information(self, "配置模板", "当前没有可加载的模板")
            return
        try:
            self.apply_config(load_template(name))
            self.status_label.setText(f"已加载模板：{name}")
        except Exception as exc:
            QMessageBox.critical(self, "模板加载失败", str(exc))

    def delete_selected_template(self) -> None:
        name = self.template_combo.currentText().strip()
        if not name:
            return
        answer = QMessageBox.question(self, "删除模板", f"确定删除模板“{name}”吗？")
        if answer != QMessageBox.Yes:
            return
        delete_template(name)
        self.refresh_templates()

    def open_template_directory(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(template_directory())))

    def open_log_directory(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_directory())))

    # ------------------------------------------------------------------
    # Original full conversion preserved
    # ------------------------------------------------------------------
    @staticmethod
    def _source_text(source: str) -> str:
        return "metadata" if source == "metadata" else "GUI/JSON"

    def run_full_conversion(self) -> None:
        try:
            cfg = self.collect_config()
            waveform = Path(cfg.input.waveform_file)
            metadata = Path(cfg.input.metadata_file)
            reference = Path(cfg.input.fsw_reference_file) if cfg.input.fsw_reference_file else None
            if not waveform.exists():
                raise FileNotFoundError(f"找不到波形文件：{waveform}")
            if not metadata.exists():
                raise FileNotFoundError(f"找不到 metadata 文件：{metadata}")
            if reference is not None and not reference.exists():
                raise FileNotFoundError(f"找不到 FSW 实测 CSV：{reference}")

            self.convert_button.setEnabled(False)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.status_label.setText("正在执行完整转换并保存...")
            QApplication.processEvents()

            result = convert(waveform, metadata, cfg)
            show_plot = cfg.output.show_plot
            cfg.output.show_plot = False
            save_result(
                result,
                waveform,
                cfg,
                metadata_path=metadata,
                reference_fsw_path=reference,
            )
            cfg.output.show_plot = show_plot
            self.config = cfg
            self.status_label.setText(f"完整转换完成 | 输出：{cfg.output.directory}")
            self._schedule_region_conversion()
        except Exception as exc:
            LOGGER.exception("完整转换失败")
            QMessageBox.critical(self, "转换失败", str(exc))
        finally:
            QApplication.restoreOverrideCursor()
            self.convert_button.setEnabled(True)

    # ------------------------------------------------------------------
    # Batch preserved from v0.3
    # ------------------------------------------------------------------
    def browse_batch_source(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择批量输入根目录")
        if path:
            self.batch_source_edit.setText(path)

    def browse_batch_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择批量输出目录")
        if path:
            self.batch_output_edit.setText(path)

    def _populate_batch_jobs(self, jobs) -> None:
        self.batch_table.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            for col, value in enumerate([job.name, "待转换", "", "", "", "", ""]):
                self.batch_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.batch_table.resizeColumnsToContents()

    def scan_batch_jobs(self) -> None:
        try:
            cfg = self.collect_config()
            jobs = discover_batch_jobs(cfg)
            self._populate_batch_jobs(jobs)
            self.batch_status_label.setText(f"扫描完成：发现 {len(jobs)} 个有效任务")
        except Exception as exc:
            LOGGER.exception("批量扫描失败")
            QMessageBox.critical(self, "批量扫描失败", str(exc))

    def run_batch_conversion(self) -> None:
        try:
            cfg = self.collect_config()
            self.run_batch_button.setEnabled(False)
            self.scan_batch_button.setEnabled(False)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.batch_status_label.setText("正在批量转换...")
            QApplication.processEvents()

            result = run_batch(cfg)
            self.batch_table.setRowCount(len(result.items))
            for row, item in enumerate(result.items):
                values = [
                    item.name,
                    item.status,
                    "" if item.center_frequency_hz is None else f"{item.center_frequency_hz/1e6:.6g}",
                    "" if item.rbw_hz is None else f"{item.rbw_hz/1e6:.6g}",
                    "" if item.mae_db is None else f"{item.mae_db:.4f}",
                    item.output_directory,
                    item.error or "",
                ]
                for col, value in enumerate(values):
                    self.batch_table.setItem(row, col, QTableWidgetItem(str(value)))
            self.batch_table.resizeColumnsToContents()
            self.batch_status_label.setText(
                f"批量转换完成：共 {result.jobs_found} 个，成功 {result.succeeded} 个，"
                f"失败 {result.failed} 个。汇总目录：{result.output_directory}"
            )
        except Exception as exc:
            LOGGER.exception("批量转换失败")
            QMessageBox.critical(self, "批量转换失败", str(exc))
        finally:
            QApplication.restoreOverrideCursor()
            self.run_batch_button.setEnabled(True)
            self.scan_batch_button.setEnabled(True)


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
