from __future__ import annotations

from pathlib import Path

from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure
from PySide6.QtCore import QTimer, Signal
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
    QSpinBox,
    QSplitter,
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
from .logging_utils import get_logger
from .plotting import configure_matplotlib_chinese


configure_matplotlib_chinese()
LOGGER = get_logger()


class DcmSwGeneratorWidget(QWidget):
    """不加载文件，直接由已知参数生成 DCM SW 合成波形。"""

    waveform_ready_for_research = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.current_waveform: DcmSwWaveform | None = None
        self._parameter_widgets: list[QDoubleSpinBox | QSpinBox] = []
        self._updating_controls = False

        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.setInterval(180)
        self._auto_timer.timeout.connect(self._generate_silent)

        self._build_ui()
        self.apply_parameters(DcmSwParameters())
        QTimer.singleShot(0, self._generate_silent)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        splitter = QSplitter()
        root.addWidget(splitter)

        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        self._build_level_group(left_layout)
        self._build_timing_group(left_layout)
        self._build_spike_group(left_layout)
        self._build_discontinuous_group(left_layout)
        self._build_sampling_group(left_layout)
        self._build_action_group(left_layout)
        left_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left_container)
        splitter.addWidget(scroll)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        splitter.addWidget(right)
        splitter.setSizes([500, 1040])

        self.figure = Figure(figsize=(10, 7))
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        right_layout.addWidget(self.toolbar)
        right_layout.addWidget(self.canvas, 1)

        self.model_label = QLabel(
            "模型：单个 DCM 开关事件。上升沿 → 高电平导通 → 下降沿 → 续流低电平 → 断续阻尼谐振。"
            "当前先建立可重复真值，后续再根据真实 DCM SW 数据修正模型。"
        )
        self.model_label.setWordWrap(True)
        right_layout.addWidget(self.model_label)

        self.status_label = QLabel("准备生成默认 DCM SW 波形")
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)

    def _double_spin(
        self,
        minimum: float,
        maximum: float,
        decimals: int,
        step: float,
    ) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(minimum, maximum)
        box.setDecimals(decimals)
        box.setSingleStep(step)
        box.setKeyboardTracking(False)
        box.valueChanged.connect(self._schedule_generate)
        self._parameter_widgets.append(box)
        return box

    def _int_spin(self, minimum: int, maximum: int) -> QSpinBox:
        box = QSpinBox()
        box.setRange(minimum, maximum)
        box.setKeyboardTracking(False)
        box.valueChanged.connect(self._schedule_generate)
        self._parameter_widgets.append(box)
        return box

    def _build_level_group(self, parent: QVBoxLayout) -> None:
        group = QGroupBox("电平参数")
        form = QFormLayout(group)
        self.baseline_v = self._double_spin(-10000.0, 10000.0, 6, 0.1)
        self.high_v = self._double_spin(-10000.0, 10000.0, 6, 0.1)
        self.freewheel_v = self._double_spin(-10000.0, 10000.0, 6, 0.1)
        form.addRow("基线电压 (V)", self.baseline_v)
        form.addRow("开通高电平电压 (V)", self.high_v)
        form.addRow("续流低电平电压 (V)", self.freewheel_v)
        parent.addWidget(group)

    def _build_timing_group(self, parent: QVBoxLayout) -> None:
        group = QGroupBox("时间参数")
        form = QFormLayout(group)
        self.total_us = self._double_spin(0.001, 1e9, 6, 1.0)
        self.start_us = self._double_spin(0.0, 1e9, 6, 0.1)
        self.on_us = self._double_spin(0.0, 1e9, 6, 0.1)
        self.freewheel_us = self._double_spin(0.0, 1e9, 6, 0.1)
        self.rise_ns = self._double_spin(0.001, 1e9, 6, 1.0)
        self.fall_ns = self._double_spin(0.001, 1e9, 6, 1.0)
        form.addRow("总显示时长 (µs)", self.total_us)
        form.addRow("开关起始时间 (µs)", self.start_us)
        form.addRow("导通时间 (µs)", self.on_us)
        form.addRow("续流时间 (µs)", self.freewheel_us)
        form.addRow("上升沿时间 (ns)", self.rise_ns)
        form.addRow("下降沿时间 (ns)", self.fall_ns)
        parent.addWidget(group)

    def _build_spike_group(self, parent: QVBoxLayout) -> None:
        group = QGroupBox("开关沿尖峰 / 寄生振铃")
        form = QFormLayout(group)
        self.rise_spike_v = self._double_spin(0.0, 10000.0, 6, 0.1)
        self.fall_spike_v = self._double_spin(0.0, 10000.0, 6, 0.1)
        self.spike_freq_mhz = self._double_spin(0.0, 100000.0, 6, 1.0)
        self.spike_decay_per_us = self._double_spin(0.0, 1e6, 6, 0.1)
        form.addRow("上升沿尖峰幅度 (V)", self.rise_spike_v)
        form.addRow("下降沿尖峰幅度 (V)", self.fall_spike_v)
        form.addRow("尖峰寄生振荡频率 (MHz)", self.spike_freq_mhz)
        form.addRow("尖峰衰减速率 α (1/µs)", self.spike_decay_per_us)
        note = QLabel("尖峰模型：A·exp(-αt)·cos(2πft)。上升沿取正幅值，下降沿取负幅值。")
        note.setWordWrap(True)
        form.addRow(note)
        parent.addWidget(group)

    def _build_discontinuous_group(self, parent: QVBoxLayout) -> None:
        group = QGroupBox("DCM 断续区谐振")
        form = QFormLayout(group)
        self.dcm_amp_v = self._double_spin(-10000.0, 10000.0, 6, 0.1)
        self.dcm_freq_mhz = self._double_spin(0.0, 100000.0, 6, 0.1)
        self.dcm_decay_per_us = self._double_spin(0.0, 1e6, 6, 0.05)
        form.addRow("断续谐振初始振幅 (V)", self.dcm_amp_v)
        form.addRow("断续谐振频率 (MHz)", self.dcm_freq_mhz)
        form.addRow("断续谐振衰减速率 α (1/µs)", self.dcm_decay_per_us)
        note = QLabel("续流结束后，以基线电压为中心生成阻尼谐振。")
        note.setWordWrap(True)
        form.addRow(note)
        parent.addWidget(group)

    def _build_sampling_group(self, parent: QVBoxLayout) -> None:
        group = QGroupBox("示波器采样 / 噪声")
        form = QFormLayout(group)
        self.noise_mv = self._double_spin(0.0, 1e6, 6, 1.0)
        self.sample_gsa = self._double_spin(0.000001, 1000.0, 6, 0.1)
        self.random_seed = self._int_spin(0, 2_147_483_647)
        form.addRow("示波器底噪 RMS (mV)", self.noise_mv)
        form.addRow("采样率 (GSa/s)", self.sample_gsa)
        form.addRow("随机种子", self.random_seed)
        note = QLabel("随机种子固定后，同一组参数每次生成完全一致，便于提取算法做重复对比。")
        note.setWordWrap(True)
        form.addRow(note)
        parent.addWidget(group)

    def _build_action_group(self, parent: QVBoxLayout) -> None:
        group = QGroupBox("生成与保存")
        layout = QVBoxLayout(group)

        self.auto_generate_check = QCheckBox("参数变化后自动重新生成")
        self.auto_generate_check.setChecked(True)
        layout.addWidget(self.auto_generate_check)

        row1 = QHBoxLayout()
        generate_btn = QPushButton("重新生成")
        defaults_btn = QPushButton("恢复默认参数")
        generate_btn.clicked.connect(self.generate_waveform)
        defaults_btn.clicked.connect(self.restore_defaults)
        row1.addWidget(generate_btn)
        row1.addWidget(defaults_btn)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        save_wave_btn = QPushButton("保存波形 CSV + 参数 JSON")
        send_btn = QPushButton("发送到波形研究")
        save_wave_btn.clicked.connect(self.save_waveform_dialog)
        send_btn.clicked.connect(self.send_to_research)
        row2.addWidget(save_wave_btn)
        row2.addWidget(send_btn)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        save_params_btn = QPushButton("保存参数 JSON")
        load_params_btn = QPushButton("加载参数 JSON")
        save_params_btn.clicked.connect(self.save_parameters_dialog)
        load_params_btn.clicked.connect(self.load_parameters_dialog)
        row3.addWidget(save_params_btn)
        row3.addWidget(load_params_btn)
        layout.addLayout(row3)

        parent.addWidget(group)

    # ------------------------------------------------------------------
    # Parameters
    # ------------------------------------------------------------------
    def collect_parameters(self) -> DcmSwParameters:
        return DcmSwParameters(
            baseline_voltage_v=self.baseline_v.value(),
            on_high_voltage_v=self.high_v.value(),
            freewheel_low_voltage_v=self.freewheel_v.value(),
            total_duration_s=self.total_us.value() * 1e-6,
            switching_start_s=self.start_us.value() * 1e-6,
            on_time_s=self.on_us.value() * 1e-6,
            freewheel_time_s=self.freewheel_us.value() * 1e-6,
            rise_time_s=self.rise_ns.value() * 1e-9,
            fall_time_s=self.fall_ns.value() * 1e-9,
            rise_spike_amplitude_v=self.rise_spike_v.value(),
            fall_spike_amplitude_v=self.fall_spike_v.value(),
            spike_ringing_frequency_hz=self.spike_freq_mhz.value() * 1e6,
            spike_decay_rate_per_s=self.spike_decay_per_us.value() * 1e6,
            discontinuous_initial_amplitude_v=self.dcm_amp_v.value(),
            discontinuous_resonance_frequency_hz=self.dcm_freq_mhz.value() * 1e6,
            discontinuous_decay_rate_per_s=self.dcm_decay_per_us.value() * 1e6,
            noise_rms_v=self.noise_mv.value() * 1e-3,
            sample_rate_hz=self.sample_gsa.value() * 1e9,
            random_seed=self.random_seed.value(),
        )

    def apply_parameters(self, p: DcmSwParameters) -> None:
        self._updating_controls = True
        try:
            self.baseline_v.setValue(p.baseline_voltage_v)
            self.high_v.setValue(p.on_high_voltage_v)
            self.freewheel_v.setValue(p.freewheel_low_voltage_v)
            self.total_us.setValue(p.total_duration_s * 1e6)
            self.start_us.setValue(p.switching_start_s * 1e6)
            self.on_us.setValue(p.on_time_s * 1e6)
            self.freewheel_us.setValue(p.freewheel_time_s * 1e6)
            self.rise_ns.setValue(p.rise_time_s * 1e9)
            self.fall_ns.setValue(p.fall_time_s * 1e9)
            self.rise_spike_v.setValue(p.rise_spike_amplitude_v)
            self.fall_spike_v.setValue(p.fall_spike_amplitude_v)
            self.spike_freq_mhz.setValue(p.spike_ringing_frequency_hz / 1e6)
            self.spike_decay_per_us.setValue(p.spike_decay_rate_per_s / 1e6)
            self.dcm_amp_v.setValue(p.discontinuous_initial_amplitude_v)
            self.dcm_freq_mhz.setValue(p.discontinuous_resonance_frequency_hz / 1e6)
            self.dcm_decay_per_us.setValue(p.discontinuous_decay_rate_per_s / 1e6)
            self.noise_mv.setValue(p.noise_rms_v * 1e3)
            self.sample_gsa.setValue(p.sample_rate_hz / 1e9)
            self.random_seed.setValue(int(p.random_seed))
        finally:
            self._updating_controls = False
        self._schedule_generate()

    def restore_defaults(self) -> None:
        self.apply_parameters(DcmSwParameters())
        self._generate_silent()

    # ------------------------------------------------------------------
    # Generation / plotting
    # ------------------------------------------------------------------
    def _schedule_generate(self) -> None:
        if self._updating_controls or not self.auto_generate_check.isChecked():
            return
        self._auto_timer.start()

    def _generate_silent(self) -> None:
        self._generate(show_error=False)

    def generate_waveform(self, checked: bool = False) -> None:
        del checked
        self._generate(show_error=True)

    def _generate(self, *, show_error: bool) -> None:
        try:
            waveform = generate_dcm_sw_waveform(self.collect_parameters())
            self.current_waveform = waveform
            self._redraw(waveform)
            e = waveform.events
            self.status_label.setText(
                f"生成完成：{waveform.points} 点 | Fs={waveform.sample_rate_hz/1e9:.6g} GSa/s | "
                f"上升沿 {e.rise_start_s*1e6:.6g}~{e.rise_end_s*1e6:.6g} µs | "
                f"高电平结束 {e.high_end_s*1e6:.6g} µs | "
                f"下降沿结束 {e.fall_end_s*1e6:.6g} µs | "
                f"续流结束/断续谐振开始 {e.freewheel_end_s*1e6:.6g} µs"
            )
            LOGGER.info("生成 DCM SW 合成波形 points=%d", waveform.points)
        except Exception as exc:
            self.current_waveform = None
            self.status_label.setText(f"参数无效：{exc}")
            if show_error:
                QMessageBox.warning(self, "DCM SW 参数无效", str(exc))

    def _redraw(self, waveform: DcmSwWaveform) -> None:
        self.figure.clear()
        ax1 = self.figure.add_subplot(211)
        ax2 = self.figure.add_subplot(212)

        x_us = waveform.time_s * 1e6
        ax1.plot(x_us, waveform.voltage_v, linewidth=0.9, label="最终 SW 波形")
        ax1.plot(x_us, waveform.ideal_voltage_v, linewidth=0.8, alpha=0.8, label="理想开关轨迹")

        event_lines = (
            (waveform.events.rise_start_s, "上升沿开始"),
            (waveform.events.rise_end_s, "上升沿结束"),
            (waveform.events.high_end_s, "下降沿开始"),
            (waveform.events.fall_end_s, "下降沿结束"),
            (waveform.events.freewheel_end_s, "断续谐振开始"),
        )
        for x_s, _ in event_lines:
            ax1.axvline(x_s * 1e6, linestyle="--", alpha=0.25)

        ax1.set_title("DCM 模式 SW 合成波形（已知真值）")
        ax1.set_xlabel("时间 (µs)")
        ax1.set_ylabel("电压 (V)")
        ax1.grid(True, alpha=0.3)
        ax1.legend()

        ax2.plot(x_us, waveform.spike_component_v, linewidth=0.8, label="开关沿尖峰 / 寄生振铃")
        ax2.plot(
            x_us,
            waveform.discontinuous_component_v,
            linewidth=0.8,
            label="DCM 断续谐振",
        )
        ax2.plot(x_us, waveform.noise_component_v, linewidth=0.55, alpha=0.65, label="示波器底噪")
        ax2.set_title("已知扰动组成（用于后续提取算法真值对照）")
        ax2.set_xlabel("时间 (µs)")
        ax2.set_ylabel("分量电压 (V)")
        ax2.grid(True, alpha=0.3)
        ax2.legend()

        self.figure.tight_layout()
        self.canvas.draw()

    # ------------------------------------------------------------------
    # Save / load
    # ------------------------------------------------------------------
    def save_waveform_dialog(self) -> None:
        if self.current_waveform is None:
            self.generate_waveform()
        if self.current_waveform is None:
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存 DCM SW 合成波形",
            "synthetic_dcm_sw.csv",
            "CSV (*.csv)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            csv_path, params_path = save_dcm_sw_waveform(
                self.current_waveform,
                path,
                save_parameters_json=True,
            )
            self.status_label.setText(
                f"已保存合成波形：{csv_path}；真值参数：{params_path.name if params_path else ''}"
            )
        except Exception as exc:
            LOGGER.exception("保存 DCM SW 合成波形失败")
            QMessageBox.critical(self, "保存失败", str(exc))

    def save_parameters_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存 DCM SW 参数",
            "dcm_sw_parameters.json",
            "JSON (*.json)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            save_dcm_sw_parameters(self.collect_parameters(), Path(path))
            self.status_label.setText(f"已保存 DCM SW 参数：{path}")
        except Exception as exc:
            QMessageBox.critical(self, "保存参数失败", str(exc))

    def load_parameters_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "加载 DCM SW 参数",
            "",
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            self.apply_parameters(load_dcm_sw_parameters(path))
            self._generate_silent()
            self.status_label.setText(f"已加载参数并重新生成：{path}")
        except Exception as exc:
            QMessageBox.critical(self, "加载参数失败", str(exc))

    def send_to_research(self) -> None:
        if self.current_waveform is None:
            self.generate_waveform()
        if self.current_waveform is None:
            return
        self.waveform_ready_for_research.emit(self.current_waveform)
        self.status_label.setText("已将当前合成波形发送到“波形研究”页面")
