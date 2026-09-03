from __future__ import annotations

import sys
from pathlib import Path

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .config import AppConfig, load_config, save_config
from .converter import convert, load_waveform, save_result


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Scope Zero Span Converter")
        self.resize(1400, 900)
        self.config = AppConfig()

        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)

        splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        splitter.addWidget(right)
        splitter.setSizes([430, 970])

        self._build_input_group(left_layout)
        self._build_signal_group(left_layout)
        self._build_conversion_group(left_layout)
        self._build_output_group(left_layout)
        self._build_config_buttons(left_layout)

        self.convert_button = QPushButton("开始转换")
        self.convert_button.setMinimumHeight(42)
        self.convert_button.clicked.connect(self.run_conversion)
        left_layout.addWidget(self.convert_button)
        left_layout.addStretch(1)

        self.figure = Figure(figsize=(9, 7))
        self.canvas = FigureCanvas(self.figure)
        right_layout.addWidget(self.canvas, 1)

        self.status_label = QLabel("就绪")
        right_layout.addWidget(self.status_label)

        self.apply_config(self.config)

    def _build_input_group(self, parent: QVBoxLayout) -> None:
        group = QGroupBox("输入文件")
        layout = QFormLayout(group)

        self.waveform_edit = QLineEdit()
        waveform_row = QHBoxLayout()
        waveform_row.addWidget(self.waveform_edit)
        btn = QPushButton("浏览")
        btn.clicked.connect(self.browse_waveform)
        waveform_row.addWidget(btn)
        layout.addRow("Waveform CSV", waveform_row)

        self.metadata_edit = QLineEdit()
        metadata_row = QHBoxLayout()
        metadata_row.addWidget(self.metadata_edit)
        btn = QPushButton("浏览")
        btn.clicked.connect(self.browse_metadata)
        metadata_row.addWidget(btn)
        layout.addRow("Metadata JSON", metadata_row)

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
        group = QGroupBox("转换参数")
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

        layout.addRow("Detector", self.detector_combo)
        layout.addRow("RBW Filter", self.rbw_filter_combo)
        layout.addRow("阻抗 (Ω)", self.impedance_ohm)
        layout.addRow("校准 (dB)", self.calibration_db)
        layout.addRow("示波器模拟带宽 (MHz)", self.scope_bw_mhz)
        layout.addRow(self.vbw_enabled_check)
        layout.addRow(self.resample_check)
        parent.addWidget(group)

    def _build_output_group(self, parent: QVBoxLayout) -> None:
        group = QGroupBox("输出")
        layout = QFormLayout(group)

        self.output_edit = QLineEdit()
        row = QHBoxLayout()
        row.addWidget(self.output_edit)
        btn = QPushButton("浏览")
        btn.clicked.connect(self.browse_output)
        row.addWidget(btn)
        layout.addRow("输出目录", row)

        self.save_csv_check = QCheckBox("保存 CSV")
        self.save_plot_check = QCheckBox("保存 PNG")
        self.show_plot_check = QCheckBox("CLI 模式弹出独立图窗")
        layout.addRow(self.save_csv_check)
        layout.addRow(self.save_plot_check)
        layout.addRow(self.show_plot_check)
        parent.addWidget(group)

    def _build_config_buttons(self, parent: QVBoxLayout) -> None:
        row = QHBoxLayout()
        load_btn = QPushButton("加载配置")
        save_btn = QPushButton("保存配置")
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

    def browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.output_edit.setText(path)

    def collect_config(self) -> AppConfig:
        cfg = AppConfig()
        cfg.input.waveform_file = self.waveform_edit.text().strip()
        cfg.input.metadata_file = self.metadata_edit.text().strip()
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
        cfg.scope.analog_bandwidth_hz = self.scope_bw_mhz.value() * 1e6
        cfg.output.directory = self.output_edit.text().strip() or "output"
        cfg.output.save_csv = self.save_csv_check.isChecked()
        cfg.output.save_plot = self.save_plot_check.isChecked()
        cfg.output.show_plot = self.show_plot_check.isChecked()
        cfg.validate()
        return cfg

    def apply_config(self, cfg: AppConfig) -> None:
        self.waveform_edit.setText(cfg.input.waveform_file)
        self.metadata_edit.setText(cfg.input.metadata_file)
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
        self.scope_bw_mhz.setValue(cfg.scope.analog_bandwidth_hz / 1e6)
        self.output_edit.setText(cfg.output.directory)
        self.save_csv_check.setChecked(cfg.output.save_csv)
        self.save_plot_check.setChecked(cfg.output.save_plot)
        self.show_plot_check.setChecked(cfg.output.show_plot)
        self.config = cfg

    def load_config_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "加载配置", "", "JSON (*.json)")
        if not path:
            return
        try:
            self.apply_config(load_config(path))
            self.status_label.setText(f"已加载配置：{path}")
        except Exception as exc:
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
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))

    def restore_defaults(self) -> None:
        self.apply_config(AppConfig())
        self.status_label.setText("已恢复默认参数")

    def run_conversion(self) -> None:
        try:
            cfg = self.collect_config()
            waveform = Path(cfg.input.waveform_file)
            metadata = Path(cfg.input.metadata_file)
            if not waveform.exists():
                raise FileNotFoundError(f"找不到波形文件：{waveform}")
            if not metadata.exists():
                raise FileNotFoundError(f"找不到 metadata 文件：{metadata}")

            self.convert_button.setEnabled(False)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.status_label.setText("正在转换...")
            QApplication.processEvents()

            result = convert(waveform, metadata, cfg)

            # GUI 内嵌预览，因此保存结果时不再额外弹 Matplotlib 窗口。
            show_plot = cfg.output.show_plot
            cfg.output.show_plot = False
            save_result(result, waveform, cfg)
            cfg.output.show_plot = show_plot

            t, voltage, _ = load_waveform(waveform)
            t = t - t[0]
            self.figure.clear()
            ax1 = self.figure.add_subplot(211)
            ax2 = self.figure.add_subplot(212)
            ax1.plot(t, voltage, linewidth=0.8)
            ax1.set_title("示波器原始时域波形")
            ax1.set_xlabel("Time (s)")
            ax1.set_ylabel("Voltage (V)")
            ax1.grid(True, alpha=0.3)

            ax2.plot(result.time_s, result.amplitude_dbm, linewidth=1.0)
            ax2.set_title(
                f"Zero Span 恢复：Center={result.center_frequency_hz/1e6:.3f} MHz, "
                f"RBW={result.rbw_hz/1e6:.3f} MHz"
            )
            ax2.set_xlabel("Time (s)")
            ax2.set_ylabel("Amplitude (dBm)")
            ax2.grid(True, alpha=0.3)
            self.figure.tight_layout()
            self.canvas.draw()

            self.config = cfg
            self.status_label.setText(
                "转换完成 | "
                f"Center {result.center_frequency_hz/1e6:.3f} MHz | "
                f"RBW {result.rbw_hz/1e6:.3f} MHz | "
                f"Fs {result.sample_rate_hz/1e6:.3f} MSa/s"
            )
        except Exception as exc:
            self.status_label.setText("转换失败")
            QMessageBox.critical(self, "转换失败", str(exc))
        finally:
            QApplication.restoreOverrideCursor()
            self.convert_button.setEnabled(True)


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
