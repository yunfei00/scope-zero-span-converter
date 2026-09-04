from __future__ import annotations

import numpy as np

from .dcm_parameter_extractor_widget_v7 import DcmParameterExtractorWidget
from .dcm_sw_generator import DcmSwWaveform
from .dcm_sw_generator_widget_v3 import DcmSwGeneratorWidget
from .dcm_zero_span_widget import DcmZeroSpanWidget
from .gui_v04 import MainWindow as WaveformResearchMainWindow
from .logging_utils import get_logger


LOGGER = get_logger()


class MainWindow(WaveformResearchMainWindow):
    """波形研究 + DCM SW 生成/反演 + DCM → Zero Span 实时联动。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(
            "Scope Zero Span Converter - 波形研究 / DCM SW / Zero Span 联动"
        )

        self.dcm_generator_tab = DcmSwGeneratorWidget(self)
        self._enable_ideal_edge_controls()
        self.dcm_generator_tab.waveform_ready_for_research.connect(
            self._accept_generated_dcm_waveform
        )
        self.tabs.insertTab(1, self.dcm_generator_tab, "DCM SW 生成器")

        self.dcm_extractor_tab = DcmParameterExtractorWidget(self)
        self.tabs.insertTab(2, self.dcm_extractor_tab, "DCM 参数提取")

        self.dcm_zero_span_tab = DcmZeroSpanWidget(self)
        self.tabs.insertTab(3, self.dcm_zero_span_tab, "DCM → Zero Span")
        LOGGER.info("DCM generator, extractor and Zero Span linked page ready")

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
        self.status_label.setText(
            "已从 DCM SW 生成器载入内存波形："
            f"{waveform.points} 点 | Fs={waveform.sample_rate_hz/1e9:.6g} GSa/s | "
            f"时间范围 {waveform.time_s[0]*1e6:.6g}~{waveform.time_s[-1]*1e6:.6g} µs | "
            f"开关起始 {e.rise_start_s*1e6:.6g} µs | "
            f"断续谐振起始 {e.freewheel_end_s*1e6:.6g} µs。"
            "现在可直接框选研究区域；如需留档，请先在生成器页保存 CSV + 参数 JSON。"
        )
        LOGGER.info(
            "generated DCM SW waveform sent to research points=%d fs=%g",
            waveform.points,
            waveform.sample_rate_hz,
        )
