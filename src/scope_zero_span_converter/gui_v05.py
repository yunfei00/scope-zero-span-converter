from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QFileDialog, QGroupBox, QMessageBox, QPushButton

from . import __version__
from .dcm_analysis_widget import DcmAnalysisWidget
from .dcm_parameter_extractor_widget_v7 import DcmParameterExtractorWidget
from .dcm_sw_generator import DcmSwWaveform
from .dcm_sw_generator_widget_v3 import DcmSwGeneratorWidget
from .diagnostics import export_diagnostic_bundle
from .gui_v04 import MainWindow as WaveformResearchMainWindow
from .logging_utils import get_logger
from .waveform_quality import analyze_time_axis


LOGGER = get_logger()


class MainWindow(WaveformResearchMainWindow):
    """波形研究 + DCM SW 生成/反演 + DCM 时域/幅相频域/Zero Span 联动。"""

    TAB_WAVEFORM_RESEARCH = "waveform_research"
    TAB_DCM_GENERATOR = "dcm_generator"
    TAB_DCM_EXTRACTOR = "dcm_extractor"
    TAB_DCM_ANALYSIS = "dcm_analysis"
    TAB_BATCH = "batch_conversion"

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(
            f"Scope Zero Span Converter {__version__} - DCM 综合分析工作台"
        )

        self.dcm_generator_tab = DcmSwGeneratorWidget(self)
        self._enable_ideal_edge_controls()
        self.dcm_generator_tab.waveform_ready_for_research.connect(
            self._accept_generated_dcm_waveform
        )
        self.tabs.insertTab(1, self.dcm_generator_tab, "DCM SW 生成器")

        self.dcm_extractor_tab = DcmParameterExtractorWidget(self)
        self.tabs.insertTab(2, self.dcm_extractor_tab, "DCM 参数提取")

        self.dcm_analysis_tab = DcmAnalysisWidget(self)
        # 保留旧属性名，避免外部脚本/既有测试在商业化收口期间失效。
        self.dcm_zero_span_tab = self.dcm_analysis_tab
        self.tabs.insertTab(3, self.dcm_analysis_tab, "DCM 综合分析")
        self._install_diagnostic_export_button()
        LOGGER.info(
            "DCM generator, extractor, magnitude/phase spectrum and Zero Span linked page ready"
        )

    def tab_id_for_index(self, index: int) -> str:
        """Return a stable tab identifier instead of persisting a fragile index."""
        if not 0 <= index < self.tabs.count():
            return self.TAB_WAVEFORM_RESEARCH
        widget = self.tabs.widget(index)
        mapping = {
            self.research_tab: self.TAB_WAVEFORM_RESEARCH,
            self.dcm_generator_tab: self.TAB_DCM_GENERATOR,
            self.dcm_extractor_tab: self.TAB_DCM_EXTRACTOR,
            self.dcm_analysis_tab: self.TAB_DCM_ANALYSIS,
            self.batch_tab: self.TAB_BATCH,
        }
        return mapping.get(widget, self.TAB_WAVEFORM_RESEARCH)

    def index_for_tab_id(self, tab_id: str) -> int:
        """Resolve a stable tab identifier; return -1 for unknown values."""
        mapping = {
            self.TAB_WAVEFORM_RESEARCH: self.research_tab,
            self.TAB_DCM_GENERATOR: self.dcm_generator_tab,
            self.TAB_DCM_EXTRACTOR: self.dcm_extractor_tab,
            self.TAB_DCM_ANALYSIS: self.dcm_analysis_tab,
            self.TAB_BATCH: self.batch_tab,
        }
        widget = mapping.get(tab_id)
        return self.tabs.indexOf(widget) if widget is not None else -1

    def load_waveform_from_ui(self) -> None:
        """Load through the base workflow, then expose the shared quality report."""
        previous_time = self.waveform_time
        previous_voltage = self.waveform_voltage
        super().load_waveform_from_ui()

        # gui_v04 currently catches load errors internally and deliberately keeps
        # the previous valid waveform on screen. Only append a quality summary if
        # a genuinely new waveform object was installed; otherwise a failed load
        # could misleadingly label the previous waveform as the failed file's PASS.
        if (
            self.waveform_time is previous_time
            and self.waveform_voltage is previous_voltage
        ):
            return
        if self.waveform_time is None or len(self.waveform_time) < 2:
            return

        quality = analyze_time_axis(self.waveform_time)
        # load_waveform() has already applied the hard quality gate. This line is
        # customer-facing traceability: show the actual sampling assumptions used
        # by FFT / Zero Span instead of leaving them implicit.
        self.status_label.setText(
            f"{self.status_label.text()} | 数据质量：{quality.summary()} | "
            f"Nyquist={quality.nyquist_hz/1e6:.6g} MHz"
        )

    def _install_diagnostic_export_button(self) -> None:
        """Add customer-support export next to the existing template/log tools."""

        group = next(
            (item for item in self.findChildren(QGroupBox) if item.title() == "配置模板"),
            None,
        )
        if group is None or group.layout() is None:
            return

        self.export_diagnostics_btn = QPushButton("导出诊断包")
        self.export_diagnostics_btn.setToolTip(
            "导出软件版本、系统/Python环境和应用日志；默认不包含客户波形或参数文件。"
        )
        self.export_diagnostics_btn.clicked.connect(self._export_diagnostics_dialog)
        group.layout().addWidget(self.export_diagnostics_btn)

    def _export_diagnostics_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出诊断包",
            f"ScopeZeroSpanConverter-{__version__}-Diagnostics.zip",
            "ZIP (*.zip)",
        )
        if not path:
            return
        try:
            saved = export_diagnostic_bundle(path)
            QMessageBox.information(
                self,
                "诊断包已导出",
                f"已保存：{saved}\n\n诊断包不包含客户波形和参数文件。",
            )
            LOGGER.info("diagnostic bundle exported path=%s", saved)
        except Exception as exc:
            LOGGER.exception("导出诊断包失败")
            QMessageBox.critical(self, "导出诊断包失败", str(exc))

    def _enable_ideal_edge_controls(self) -> None:
        for control in (
            self.dcm_generator_tab.rise_ns,
            self.dcm_generator_tab.fall_ns,
        ):
            current_value = control.value()
            control._hard_min = 0.0
            control._soft_min = 0.0
            control.spin.setMinimum(0.0)
            control.slider.setValue(control._value_to_slider(current_value))

        self.dcm_generator_tab.model_label.setText(
            "模型：单个 DCM 开关事件。上升沿 → 高电平导通 → 下降沿 → 续流低电平 → 断续阻尼谐振。"
            "左侧每个参数均为“滑块粗调 + 数值框精调”，两者实时双向联动；"
            "时间轴起点与总显示时长共同定义绝对时间范围；"
            "上升沿时间或下降沿时间设为 0 ns 时表示理想瞬时阶跃。"
        )

    def _accept_generated_dcm_waveform(self, waveform: DcmSwWaveform) -> None:
        self.waveform_time = np.asarray(waveform.time_s, dtype=float).copy()
        self.waveform_voltage = np.asarray(waveform.voltage_v, dtype=float).copy()
        self.waveform_sample_rate = float(waveform.sample_rate_hz)
        self.current_region = None
        self.region_conversion = None
        self._region_time = None
        self._region_voltage = None
        self._zoom_to_region = False

        self.waveform_edit.clear()

        self._sync_roi_controls()
        self._redraw_waveform_and_conversion()
        self.tabs.setCurrentWidget(self.research_tab)

        e = waveform.events
        quality = analyze_time_axis(self.waveform_time)
        self.status_label.setText(
            "已从 DCM SW 生成器载入内存波形："
            f"{waveform.points} 点 | Fs={waveform.sample_rate_hz/1e9:.6g} GSa/s | "
            f"时间范围 {waveform.time_s[0]*1e6:.6g}~{waveform.time_s[-1]*1e6:.6g} µs | "
            f"开关起始 {e.rise_start_s*1e6:.6g} µs | "
            f"断续谐振起始 {e.freewheel_end_s*1e6:.6g} µs | "
            f"数据质量 {quality.status.upper()}，Nyquist={quality.nyquist_hz/1e6:.6g} MHz。"
            "现在可直接框选研究区域；如需留档，请先在生成器页保存 CSV + 参数 JSON。"
        )
        LOGGER.info(
            "generated DCM SW waveform sent to research points=%d fs=%g quality=%s",
            waveform.points,
            waveform.sample_rate_hz,
            quality.status,
        )
