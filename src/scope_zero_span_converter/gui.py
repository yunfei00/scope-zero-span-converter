from __future__ import annotations

import sys
from pathlib import Path

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QUrl
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


configure_matplotlib_chinese()
LOGGER = get_logger()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Scope Zero Span Converter v0.3")
        self.resize(1500, 940)
        self.config = AppConfig()

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.single_tab = QWidget()
        self.batch_tab = QWidget()
        self.tabs.addTab(self.single_tab, "单次转换")
        self.tabs.addTab(self.batch_tab, "批量转换")

        self._build_single_tab()
        self._build_batch_tab()
        self.apply_config(self.config)
        self.refresh_templates()

        LOGGER.info("GUI 启动 v0.3")

    def _build_single_tab(self) -> None:
        root_layout = QVBoxLayout(self.single_tab)
        splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(splitter, 1)

        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        self._build_input_group(left_layout)
        self._build_signal_group(left_layout)
        self._build_conversion_group(left_layout)
        self._build_output_group(left_layout)
        self._build_template_group(left_layout)
        self._build_config_buttons(left_layout)

        self.convert_button = QPushButton("开始转换")
        self.convert_button.setMinimumHeight(44)
        self.convert_button.clicked.connect(self.run_conversion)
        left_layout.addWidget(self.convert_button)
        left_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left_container)
        splitter.addWidget(scroll)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        splitter.addWidget(right)
        splitter.setSizes([500, 1000])

        self.figure = Figure(figsize=(9, 7))
        self.canvas = FigureCanvas(self.figure)
        right_layout.addWidget(self.canvas, 1)

        self.parameter_source_label = QLabel("有效参数：尚未转换")
        self.parameter_source_label.setWordWrap(True)
        right_layout.addWidget(self.parameter_source_label)

        self.status_label = QLabel("就绪")
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)

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
            [
                "任务",
                "状态",
                "Center (MHz)",
                "RBW (MHz)",
                "MAE (dB)",
                "输出目录",
                "错误",
            ]
        )
        self.batch_table.setAlternatingRowColors(True)
        self.batch_table.setSortingEnabled(False)
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
        self.fsw_reference_edit.setPlaceholderText("可选：FSW Zero Span 实测 CSV")
        layout.addRow(
            "FSW 实测 CSV",
            self._file_row(self.fsw_reference_edit, self.browse_fsw_reference),
        )

        parent.addWidget(group)

    def _spin(self, minimum: float, maximum: float, decimals: int = 6) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(minimum, maximum)
        box.setDecimals(decimals)
        box.setKeyboardTracking(False)
        return box

    def _build_signal_group(self, parent: QVBoxLayout) -> None:
        group = QGroupBox("Zero Span 测量参数")
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
        group = QGroupBox("转换与对比")
        layout = QFormLayout(group)

        self.detector_combo = QComboBox()
        self.detector_combo.addItems(["rms"])
        self.rbw_filter_combo = QComboBox()
        self.rbw_filter_combo.addItems(["gaussian"])

        self.impedance_ohm = self._spin(0.001, 1000000.0, 3)
        self.calibration_db = self._spin(-200.0, 200.0, 3)
        self.scope_bw_mhz = self._spin(0.001, 100000.0, 3)

        self.vbw_enabled_check = QCheckBox("启用 VBW")
        self.resample_check = QCheckBox("重采样到 FSW Sweep Time / Points")
        self.comparison_enabled_check = QCheckBox("有 FSW 实测 CSV 时自动对比")
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
        group = QGroupBox("输出")
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

    def browse_waveform(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 waveform.csv", "", "CSV (*.csv)")
        if path:
            self.waveform_edit.setText(path)

    def browse_metadata(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 metadata.json", "", "JSON (*.json)")
        if path:
            self.metadata_edit.setText(path)

    def browse_fsw_reference(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 FSW Zero Span 实测 CSV",
            "",
            "CSV (*.csv)",
        )
        if path:
            self.fsw_reference_edit.setText(path)

    def browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.output_edit.setText(path)

    def browse_batch_source(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择批量输入根目录")
        if path:
            self.batch_source_edit.setText(path)

    def browse_batch_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择批量输出目录")
        if path:
            self.batch_output_edit.setText(path)

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

    def load_config_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "加载配置", "", "JSON (*.json)")
        if not path:
            return
        try:
            self.apply_config(load_config(path))
            self.status_label.setText(f"已加载配置：{path}")
            LOGGER.info("加载配置 %s", path)
        except Exception as exc:
            LOGGER.exception("加载配置失败")
            QMessageBox.critical(self, "加载失败", str(exc))

    def save_config_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存配置",
            "converter-config.json",
            "JSON (*.json)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            cfg = self.collect_config()
            save_config(cfg, path)
            self.config = cfg
            self.status_label.setText(f"已保存配置：{path}")
            LOGGER.info("保存配置 %s", path)
        except Exception as exc:
            LOGGER.exception("保存配置失败")
            QMessageBox.critical(self, "保存失败", str(exc))

    def restore_defaults(self) -> None:
        self.apply_config(AppConfig())
        self.parameter_source_label.setText("有效参数：尚未转换")
        self.status_label.setText("已恢复默认参数")

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
            cfg = self.collect_config()
            save_template(name, cfg, overwrite=True)
            self.refresh_templates()
            self.template_combo.setCurrentText(name.strip())
            self.status_label.setText(f"已保存模板：{name.strip()}")
        except Exception as exc:
            LOGGER.exception("保存模板失败")
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
            LOGGER.exception("加载模板失败")
            QMessageBox.critical(self, "模板加载失败", str(exc))

    def delete_selected_template(self) -> None:
        name = self.template_combo.currentText().strip()
        if not name:
            return
        answer = QMessageBox.question(
            self,
            "删除模板",
            f"确定删除模板“{name}”吗？",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            delete_template(name)
            self.refresh_templates()
            self.status_label.setText(f"已删除模板：{name}")
        except Exception as exc:
            LOGGER.exception("删除模板失败")
            QMessageBox.critical(self, "模板删除失败", str(exc))

    def open_template_directory(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(template_directory())))

    def open_log_directory(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_directory())))

    @staticmethod
    def _source_text(source: str) -> str:
        return "metadata" if source == "metadata" else "GUI/JSON"

    def run_conversion(self) -> None:
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
            self.status_label.setText("正在转换...")
            QApplication.processEvents()

            LOGGER.info("开始单次转换 waveform=%s metadata=%s", waveform, metadata)
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

            t, voltage, _ = load_waveform(waveform)
            t = t - t[0]
            self.figure.clear()
            ax1 = self.figure.add_subplot(211)
            ax2 = self.figure.add_subplot(212)
            ax1.plot(t, voltage, linewidth=0.8)
            ax1.set_title("示波器原始时域波形")
            ax1.set_xlabel("时间 (s)")
            ax1.set_ylabel("电压 (V)")
            ax1.grid(True, alpha=0.3)

            ax2.plot(result.time_s, result.amplitude_dbm, linewidth=1.0, label="示波器恢复")
            if result.comparison is not None:
                ax2.plot(
                    result.comparison.time_s,
                    result.comparison.reference_dbm,
                    linewidth=1.0,
                    label="FSW 实测",
                )
                ax2.legend()
                metrics = (
                    f"MAE={result.comparison.mae_db:.3f} dB | "
                    f"RMSE={result.comparison.rmse_db:.3f} dB | "
                    f"Bias={result.comparison.bias_db:+.3f} dB"
                )
                ax2.text(
                    0.01,
                    0.02,
                    metrics,
                    transform=ax2.transAxes,
                    ha="left",
                    va="bottom",
                    fontsize=9,
                    bbox=dict(boxstyle="round", alpha=0.12),
                )

            ax2.set_title(
                f"Zero Span 恢复：Center={result.center_frequency_hz/1e6:.3f} MHz, "
                f"RBW={result.rbw_hz/1e6:.3f} MHz"
            )
            ax2.set_xlabel("时间 (s)")
            ax2.set_ylabel("功率 (dBm)")
            ax2.grid(True, alpha=0.3)
            self.figure.tight_layout()
            self.canvas.draw()

            sources = result.parameter_sources
            self.parameter_source_label.setText(
                "有效参数："
                f"Center {result.center_frequency_hz/1e6:.6g} MHz "
                f"[{self._source_text(sources['center_frequency_hz'])}]；"
                f"RBW {result.rbw_hz/1e6:.6g} MHz "
                f"[{self._source_text(sources['rbw_hz'])}]；"
                f"VBW "
                f"{(result.vbw_hz/1e6 if result.vbw_hz is not None else 0):.6g} MHz "
                f"[{self._source_text(sources['vbw_hz'])}]"
            )

            extra = ""
            if result.comparison is not None:
                extra = (
                    f" | MAE {result.comparison.mae_db:.3f} dB"
                    f" | RMSE {result.comparison.rmse_db:.3f} dB"
                )

            self.config = cfg
            self.status_label.setText(
                "转换完成 | "
                f"Fs {result.sample_rate_hz/1e6:.3f} MSa/s"
                f" | 输出 {cfg.output.directory}{extra}"
            )
            LOGGER.info("单次转换完成 output=%s", cfg.output.directory)
        except Exception as exc:
            LOGGER.exception("单次转换失败")
            self.status_label.setText("转换失败")
            QMessageBox.critical(self, "转换失败", str(exc))
        finally:
            QApplication.restoreOverrideCursor()
            self.convert_button.setEnabled(True)

    def _populate_batch_jobs(self, jobs) -> None:
        self.batch_table.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            values = [job.name, "待转换", "", "", "", "", ""]
            for col, value in enumerate(values):
                self.batch_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.batch_table.resizeColumnsToContents()

    def scan_batch_jobs(self) -> None:
        try:
            cfg = self.collect_config()
            jobs = discover_batch_jobs(cfg)
            self._populate_batch_jobs(jobs)
            self.batch_status_label.setText(
                f"扫描完成：发现 {len(jobs)} 个有效任务。"
                f"每个任务目录必须同时包含 {cfg.batch.waveform_filename} "
                f"和 {cfg.batch.metadata_filename}。"
            )
            LOGGER.info("批量扫描完成 jobs=%d", len(jobs))
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

            LOGGER.info("开始批量转换 source=%s", cfg.batch.source_directory)
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
                f"批量转换完成：共 {result.jobs_found} 个，"
                f"成功 {result.succeeded} 个，失败 {result.failed} 个。"
                f"汇总目录：{result.output_directory}"
            )
            LOGGER.info(
                "批量转换完成 total=%d success=%d failed=%d",
                result.jobs_found,
                result.succeeded,
                result.failed,
            )
        except Exception as exc:
            LOGGER.exception("批量转换失败")
            self.batch_status_label.setText("批量转换失败")
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
