from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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

from .dcm_parameter_extractor import (
    DcmBasicExtractionResult,
    extract_dcm_basic_parameters,
    load_waveform_csv,
)
from .dcm_ringing_extractor import DcmRingingExtractionResult, extract_dcm_edge_ringing
from .logging_utils import get_logger
from .plotting import configure_matplotlib_chinese


configure_matplotlib_chinese()
LOGGER = get_logger()


class DcmParameterExtractorWidget(QWidget):
    """从 time_s, voltage_v CSV 中逐阶段反演 DCM SW 参数。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.waveform_path: Path | None = None
        self.time_s: np.ndarray | None = None
        self.voltage_v: np.ndarray | None = None
        self.result: DcmBasicExtractionResult | None = None
        self.ringing_result: DcmRingingExtractionResult | None = None
        self.ringing_error: str | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        splitter.addWidget(left)

        input_group = QGroupBox("输入与分析")
        input_layout = QVBoxLayout(input_group)
        self.file_label = QLabel("尚未加载 CSV")
        self.file_label.setWordWrap(True)
        input_layout.addWidget(self.file_label)

        load_btn = QPushButton("加载 CSV 并自动提取")
        load_btn.setMinimumHeight(38)
        load_btn.clicked.connect(self.load_and_extract_dialog)
        input_layout.addWidget(load_btn)

        rerun_btn = QPushButton("重新分析当前 CSV")
        rerun_btn.clicked.connect(self.run_extraction)
        input_layout.addWidget(rerun_btn)
        left_layout.addWidget(input_group)

        result_group = QGroupBox("DCM 参数反演结果")
        result_layout = QVBoxLayout(result_group)
        self.result_table = QTableWidget(0, 3)
        self.result_table.setHorizontalHeaderLabels(["参数", "提取值", "置信度"])
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.result_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.result_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.result_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.result_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        result_layout.addWidget(self.result_table)
        left_layout.addWidget(result_group, 1)

        self.confidence_label = QLabel("总体置信度：--")
        self.confidence_label.setWordWrap(True)
        left_layout.addWidget(self.confidence_label)

        self.warning_label = QLabel(
            "当前已实现：基础电平/时间分段 + 上下沿尖峰/共享寄生振铃反演。"
            "下一阶段继续从扣除尖峰后的残差中提取 DCM 断续谐振。"
        )
        self.warning_label.setWordWrap(True)
        left_layout.addWidget(self.warning_label)

        save_btn = QPushButton("保存提取结果 JSON")
        save_btn.clicked.connect(self.save_result_dialog)
        left_layout.addWidget(save_btn)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        splitter.addWidget(right)
        splitter.setSizes([500, 1020])

        self.show_residual_check = QCheckBox("显示拟合残差 / 尖峰振铃分量")
        self.show_residual_check.setChecked(False)
        self.show_residual_check.stateChanged.connect(self._redraw)
        right_layout.addWidget(self.show_residual_check)

        self.figure = Figure(figsize=(10, 7))
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        right_layout.addWidget(self.toolbar)
        right_layout.addWidget(self.canvas, 1)

        self.status_label = QLabel(
            "加载只含 time_s / voltage_v 的 CSV 后，工具会先完成基础分段，再从残差中自动拟合"
            "上升沿和下降沿尖峰、寄生振铃频率与指数衰减。"
        )
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)

    def load_and_extract_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "加载 DCM SW 波形 CSV",
            "",
            "CSV (*.csv)",
        )
        if not path:
            return
        try:
            time_s, voltage_v = load_waveform_csv(path)
        except Exception as exc:
            QMessageBox.critical(self, "加载 CSV 失败", str(exc))
            return

        self.waveform_path = Path(path)
        self.time_s = time_s
        self.voltage_v = voltage_v
        self.file_label.setText(str(self.waveform_path))
        self.run_extraction()

    def set_waveform(
        self,
        time_s: np.ndarray,
        voltage_v: np.ndarray,
        *,
        source_name: str = "内存波形",
    ) -> None:
        """预留给波形研究页/生成器直接发送内存数据。"""

        self.waveform_path = None
        self.time_s = np.asarray(time_s, dtype=float).copy()
        self.voltage_v = np.asarray(voltage_v, dtype=float).copy()
        self.file_label.setText(source_name)
        self.run_extraction()

    def run_extraction(self) -> None:
        if self.time_s is None or self.voltage_v is None:
            QMessageBox.information(self, "尚未加载", "请先加载 time_s, voltage_v CSV。")
            return
        try:
            self.result = extract_dcm_basic_parameters(self.time_s, self.voltage_v)
        except Exception as exc:
            self.result = None
            self.ringing_result = None
            self.ringing_error = None
            LOGGER.exception("DCM 基础参数提取失败")
            QMessageBox.critical(self, "参数提取失败", str(exc))
            return

        self.ringing_result = None
        self.ringing_error = None
        try:
            self.ringing_result = extract_dcm_edge_ringing(
                self.time_s,
                self.voltage_v,
                self.result,
            )
        except Exception as exc:
            self.ringing_error = str(exc)
            LOGGER.exception("DCM 开关沿尖峰/寄生振铃提取失败，保留基础参数结果")

        self._populate_results(self.result, self.ringing_result)
        self._redraw()
        self._update_status(self.result, self.ringing_result)
        LOGGER.info(
            "DCM extraction complete source=%s basic_confidence=%.3f ringing_confidence=%s",
            self.waveform_path or "memory",
            self.result.overall_confidence,
            "--" if self.ringing_result is None else f"{self.ringing_result.overall_confidence:.3f}",
        )

    def _populate_results(
        self,
        result: DcmBasicExtractionResult,
        ringing: DcmRingingExtractionResult | None,
    ) -> None:
        rows: list[tuple[str, str, float | None]] = [
            ("【基础】采样率", f"{result.sample_rate_hz/1e9:.6g} GSa/s", None),
            ("【基础】总显示时长", f"{result.total_duration_s*1e6:.6g} µs", None),
            (
                "【基础】基线电压",
                f"{result.baseline_voltage_v:.9g} V",
                result.confidence.get("baseline_voltage"),
            ),
            (
                "【基础】开通高电平电压",
                f"{result.on_high_voltage_v:.9g} V",
                result.confidence.get("on_high_voltage"),
            ),
            (
                "【基础】续流低电平电压",
                f"{result.freewheel_low_voltage_v:.9g} V",
                result.confidence.get("freewheel_low_voltage"),
            ),
            (
                "【基础】开关起始时间",
                f"{result.switching_start_s*1e6:.9g} µs",
                result.confidence.get("switching_start"),
            ),
            (
                "【基础】上升时间（模型完整边沿）",
                f"{result.rise_time_s*1e9:.9g} ns",
                result.confidence.get("rise_time"),
            ),
            (
                "【基础】上升时间（10%~90%）",
                f"{result.rise_time_10_90_s*1e9:.9g} ns",
                result.confidence.get("rise_time"),
            ),
            (
                "【基础】导通时间",
                f"{result.on_time_s*1e6:.9g} µs",
                result.confidence.get("on_time"),
            ),
            (
                "【基础】下降时间（模型完整边沿）",
                f"{result.fall_time_s*1e9:.9g} ns",
                result.confidence.get("fall_time"),
            ),
            (
                "【基础】下降时间（10%~90%）",
                f"{result.fall_time_10_90_s*1e9:.9g} ns",
                result.confidence.get("fall_time"),
            ),
            (
                "【基础】续流时间",
                f"{result.freewheel_time_s*1e6:.9g} µs",
                result.confidence.get("freewheel_time"),
            ),
            ("【基础】基线区估计噪声 RMS", f"{result.estimated_noise_rms_v*1e3:.9g} mV", None),
        ]

        if ringing is not None:
            rows.extend(
                [
                    (
                        "【尖峰】上升沿初始尖峰电压",
                        f"{ringing.rise.signed_initial_amplitude_v:.9g} V",
                        ringing.rise.confidence,
                    ),
                    (
                        "【尖峰】下降沿初始尖峰电压",
                        f"{ringing.fall.signed_initial_amplitude_v:.9g} V",
                        ringing.fall.confidence,
                    ),
                    (
                        "【振铃】共享寄生振铃频率",
                        f"{ringing.ringing_frequency_hz/1e6:.9g} MHz",
                        ringing.overall_confidence,
                    ),
                    (
                        "【振铃】共享衰减速率",
                        f"{ringing.decay_rate_per_s/1e6:.9g} /µs",
                        ringing.overall_confidence,
                    ),
                    (
                        "【研究】上升沿拟合相位",
                        f"{np.degrees(ringing.rise.phase_rad):.6g}°",
                        ringing.rise.confidence,
                    ),
                    (
                        "【研究】下降沿拟合相位",
                        f"{np.degrees(ringing.fall.phase_rad):.6g}°",
                        ringing.fall.confidence,
                    ),
                    (
                        "【研究】上升沿局部拟合 R²",
                        f"{ringing.rise.r_squared:.6f}",
                        ringing.rise.confidence,
                    ),
                    (
                        "【研究】下降沿局部拟合 R²",
                        f"{ringing.fall.r_squared:.6f}",
                        ringing.fall.confidence,
                    ),
                ]
            )

        self.result_table.setRowCount(len(rows))
        for row, (name, value, confidence) in enumerate(rows):
            self.result_table.setItem(row, 0, QTableWidgetItem(name))
            self.result_table.setItem(row, 1, QTableWidgetItem(value))
            conf_text = "--" if confidence is None else f"{confidence*100:.0f}%"
            conf_item = QTableWidgetItem(conf_text)
            conf_item.setTextAlignment(Qt.AlignCenter)
            self.result_table.setItem(row, 2, conf_item)

    def _update_status(
        self,
        result: DcmBasicExtractionResult,
        ringing: DcmRingingExtractionResult | None,
    ) -> None:
        if ringing is None:
            self.confidence_label.setText(
                f"基础参数总体置信度：{result.overall_confidence*100:.1f}% | 尖峰/振铃：未完成"
            )
        else:
            combined = 0.5 * result.overall_confidence + 0.5 * ringing.overall_confidence
            self.confidence_label.setText(
                f"综合参考置信度：{combined*100:.1f}% | "
                f"基础 {result.overall_confidence*100:.1f}% | "
                f"尖峰/振铃 {ringing.overall_confidence*100:.1f}%"
            )

        warnings = list(result.warnings)
        if ringing is not None:
            warnings.extend(ringing.warnings)
        elif self.ringing_error:
            warnings.append(f"尖峰/寄生振铃拟合未完成：{self.ringing_error}")

        if warnings:
            self.warning_label.setText("注意：\n" + "\n".join(f"• {item}" for item in warnings))
        else:
            self.warning_label.setText(
                "基础分段与开关沿寄生振铃拟合均未发现明显低置信度项。"
                "下一阶段将继续分析扣除开关沿分量后的 DCM 断续区残差。"
            )

        if ringing is None:
            self.status_label.setText(
                "基础参数提取完成；尖峰/寄生振铃未能稳定拟合。基础结果仍可保存和研究。"
            )
        else:
            self.status_label.setText(
                "第二阶段完成：只使用 CSV 的 time_s / voltage_v，已反演上升/下降尖峰及共享寄生"
                f"振铃参数。f={ringing.ringing_frequency_hz/1e6:.6g} MHz，"
                f"α={ringing.decay_rate_per_s/1e6:.6g} /µs。"
            )

    def _redraw(self) -> None:
        self.figure.clear()
        if self.time_s is None or self.voltage_v is None:
            self.canvas.draw()
            return

        show_residual = self.show_residual_check.isChecked() and self.result is not None
        if show_residual:
            ax = self.figure.add_subplot(211)
            residual_ax = self.figure.add_subplot(212, sharex=ax)
        else:
            ax = self.figure.add_subplot(111)
            residual_ax = None

        x_us = self.time_s * 1e6
        ax.plot(x_us, self.voltage_v, linewidth=0.8, label="CSV 实测波形")

        if self.result is not None:
            r = self.result
            ax.plot(
                x_us,
                r.fitted_ideal_voltage_v,
                linewidth=1.1,
                linestyle="--",
                label="基础理想轨迹",
            )

            if self.ringing_result is not None:
                reconstructed = r.fitted_ideal_voltage_v + self.ringing_result.fitted_spike_component_v
                ax.plot(
                    x_us,
                    reconstructed,
                    linewidth=0.9,
                    alpha=0.85,
                    label="基础 + 尖峰/寄生振铃拟合",
                )

            markers = [
                (r.switching_start_s, "开关起始"),
                (r.rise_end_s, "上升结束"),
                (r.fall_start_s, "下降开始"),
                (r.fall_end_s, "下降结束"),
                (r.freewheel_end_s, "断续开始"),
            ]
            for index, (time_value, label) in enumerate(markers):
                ax.axvline(time_value * 1e6, linestyle=":", alpha=0.55)
                ax.text(
                    time_value * 1e6,
                    0.98 - (index % 2) * 0.08,
                    label,
                    transform=ax.get_xaxis_transform(),
                    rotation=90,
                    va="top",
                    ha="right",
                    fontsize=8,
                )

            if residual_ax is not None:
                residual_ax.plot(x_us, r.residual_v, linewidth=0.65, label="基础残差")
                if self.ringing_result is not None:
                    residual_ax.plot(
                        x_us,
                        self.ringing_result.fitted_spike_component_v,
                        linewidth=0.85,
                        label="尖峰/寄生振铃拟合分量",
                    )
                    residual_ax.plot(
                        x_us,
                        self.ringing_result.residual_after_spike_v,
                        linewidth=0.65,
                        alpha=0.9,
                        label="扣除开关沿后的残差",
                    )
                residual_ax.axhline(0.0, linewidth=0.7, alpha=0.5)
                residual_ax.set_title("残差研究：下一阶段 DCM 断续谐振将从扣除尖峰后的残差继续提取")
                residual_ax.set_ylabel("残差电压 (V)")
                residual_ax.grid(True, alpha=0.3)
                residual_ax.legend()
                residual_ax.set_xlabel("时间 (µs)")

        ax.set_title("DCM SW 参数反演：实测波形与逐阶段拟合轨迹")
        ax.set_ylabel("电压 (V)")
        if residual_ax is None:
            ax.set_xlabel("时间 (µs)")
        ax.grid(True, alpha=0.3)
        ax.legend()
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
            "algorithm": "dcm_parameter_identification_v2",
            "basic": self.result.to_dict(),
            "edge_ringing": None if self.ringing_result is None else self.ringing_result.to_dict(),
        }
        if self.ringing_error:
            payload["edge_ringing_error"] = self.ringing_error
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
