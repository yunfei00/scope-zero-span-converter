from __future__ import annotations

import numpy as np

from .dcm_sw_generator import DcmSwWaveform
from .dcm_sw_generator_widget import DcmSwGeneratorWidget
from .gui_v04 import MainWindow as WaveformResearchMainWindow
from .logging_utils import get_logger


LOGGER = get_logger()


class MainWindow(WaveformResearchMainWindow):
    """v0.4 波形研究界面 + 独立 DCM SW 真值波形生成器。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Scope Zero Span Converter v0.4 - 波形研究 / DCM SW 生成器")

        self.dcm_generator_tab = DcmSwGeneratorWidget(self)
        self.dcm_generator_tab.waveform_ready_for_research.connect(
            self._accept_generated_dcm_waveform
        )
        self.tabs.insertTab(1, self.dcm_generator_tab, "DCM SW 生成器")
        LOGGER.info("DCM SW generator tab ready")

    def _accept_generated_dcm_waveform(self, waveform: DcmSwWaveform) -> None:
        """把生成器的内存波形直接送入现有 ROI 研究链路，无需先保存/再加载。"""

        self.waveform_time = np.asarray(waveform.time_s, dtype=float).copy()
        self.waveform_voltage = np.asarray(waveform.voltage_v, dtype=float).copy()
        self.waveform_sample_rate = float(waveform.sample_rate_hz)
        self.current_region = None
        self.region_conversion = None
        self._region_time = None
        self._region_voltage = None
        self._zoom_to_region = False

        # 避免把之前真实文件路径误记成当前合成波形来源。
        self.waveform_edit.clear()

        self._sync_roi_controls()
        self._redraw_waveform_and_conversion()
        self.tabs.setCurrentWidget(self.research_tab)

        e = waveform.events
        self.status_label.setText(
            "已从 DCM SW 生成器载入内存波形："
            f"{waveform.points} 点 | Fs={waveform.sample_rate_hz/1e9:.6g} GSa/s | "
            f"开关起始 {e.rise_start_s*1e6:.6g} µs | "
            f"断续谐振起始 {e.freewheel_end_s*1e6:.6g} µs。"
            "现在可直接框选研究区域；如需留档，请先在生成器页保存 CSV + 参数 JSON。"
        )
        LOGGER.info(
            "generated DCM SW waveform sent to research points=%d fs=%g",
            waveform.points,
            waveform.sample_rate_hz,
        )
