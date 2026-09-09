"""Formal DCM parameter-extractor GUI entry point.

The staged extraction pipeline remains compatible with the historical v7
implementation. The expensive fourth-stage global refinement is moved out of
the GUI thread here so the commercial entry point stays responsive.
"""

from __future__ import annotations

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QMessageBox, QPushButton

from ..dcm_parameter_extractor_widget_v7 import (
    DcmParameterExtractorWidget as _LegacyExtractorWidget,
)
from ..dcm_unified_fit import parameters_from_extraction
from ..logging_utils import get_logger
from ..waveform_quality import waveform_signature
from .worker import GlobalRefinementWorkerTask


LOGGER = get_logger()


class DcmParameterExtractorWidget(_LegacyExtractorWidget):
    """Stable extractor widget with non-blocking global refinement."""

    def __init__(self, parent=None) -> None:
        self._global_refinement_pool = QThreadPool.globalInstance()
        self._global_refinement_request_seq = 0
        self._global_refinement_active_request_id: int | None = None
        self._global_refinement_task: GlobalRefinementWorkerTask | None = None
        self._global_refinement_active_source_signature: str | None = None
        self._global_refinement_active_inputs: tuple[object, object, object] | None = None
        super().__init__(parent)

    def _ready_for_global_refinement(self) -> bool:
        return (
            self.time_s is not None
            and self.voltage_v is not None
            and self.result is not None
            and self.ringing_result is not None
            and self.dcm_result is not None
        )

    def _set_global_refinement_busy(self, busy: bool) -> None:
        # Prevent the common customer path from replacing the source waveform
        # halfway through a running refinement. The worker itself never touches
        # QWidget state.
        for button in self.findChildren(QPushButton):
            text = button.text()
            if text in {"加载 CSV 并自动提取", "重新分析当前 CSV"}:
                button.setEnabled(not busy)

        if hasattr(self, "global_refine_btn"):
            self.global_refine_btn.setText(
                "全局联合精修中…" if busy else "重新运行全局联合精修（较慢）"
            )
            self.global_refine_btn.setEnabled(
                (not busy) and self._ready_for_global_refinement()
            )
        if hasattr(self, "use_global_all_btn"):
            self.use_global_all_btn.setEnabled(
                (not busy) and self.global_result is not None
            )

    def run_global_refinement(self) -> None:
        if self._global_refinement_active_request_id is not None:
            return
        if not self._ready_for_global_refinement():
            QMessageBox.information(
                self,
                "尚不能联合精修",
                "请先完成基础参数、开关沿寄生振铃和 DCM 断续谐振三个阶段。",
            )
            return

        assert self.time_s is not None
        assert self.voltage_v is not None
        assert self.result is not None
        assert self.ringing_result is not None
        assert self.dcm_result is not None

        self.global_result = None
        self.global_error = None
        self._global_refinement_request_seq += 1
        request_id = self._global_refinement_request_seq
        task = GlobalRefinementWorkerTask(
            request_id=request_id,
            time_s=self.time_s,
            voltage_v=self.voltage_v,
            basic=self.result,
            ringing=self.ringing_result,
            dcm=self.dcm_result,
            max_iterations=8,
            max_optimization_points=18_000,
        )
        task.signals.finished.connect(self._on_global_refinement_finished)
        task.signals.failed.connect(self._on_global_refinement_failed)

        self._global_refinement_active_request_id = request_id
        self._global_refinement_task = task
        self._global_refinement_active_source_signature = waveform_signature(
            self.time_s,
            self.voltage_v,
        )
        self._global_refinement_active_inputs = (
            self.result,
            self.ringing_result,
            self.dcm_result,
        )
        self._set_global_refinement_busy(True)
        self.status_label.setText(
            "全局联合精修已进入后台计算：界面保持响应。"
            "优化使用前三阶段结果为初值，并在完成后自动载入生成器同源参数。"
        )
        self._global_refinement_pool.start(task)

    def _release_global_refinement_task(self) -> None:
        self._global_refinement_active_request_id = None
        self._global_refinement_task = None
        self._global_refinement_active_source_signature = None
        self._global_refinement_active_inputs = None
        self._set_global_refinement_busy(False)

    def _global_refinement_source_is_current(self) -> bool:
        if self.time_s is None or self.voltage_v is None:
            return False
        active_inputs = self._global_refinement_active_inputs
        current_inputs = (
            self.result,
            self.ringing_result,
            self.dcm_result,
        )
        if active_inputs is None or not all(
            active is current
            for active, current in zip(active_inputs, current_inputs, strict=True)
        ):
            return False
        return self._global_refinement_active_source_signature == waveform_signature(
            self.time_s,
            self.voltage_v,
        )

    def _on_global_refinement_finished(self, request_id: int, result) -> None:
        if request_id != self._global_refinement_active_request_id:
            return
        if not self._global_refinement_source_is_current():
            self._release_global_refinement_task()
            self.status_label.setText(
                "联合精修结果已丢弃：输入波形或前三阶段结果已更新。"
            )
            return

        self.global_result = result
        self.global_error = None
        self._release_global_refinement_task()

        if self.result is None:
            return
        self.current_parameters = parameters_from_extraction(
            self.result,
            self.ringing_result,
            self.dcm_result,
            self.global_result,
        )
        self._build_parameter_table()
        self._run_current_model()
        self.use_global_all_btn.setEnabled(True)
        self.status_label.setText(
            self.status_label.text()
            + " | 全局联合精修完成："
            f"RMSE {result.staged_rmse_v*1e3:.6g} → {result.optimized_rmse_v*1e3:.6g} mV，"
            f"改善 {result.rmse_improvement_percent:.6g}%，"
            "精修值已映射到生成器原生参数，可继续逐项人工校正。"
        )
        LOGGER.info(
            "DCM global refinement worker complete source=%s staged_rmse=%g optimized_rmse=%g improvement=%g%% evaluations=%d",
            self.waveform_path or "memory",
            result.staged_rmse_v,
            result.optimized_rmse_v,
            result.rmse_improvement_percent,
            result.evaluations,
        )

    def _on_global_refinement_failed(self, request_id: int, message: str) -> None:
        if request_id != self._global_refinement_active_request_id:
            return
        if not self._global_refinement_source_is_current():
            self._release_global_refinement_task()
            return

        self.global_result = None
        self.global_error = str(message)
        self._release_global_refinement_task()
        self.status_label.setText(
            "全局联合精修未完成；前三阶段结果和当前生成器同源参数仍然有效。"
        )
        self.warning_label.setText(
            self.warning_label.text() + f"\n• 全局联合精修未完成：{message}"
        )
        LOGGER.error("DCM global refinement worker failed: %s", message)
        QMessageBox.warning(
            self,
            "全局联合精修未完成",
            f"前三阶段结果仍然有效。\n\n{message}",
        )


__all__ = ["DcmParameterExtractorWidget"]
