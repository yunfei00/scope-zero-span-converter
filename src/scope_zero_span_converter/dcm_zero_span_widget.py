from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .dcm_sw_generator import (
    DcmSwParameters,
    DcmSwWaveform,
    generate_dcm_sw_waveform,
    load_dcm_sw_parameters,
    save_dcm_sw_parameters,
    save_dcm_sw_waveform,
)
from .dcm_zero_span_link import (
    DcmZeroSpanResult,
    ZeroSpanProfile,
    convert_dcm_waveform_to_zero_span,
    load_zero_span_profile,
    save_zero_span_profile,
)
from .linked_parameter_control import LinkedDoubleControl, LinkedIntControl
from .logging_utils import get_logger


LOGGER = get_logger()


class DcmZeroSpanWidget(QWidget):
    """DCM 参数滑动 → 上方时域波形 + 下方 Zero Span 波形同步联动。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.parameters = DcmSwParameters()
        self.profile = ZeroSpanProfile()
        self.current_waveform: DcmSwWaveform | None = None
        self.current_zero_span: DcmZeroSpanResult | None = None
        self.current_zero_span_error: str | None = None
        self._syncing = False
        self._parameter_controls: dict[str, LinkedDoubleControl | LinkedIntControl] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        intro = QLabel(
            "加载已提取的 DCM 参数后，可直接拖动左侧参数。"
            "上方 DCM SW 波形与下方 Zero Span 功率波形会同时重新计算。"
            "Zero Span 转换参数通常只需首次设置，默认折叠。"
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(470)
        left_scroll.setMaximumWidth(680)
        left_host = QWidget()
        self.left_layout = QVBoxLayout(left_host)
        self.left_layout.setContentsMargins(4, 4, 8, 4)
        left_scroll.setWidget(left_host)
        splitter.addWidget(left_scroll)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.figure = Figure(figsize=(9, 7))
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_layout.addWidget(self.canvas, 1)
        self.status_label = QLabel("等待生成")
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([520, 1000])

        self._build_file_group()
        self._build_dcm_parameter_groups()
        self._build_zero_span_fold()
        self._build_export_group()
        self.left_layout.addStretch(1)

        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(120)
        self._update_timer.timeout.connect(self._recompute)

        self._apply_parameters_to_controls(self.parameters)
        self._apply_profile_to_controls(self.profile)
        self._recompute()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_file_group(self) -> None:
        group = QGroupBox("DCM 参数")
        layout = QVBoxLayout(group)
        row = QHBoxLayout()
        load_btn = QPushButton("加载 DCM 参数 JSON")
        save_btn = QPushButton("保存当前 DCM 参数 JSON")
        load_btn.clicked.connect(self.load_dcm_parameters_dialog)
        save_btn.clicked.connect(self.save_dcm_parameters_dialog)
        row.addWidget(load_btn)
        row.addWidget(save_btn)
        layout.addLayout(row)
        self.dcm_file_label = QLabel("当前：默认 DCM 参数")
        self.dcm_file_label.setWordWrap(True)
        layout.addWidget(self.dcm_file_label)
        self.left_layout.addWidget(group)

    def _build_dcm_parameter_groups(self) -> None:
        self._add_group(
            "时间轴 / 采样",
            (
                ("time_origin_s", "时间轴起点", "µs"),
                ("total_duration_s", "总显示时长", "µs"),
                ("sample_rate_hz", "采样率", "GSa/s"),
                ("random_seed", "随机种子", ""),
                ("noise_rms_v", "示波器底噪 RMS", "mV"),
            ),
        )
        self._add_group(
            "DCM 电平",
            (
                ("baseline_voltage_v", "基线电压", "V"),
                ("on_high_voltage_v", "开通高电平电压", "V"),
                ("freewheel_low_voltage_v", "续流低电平电压", "V"),
            ),
        )
        self._add_group(
            "开关时序",
            (
                ("switching_start_s", "开关起始时间", "µs"),
                ("rise_time_s", "上升沿时间", "ns"),
                ("on_time_s", "导通时间", "µs"),
                ("fall_time_s", "下降沿时间", "ns"),
                ("freewheel_time_s", "续流时间", "µs"),
            ),
        )
        self._add_group(
            "开关沿尖峰 / 寄生振铃",
            (
                ("rise_spike_amplitude_v", "上升沿尖峰电压", "V"),
                ("fall_spike_amplitude_v", "下降沿尖峰电压", "V"),
                ("spike_ringing_frequency_hz", "尖峰寄生振荡频率", "MHz"),
                ("spike_decay_rate_per_s", "尖峰衰减速率", "1/µs"),
            ),
        )
        self._add_group(
            "DCM 断续谐振",
            (
                ("discontinuous_initial_amplitude_v", "断续谐振初始振幅", "V"),
                ("discontinuous_resonance_frequency_hz", "断续谐振频率", "MHz"),
                ("discontinuous_decay_rate_per_s", "断续谐振衰减速率", "1/µs"),
            ),
        )

    def _add_group(self, title: str, rows: tuple[tuple[str, str, str], ...]) -> None:
        group = QGroupBox(title)
        form = QFormLayout(group)
        for key, label, unit in rows:
            control = self._make_parameter_control(key)
            self._parameter_controls[key] = control
            suffix = f" ({unit})" if unit else ""
            form.addRow(label + suffix, control)
            control.valueChanged.connect(
                lambda value, name=key: self._on_parameter_changed(name, value)
            )
        self.left_layout.addWidget(group)

    def _make_parameter_control(self, key: str):
        if key == "random_seed":
            return LinkedIntControl(0, 2_147_483_647, slider_min=0, slider_max=100_000)

        ranges: dict[str, tuple[float, float, float, float, int, float]] = {
            "time_origin_s": (-1e9, 1e9, -100.0, 100.0, 6, 0.01),
            "total_duration_s": (0.001, 1e9, 0.1, 100.0, 6, 0.01),
            "sample_rate_hz": (0.000001, 1000.0, 0.1, 20.0, 6, 0.1),
            "noise_rms_v": (0.0, 1e6, 0.0, 500.0, 6, 0.1),
            "baseline_voltage_v": (-10000.0, 10000.0, -50.0, 50.0, 6, 0.01),
            "on_high_voltage_v": (-10000.0, 10000.0, -50.0, 50.0, 6, 0.01),
            "freewheel_low_voltage_v": (-10000.0, 10000.0, -50.0, 50.0, 6, 0.01),
            "switching_start_s": (-1e9, 1e9, -100.0, 100.0, 6, 0.01),
            "rise_time_s": (0.0, 1e9, 0.0, 500.0, 3, 0.1),
            "on_time_s": (0.0, 1e9, 0.0, 20.0, 6, 0.01),
            "fall_time_s": (0.0, 1e9, 0.0, 500.0, 3, 0.1),
            "freewheel_time_s": (0.0, 1e9, 0.0, 20.0, 6, 0.01),
            "rise_spike_amplitude_v": (-10000.0, 10000.0, -50.0, 50.0, 6, 0.01),
            "fall_spike_amplitude_v": (-10000.0, 10000.0, -50.0, 50.0, 6, 0.01),
            "spike_ringing_frequency_hz": (0.0, 100000.0, 0.0, 500.0, 6, 0.1),
            "spike_decay_rate_per_s": (0.0, 1e6, 0.0, 50.0, 6, 0.05),
            "discontinuous_initial_amplitude_v": (-10000.0, 10000.0, -50.0, 50.0, 6, 0.01),
            "discontinuous_resonance_frequency_hz": (0.0, 100000.0, 0.0, 100.0, 6, 0.1),
            "discontinuous_decay_rate_per_s": (0.0, 1e6, 0.0, 20.0, 6, 0.05),
        }
        minimum, maximum, soft_min, soft_max, decimals, step = ranges[key]
        return LinkedDoubleControl(
            minimum,
            maximum,
            decimals,
            step,
            slider_min=soft_min,
            slider_max=soft_max,
        )

    def _build_zero_span_fold(self) -> None:
        self.zero_span_toggle = QToolButton()
        self.zero_span_toggle.setText("Zero Span 转换参数（首次配置后可折叠）")
        self.zero_span_toggle.setCheckable(True)
        self.zero_span_toggle.setChecked(False)
        self.zero_span_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.zero_span_toggle.setArrowType(Qt.RightArrow)
        self.zero_span_toggle.toggled.connect(self._toggle_zero_span_panel)
        self.left_layout.addWidget(self.zero_span_toggle)

        self.zero_span_panel = QGroupBox()
        self.zero_span_panel.setVisible(False)
        form = QFormLayout(self.zero_span_panel)

        self.center_mhz = self._profile_spin(0.001, 100000.0, 6, 1.0)
        self.rbw_mhz = self._profile_spin(0.000001, 100000.0, 6, 0.1)
        self.vbw_mhz = self._profile_spin(0.000001, 100000.0, 6, 0.1)
        self.impedance_ohm = self._profile_spin(0.001, 1e9, 6, 1.0)
        self.calibration_db = self._profile_spin(-1000.0, 1000.0, 6, 0.1)
        self.scope_bw_mhz = self._profile_spin(0.001, 100000.0, 6, 10.0)
        self.vbw_enabled = QCheckBox("启用 VBW")
        self.vbw_enabled.setChecked(True)

        form.addRow("Center Frequency (MHz)", self.center_mhz)
        form.addRow("Span", QLabel("0 Hz（固定 Zero Span）"))
        form.addRow("RBW (MHz)", self.rbw_mhz)
        form.addRow("VBW (MHz)", self.vbw_mhz)
        form.addRow("VBW", self.vbw_enabled)
        form.addRow("Detector", QLabel("RMS（固定）"))
        form.addRow("RBW Filter", QLabel("Gaussian（固定）"))
        form.addRow("阻抗 (Ω)", self.impedance_ohm)
        form.addRow("校准偏移 (dB)", self.calibration_db)
        form.addRow("示波器模拟带宽 (MHz)", self.scope_bw_mhz)

        row = QHBoxLayout()
        load_btn = QPushButton("加载转换参数")
        save_btn = QPushButton("保存转换参数")
        load_btn.clicked.connect(self.load_zero_span_profile_dialog)
        save_btn.clicked.connect(self.save_zero_span_profile_dialog)
        row.addWidget(load_btn)
        row.addWidget(save_btn)
        form.addRow(row)

        for widget in (
            self.center_mhz,
            self.rbw_mhz,
            self.vbw_mhz,
            self.impedance_ohm,
            self.calibration_db,
            self.scope_bw_mhz,
        ):
            widget.valueChanged.connect(self._on_profile_changed)
        self.vbw_enabled.toggled.connect(self._on_profile_changed)

        self.left_layout.addWidget(self.zero_span_panel)

    def _build_export_group(self) -> None:
        group = QGroupBox("结果保存")
        layout = QVBoxLayout(group)
        row = QHBoxLayout()
        save_dcm = QPushButton("保存当前 DCM 波形 CSV")
        save_zero = QPushButton("保存当前 Zero Span CSV")
        save_dcm.clicked.connect(self.save_dcm_waveform_dialog)
        save_zero.clicked.connect(self.save_zero_span_csv_dialog)
        row.addWidget(save_dcm)
        row.addWidget(save_zero)
        layout.addLayout(row)
        self.left_layout.addWidget(group)

    @staticmethod
    def _profile_spin(minimum: float, maximum: float, decimals: int, step: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setKeyboardTracking(True)
        spin.setMinimumWidth(150)
        return spin

    # ------------------------------------------------------------------
    # Parameter sync
    # ------------------------------------------------------------------
    def _toggle_zero_span_panel(self, checked: bool) -> None:
        self.zero_span_panel.setVisible(checked)
        self.zero_span_toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)

    def _to_display(self, key: str, value: float) -> float:
        if key in {"time_origin_s", "total_duration_s", "switching_start_s", "on_time_s", "freewheel_time_s"}:
            return value * 1e6
        if key in {"rise_time_s", "fall_time_s"}:
            return value * 1e9
        if key == "sample_rate_hz":
            return value / 1e9
        if key == "noise_rms_v":
            return value * 1e3
        if key in {"spike_ringing_frequency_hz", "discontinuous_resonance_frequency_hz"}:
            return value / 1e6
        if key in {"spike_decay_rate_per_s", "discontinuous_decay_rate_per_s"}:
            return value / 1e6
        return value

    def _from_display(self, key: str, value: float) -> float:
        if key in {"time_origin_s", "total_duration_s", "switching_start_s", "on_time_s", "freewheel_time_s"}:
            return value * 1e-6
        if key in {"rise_time_s", "fall_time_s"}:
            return value * 1e-9
        if key == "sample_rate_hz":
            return value * 1e9
        if key == "noise_rms_v":
            return value * 1e-3
        if key in {"spike_ringing_frequency_hz", "discontinuous_resonance_frequency_hz"}:
            return value * 1e6
        if key in {"spike_decay_rate_per_s", "discontinuous_decay_rate_per_s"}:
            return value * 1e6
        return value

    def _apply_parameters_to_controls(self, parameters: DcmSwParameters) -> None:
        self._syncing = True
        try:
            for key, control in self._parameter_controls.items():
                value = getattr(parameters, key)
                if key == "random_seed":
                    control.setValue(int(value))
                else:
                    control.setValue(self._to_display(key, float(value)))
        finally:
            self._syncing = False

    def _apply_profile_to_controls(self, profile: ZeroSpanProfile) -> None:
        self._syncing = True
        try:
            self.center_mhz.setValue(profile.center_frequency_hz / 1e6)
            self.rbw_mhz.setValue(profile.rbw_hz / 1e6)
            self.vbw_mhz.setValue(profile.vbw_hz / 1e6)
            self.vbw_enabled.setChecked(profile.vbw_enabled)
            self.impedance_ohm.setValue(profile.impedance_ohm)
            self.calibration_db.setValue(profile.calibration_db)
            self.scope_bw_mhz.setValue(profile.scope_analog_bandwidth_hz / 1e6)
        finally:
            self._syncing = False

    def _on_parameter_changed(self, key: str, display_value) -> None:
        if self._syncing:
            return
        value = int(display_value) if key == "random_seed" else self._from_display(key, float(display_value))
        self.parameters = replace(self.parameters, **{key: value})
        self._update_timer.start()

    def _on_profile_changed(self, *_args) -> None:
        if self._syncing:
            return
        self.profile = ZeroSpanProfile(
            center_frequency_hz=self.center_mhz.value() * 1e6,
            rbw_hz=self.rbw_mhz.value() * 1e6,
            vbw_hz=self.vbw_mhz.value() * 1e6,
            vbw_enabled=self.vbw_enabled.isChecked(),
            impedance_ohm=self.impedance_ohm.value(),
            calibration_db=self.calibration_db.value(),
            scope_analog_bandwidth_hz=self.scope_bw_mhz.value() * 1e6,
        )
        self._update_timer.start()

    # ------------------------------------------------------------------
    # Core recompute / plot
    # ------------------------------------------------------------------
    def _recompute(self) -> None:
        # DCM 正向模型和 Zero Span 转换是两个独立状态。即使转换配置暂时无效，
        # 也必须继续允许客户调 DCM 参数并实时刷新上方时域波形。
        try:
            waveform = generate_dcm_sw_waveform(self.parameters)
        except Exception as exc:
            self.current_waveform = None
            self.current_zero_span = None
            self.current_zero_span_error = None
            self._redraw(dcm_error=str(exc))
            self.status_label.setText(f"当前 DCM 参数组合无效：{exc}")
            LOGGER.debug("DCM 实时生成参数无效: %s", exc)
            return

        self.current_waveform = waveform

        try:
            zero = convert_dcm_waveform_to_zero_span(waveform, self.profile)
        except Exception as exc:
            self.current_zero_span = None
            self.current_zero_span_error = str(exc)
            self._redraw(zero_span_error=self.current_zero_span_error)
            self.status_label.setText(
                "DCM 波形已按当前参数更新；Zero Span 当前不可计算："
                f"{self.current_zero_span_error}。"
                "可继续调整全部 DCM 参数；修正 Center / RBW / 采样率 / 模拟带宽后，下图会自动恢复。"
            )
            LOGGER.debug("Zero Span 转换参数无效，但 DCM 继续联动: %s", exc)
            return

        self.current_zero_span = zero
        self.current_zero_span_error = None
        self._redraw()
        self.status_label.setText(
            "实时联动完成："
            f"DCM {waveform.points} 点 | "
            f"时间 {waveform.time_s[0]*1e6:.6g}~{waveform.time_s[-1]*1e6:.6g} µs | "
            f"Center={zero.center_frequency_hz/1e6:.6g} MHz | "
            f"RBW={zero.rbw_hz/1e6:.6g} MHz | "
            f"VBW={'OFF' if zero.vbw_hz is None else f'{zero.vbw_hz/1e6:.6g} MHz'}"
        )

    def _redraw(
        self,
        *,
        zero_span_error: str | None = None,
        dcm_error: str | None = None,
    ) -> None:
        self.figure.clear()
        ax1 = self.figure.add_subplot(211)
        ax2 = self.figure.add_subplot(212, sharex=ax1)

        waveform = self.current_waveform
        zero = self.current_zero_span

        if waveform is None:
            ax1.text(
                0.5,
                0.5,
                "DCM 波形当前不可生成" + (f"\n{dcm_error}" if dcm_error else ""),
                ha="center",
                va="center",
                transform=ax1.transAxes,
            )
            ax1.set_title("DCM SW 时域波形")
            ax1.set_ylabel("电压 (V)")
            ax2.text(
                0.5,
                0.5,
                "等待有效 DCM 波形",
                ha="center",
                va="center",
                transform=ax2.transAxes,
            )
            ax2.set_title("Zero Span")
            ax2.set_xlabel("绝对时间 (µs)")
            ax2.set_ylabel("功率 (dBm)")
            self.figure.tight_layout()
            self.canvas.draw_idle()
            return

        x_us = waveform.time_s * 1e6
        ax1.plot(x_us, waveform.voltage_v, linewidth=0.9, label="当前 DCM SW")
        ax1.plot(x_us, waveform.ideal_voltage_v, linewidth=0.75, alpha=0.75, label="理想轨迹")
        ax1.set_ylabel("电压 (V)")
        ax1.set_title("DCM SW 时域波形")
        ax1.grid(True, alpha=0.25)
        ax1.legend(loc="best")

        if zero is None:
            message = "Zero Span 当前不可计算"
            if zero_span_error:
                message += f"\n{zero_span_error}"
            ax2.text(
                0.5,
                0.5,
                message,
                ha="center",
                va="center",
                wrap=True,
                transform=ax2.transAxes,
            )
            ax2.set_xlim(float(x_us[0]), float(x_us[-1]))
            ax2.set_title("Zero Span（等待有效转换参数）")
        else:
            ax2.plot(zero.time_s * 1e6, zero.amplitude_dbm, linewidth=0.9, label="等效 FSW Zero Span")
            ax2.set_title(
                f"Zero Span：Center {zero.center_frequency_hz/1e6:.6g} MHz / "
                f"RBW {zero.rbw_hz/1e6:.6g} MHz"
            )
            ax2.grid(True, alpha=0.25)
            ax2.legend(loc="best")

        ax2.set_xlabel("绝对时间 (µs)")
        ax2.set_ylabel("功率 (dBm)")
        self.figure.tight_layout()
        self.canvas.draw_idle()

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------
    def load_dcm_parameters_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "加载 DCM 参数", "", "JSON (*.json)")
        if not path:
            return
        try:
            parameters = load_dcm_sw_parameters(path)
            self.parameters = parameters
            self._apply_parameters_to_controls(parameters)
            self.dcm_file_label.setText(f"当前：{path}")
            self._recompute()
        except Exception as exc:
            QMessageBox.critical(self, "加载 DCM 参数失败", str(exc))

    def save_dcm_parameters_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "保存当前 DCM 参数", "dcm_sw_parameters.json", "JSON (*.json)")
        if not path:
            return
        try:
            saved = save_dcm_sw_parameters(self.parameters, path)
            self.dcm_file_label.setText(f"当前：{saved}")
        except Exception as exc:
            QMessageBox.critical(self, "保存 DCM 参数失败", str(exc))

    def load_zero_span_profile_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "加载 Zero Span 转换参数", "", "JSON (*.json)")
        if not path:
            return
        try:
            self.profile = load_zero_span_profile(path)
            self._apply_profile_to_controls(self.profile)
            self._recompute()
        except Exception as exc:
            QMessageBox.critical(self, "加载转换参数失败", str(exc))

    def save_zero_span_profile_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "保存 Zero Span 转换参数", "zero_span_profile.json", "JSON (*.json)")
        if not path:
            return
        try:
            saved = save_zero_span_profile(self.profile, path)
            self.status_label.setText(f"已保存 Zero Span 转换参数：{saved}")
        except Exception as exc:
            QMessageBox.critical(self, "保存转换参数失败", str(exc))

    def save_dcm_waveform_dialog(self) -> None:
        if self.current_waveform is None:
            QMessageBox.information(self, "没有波形", "当前还没有有效 DCM 波形。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存当前 DCM 波形", "dcm_linked_waveform.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            saved, _ = save_dcm_sw_waveform(self.current_waveform, path, save_parameters_json=True)
            self.status_label.setText(f"已保存当前 DCM 波形：{saved}")
        except Exception as exc:
            QMessageBox.critical(self, "保存 DCM 波形失败", str(exc))

    def save_zero_span_csv_dialog(self) -> None:
        if self.current_zero_span is None:
            QMessageBox.information(self, "没有结果", "当前还没有有效 Zero Span 波形。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存当前 Zero Span 结果", "dcm_zero_span.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            path_obj = Path(path)
            if path_obj.suffix.lower() != ".csv":
                path_obj = path_obj.with_suffix(".csv")
            path_obj.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                {
                    "time_s": self.current_zero_span.time_s,
                    "amplitude_dbm": self.current_zero_span.amplitude_dbm,
                }
            ).to_csv(path_obj, index=False, encoding="utf-8-sig")
            self.status_label.setText(f"已保存当前 Zero Span CSV：{path_obj}")
        except Exception as exc:
            QMessageBox.critical(self, "保存 Zero Span CSV 失败", str(exc))
