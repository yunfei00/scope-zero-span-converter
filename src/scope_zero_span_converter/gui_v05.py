from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidgetItem,
)

from . import __version__
from .batch import BatchItemResult, BatchRunResult
from .batch_worker import BatchWorkerTask
from .conversion_worker import FullConversionWorkerResult, FullConversionWorkerTask
from .dcm_analysis.widget import DcmAnalysisWidget
from .dcm_extractor.widget import DcmParameterExtractorWidget
from .dcm_generator.widget import DcmSwGeneratorWidget
from .dcm_sw_generator import DcmSwWaveform
from .diagnostics import export_diagnostic_bundle
from .gui_v04 import MainWindow as WaveformResearchMainWindow
from .logging_utils import get_logger
from .roi_worker import RoiConversionWorkerResult, RoiConversionWorkerTask
from .waveform_quality import analyze_time_axis


LOGGER = get_logger()


class MainWindow(WaveformResearchMainWindow):
    """波形研究 + DCM SW 生成/反演 + DCM 时域/幅相频域/Zero Span 联动。"""

    TAB_WAVEFORM_RESEARCH = "waveform_research"
    TAB_DCM_GENERATOR = "dcm_generator"
    TAB_DCM_EXTRACTOR = "dcm_extractor"
    TAB_DCM_ANALYSIS = "dcm_analysis"
    TAB_BATCH = "batch_conversion"

    ROI_BACKGROUND_THRESHOLD_POINTS = 250_000

    def __init__(self) -> None:
        # Base construction connects its ROI debounce timer to the dynamically
        # resolved update_region_conversion(), so request-generation state must
        # exist before super().__init__().
        self._roi_generation = 0
        self._roi_active_request_id: int | None = None
        self._roi_task: RoiConversionWorkerTask | None = None
        self._roi_pending_payload: tuple | None = None

        super().__init__()
        self.setWindowTitle(
            f"Scope Zero Span Converter {__version__} - DCM 综合分析工作台"
        )

        self._worker_pool = QThreadPool.globalInstance()
        self._conversion_task: FullConversionWorkerTask | None = None
        self._batch_task: BatchWorkerTask | None = None
        self._install_batch_worker_controls()

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
        # Any in-flight large ROI result belongs to the previously loaded source.
        # Advancing generation makes it stale immediately, before the new 250 ms
        # debounce timer fires.
        self._roi_generation += 1
        self._roi_pending_payload = None

        previous_time = self.waveform_time
        previous_voltage = self.waveform_voltage
        super().load_waveform_from_ui()

        if (
            self.waveform_time is previous_time
            and self.waveform_voltage is previous_voltage
        ):
            return
        if self.waveform_time is None or len(self.waveform_time) < 2:
            return

        quality = analyze_time_axis(self.waveform_time)
        self.status_label.setText(
            f"{self.status_label.text()} | 数据质量：{quality.summary()} | "
            f"Nyquist={quality.nyquist_hz/1e6:.6g} MHz"
        )

    # ------------------------------------------------------------------
    # ROI conversion: small synchronous / large latest-wins worker
    # ------------------------------------------------------------------
    def _schedule_region_conversion(self) -> None:
        if not self.auto_update_roi_check.isChecked():
            return
        self._roi_generation += 1
        self._conversion_timer.start()

    def update_region_conversion(self) -> None:
        if self.waveform_time is None:
            return
        metadata = Path(self.metadata_edit.text().strip())
        if not metadata.exists():
            self._roi_generation += 1
            self._roi_pending_payload = None
            self.region_conversion = None
            self._redraw_waveform_and_conversion()
            self.status_label.setText(
                "已选择研究区域；选择 metadata.json 后可联动更新下方转换波形"
            )
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
            if t is None or v is None:
                return
        except Exception as exc:
            self.region_conversion = None
            self._redraw_waveform_and_conversion()
            self.status_label.setText(f"研究区域转换配置无效：{exc}")
            return

        if len(t) < self.ROI_BACKGROUND_THRESHOLD_POINTS:
            # Signal delivery from any older worker cannot interrupt this GUI-thread
            # calculation; generation checks will reject it afterwards.
            super().update_region_conversion()
            return

        request_id = self._roi_generation
        payload = (request_id, t, v, metadata, cfg, origin_s)
        self.region_conversion = None
        self._redraw_waveform_and_conversion()

        if self._roi_task is not None:
            # Only retain the newest expensive request. Do not pile up FFT jobs
            # while the customer drags ROI bounds or adjusts Center/RBW.
            self._roi_pending_payload = payload
            self.status_label.setText(
                f"大研究区转换更新已排队：{len(t)} 点；等待当前后台 FFT 完成后只计算最新参数。"
            )
            return

        self._start_roi_worker(payload)

    def _start_roi_worker(self, payload: tuple) -> None:
        request_id, t, v, metadata, cfg, origin_s = payload
        task = RoiConversionWorkerTask(
            request_id=request_id,
            time_s=t,
            voltage_v=v,
            metadata_path=metadata,
            config=cfg,
            origin_s=origin_s,
        )
        task.signals.finished.connect(self._on_roi_worker_finished)
        task.signals.failed.connect(self._on_roi_worker_failed)
        self._roi_active_request_id = int(request_id)
        self._roi_task = task
        self._roi_pending_payload = None
        self.status_label.setText(
            f"大研究区 Zero Span 转换后台计算中：{len(t)} 点；窗口保持响应。"
        )
        self._worker_pool.start(task)

    def _release_roi_worker_and_start_pending(self) -> bool:
        self._roi_active_request_id = None
        self._roi_task = None
        pending = self._roi_pending_payload
        self._roi_pending_payload = None
        if pending is not None:
            self._start_roi_worker(pending)
            return True
        return False

    def _apply_roi_worker_result(self, payload: RoiConversionWorkerResult) -> None:
        result = payload.conversion
        self.region_conversion = (result, payload.origin_s)
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
        points = len(result.time_s)
        self.status_label.setText(
            f"大研究区后台联动转换完成：{points} 点 | "
            f"Center={result.center_frequency_hz/1e6:.6g} MHz | "
            f"RBW={result.rbw_hz/1e6:.6g} MHz"
        )

    def _on_roi_worker_finished(self, payload: RoiConversionWorkerResult) -> None:
        is_active = payload.request_id == self._roi_active_request_id
        is_latest = payload.request_id == self._roi_generation
        pending_exists = self._roi_pending_payload is not None

        if is_active and is_latest and not pending_exists:
            self._apply_roi_worker_result(payload)

        self._release_roi_worker_and_start_pending()

    def _on_roi_worker_failed(self, request_id: int, message: str) -> None:
        is_active = request_id == self._roi_active_request_id
        is_latest = request_id == self._roi_generation
        pending_exists = self._roi_pending_payload is not None

        if is_active and is_latest and not pending_exists:
            self.region_conversion = None
            self._redraw_waveform_and_conversion()
            self.status_label.setText(f"研究区域后台转换失败：{message}")
            LOGGER.error("ROI conversion worker failed: %s", message)

        self._release_roi_worker_and_start_pending()

    # ------------------------------------------------------------------
    # Non-blocking full conversion
    # ------------------------------------------------------------------
    def run_full_conversion(self) -> None:
        if self._conversion_task is not None:
            return
        try:
            cfg = self.collect_config()
        except Exception as exc:
            LOGGER.exception("完整转换配置无效")
            QMessageBox.critical(self, "转换配置无效", str(exc))
            return

        task = FullConversionWorkerTask(cfg)
        task.signals.finished.connect(self._on_full_conversion_finished)
        task.signals.failed.connect(self._on_full_conversion_failed)
        self._conversion_task = task
        self.convert_button.setEnabled(False)
        self.status_label.setText(
            "完整转换已进入后台：正在执行 Zero Span 转换、结果保存和可选 PNG 输出；窗口保持响应。"
        )
        self._worker_pool.start(task)

    def _release_full_conversion_task(self) -> None:
        self._conversion_task = None
        self.convert_button.setEnabled(True)

    def _on_full_conversion_finished(self, payload: FullConversionWorkerResult) -> None:
        self._release_full_conversion_task()
        self.config = payload.config
        conversion = payload.conversion
        extras: list[str] = []
        if conversion.output_csv is not None:
            extras.append("CSV")
        if conversion.output_plot is not None:
            extras.append("PNG")
        if conversion.output_metadata is not None:
            extras.append("metadata")
        if conversion.comparison is not None:
            extras.append(f"FSW MAE={conversion.comparison.mae_db:.3f} dB")
        detail = " | " + ", ".join(extras) if extras else ""
        self.status_label.setText(
            f"完整转换完成 | 输出：{payload.config.output.directory}{detail}"
        )
        self._schedule_region_conversion()
        LOGGER.info(
            "full conversion worker complete output=%s points=%d",
            payload.config.output.directory,
            len(conversion.time_s),
        )

    def _on_full_conversion_failed(self, message: str) -> None:
        self._release_full_conversion_task()
        self.status_label.setText(f"完整转换失败：{message}")
        LOGGER.error("full conversion worker failed: %s", message)
        QMessageBox.critical(self, "转换失败", message)

    # ------------------------------------------------------------------
    # Non-blocking batch conversion
    # ------------------------------------------------------------------
    def _install_batch_worker_controls(self) -> None:
        layout = self.batch_tab.layout()
        if layout is None:
            return

        self.batch_progress = QProgressBar(self.batch_tab)
        self.batch_progress.setRange(0, 1)
        self.batch_progress.setValue(0)
        self.batch_progress.setFormat("尚未运行")

        self.cancel_batch_button = QPushButton("停止后续任务", self.batch_tab)
        self.cancel_batch_button.setEnabled(False)
        self.cancel_batch_button.setToolTip(
            "协作式停止：当前正在转换/保存的单个任务会先完整结束，然后不再启动下一项。"
        )
        self.cancel_batch_button.clicked.connect(self.cancel_batch_conversion)

        row = QHBoxLayout()
        row.addWidget(self.batch_progress, 1)
        row.addWidget(self.cancel_batch_button)
        layout.insertLayout(2, row)

    def run_batch_conversion(self) -> None:
        if self._batch_task is not None:
            return
        try:
            cfg = self.collect_config()
        except Exception as exc:
            LOGGER.exception("批量转换配置无效")
            QMessageBox.critical(self, "批量转换配置无效", str(exc))
            return

        task = BatchWorkerTask(cfg)
        task.signals.started.connect(self._on_batch_started)
        task.signals.progress.connect(self._on_batch_progress)
        task.signals.finished.connect(self._on_batch_finished)
        task.signals.failed.connect(self._on_batch_failed)

        self._batch_task = task
        self.run_batch_button.setEnabled(False)
        self.scan_batch_button.setEnabled(False)
        self.cancel_batch_button.setEnabled(True)
        self.batch_status_label.setText(
            "批量转换已进入后台；窗口可继续响应。可点击“停止后续任务”在当前任务完成后停止。"
        )
        self.batch_progress.setRange(0, 0)
        self.batch_progress.setFormat("正在扫描任务…")
        self._worker_pool.start(task)

    def cancel_batch_conversion(self) -> None:
        task = self._batch_task
        if task is None:
            return
        task.cancel()
        self.cancel_batch_button.setEnabled(False)
        self.batch_status_label.setText(
            "已请求停止：当前正在执行的任务会完整转换并保存；完成后不再启动下一项。"
        )
        self.batch_progress.setFormat("停止已请求：等待当前任务完成…")

    def _on_batch_started(self, total: int) -> None:
        total = max(0, int(total))
        self.batch_table.clearContents()
        self.batch_table.setRowCount(total)
        self.batch_progress.setRange(0, max(total, 1))
        self.batch_progress.setValue(0)
        self.batch_progress.setFormat(
            "没有发现任务" if total == 0 else f"0 / {total}（0%）"
        )
        self.batch_status_label.setText(f"已发现 {total} 个批量任务，正在后台执行。")

    @staticmethod
    def _batch_item_values(item: BatchItemResult) -> list[str]:
        return [
            item.name,
            item.status,
            "" if item.center_frequency_hz is None else f"{item.center_frequency_hz/1e6:.6g}",
            "" if item.rbw_hz is None else f"{item.rbw_hz/1e6:.6g}",
            "" if item.mae_db is None else f"{item.mae_db:.4f}",
            item.output_directory,
            item.error or "",
        ]

    def _on_batch_progress(
        self,
        current: int,
        total: int,
        item: BatchItemResult,
    ) -> None:
        row = max(0, int(current) - 1)
        if row >= self.batch_table.rowCount():
            self.batch_table.setRowCount(row + 1)
        for column, value in enumerate(self._batch_item_values(item)):
            self.batch_table.setItem(row, column, QTableWidgetItem(value))

        total = max(int(total), 1)
        current = min(max(int(current), 0), total)
        self.batch_progress.setRange(0, total)
        self.batch_progress.setValue(current)
        percent = int(round(100.0 * current / total))
        self.batch_progress.setFormat(f"{current} / {total}（{percent}%）")
        self.batch_status_label.setText(
            f"正在批量转换：{current}/{total} | 最近任务 {item.name}：{item.status}"
        )

    def _release_batch_task(self) -> None:
        self._batch_task = None
        self.run_batch_button.setEnabled(True)
        self.scan_batch_button.setEnabled(True)
        self.cancel_batch_button.setEnabled(False)

    def _on_batch_finished(self, result: BatchRunResult) -> None:
        self._release_batch_task()
        self.batch_table.resizeColumnsToContents()
        if result.jobs_found:
            self.batch_progress.setRange(0, result.jobs_found)
            self.batch_progress.setValue(result.jobs_processed)
        else:
            self.batch_progress.setRange(0, 1)
            self.batch_progress.setValue(0)

        if result.cancelled:
            self.batch_progress.setFormat(
                f"已停止：完成 {result.jobs_processed} / {result.jobs_found}"
            )
            self.batch_status_label.setText(
                f"批量转换已按请求停止：发现 {result.jobs_found} 个，"
                f"已处理 {result.jobs_processed} 个，成功 {result.succeeded} 个，"
                f"失败 {result.failed} 个。已完成任务的输出和汇总均已保留。"
            )
        else:
            self.batch_progress.setFormat(
                f"完成 {result.jobs_processed} / {result.jobs_found}"
            )
            self.batch_status_label.setText(
                f"批量转换完成：共 {result.jobs_found} 个，成功 {result.succeeded} 个，"
                f"失败 {result.failed} 个。汇总目录：{result.output_directory}"
            )
        LOGGER.info(
            "batch worker complete found=%d processed=%d succeeded=%d failed=%d cancelled=%s",
            result.jobs_found,
            result.jobs_processed,
            result.succeeded,
            result.failed,
            result.cancelled,
        )

    def _on_batch_failed(self, message: str) -> None:
        self._release_batch_task()
        self.batch_progress.setRange(0, 1)
        self.batch_progress.setValue(0)
        self.batch_progress.setFormat("批量转换失败")
        self.batch_status_label.setText(f"批量转换失败：{message}")
        LOGGER.error("batch worker failed: %s", message)
        QMessageBox.critical(self, "批量转换失败", message)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def _install_diagnostic_export_button(self) -> None:
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
        # An in-flight ROI conversion belongs to the previous research waveform.
        self._roi_generation += 1
        self._roi_pending_payload = None

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
