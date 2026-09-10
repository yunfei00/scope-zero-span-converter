from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace

import numpy as np
from PySide6.QtCore import QThreadPool

from ..dcm_sw_generator import DcmSwParameters, DcmSwWaveform
from ..dcm_zero_span_link import DcmZeroSpanResult, ZeroSpanProfile
from ..logging_utils import get_logger
from ..waveform_quality import waveform_signature
from .recompute_worker import DcmRecomputeWorkerResult, DcmRecomputeWorkerTask


LOGGER = get_logger()


@dataclass(frozen=True)
class _PendingRecompute:
    request_id: int
    request_generation: int
    parameters: DcmSwParameters
    profile: ZeroSpanProfile


class DcmRecomputeMixin:
    """Latest-wins background scheduling for large DCM + Zero Span recomputes.

    ``DcmAnalysisControls`` remains the source of the validated synchronous
    recompute behavior. Small waveforms use that path unchanged. Large jobs are
    moved to a worker so slider interaction does not block the Qt GUI thread.

    A worker result is accepted only when all three conditions still hold:
    - it is the active request;
    - no newer recompute request exists;
    - the current DCM parameters and Zero Span profile still equal the snapshots
      used by the worker.

    The last condition closes the debounce window where a control has already
    changed ``self.parameters`` but the 120 ms recompute timer has not fired yet.
    """

    RECOMPUTE_BACKGROUND_THRESHOLD_POINTS = 250_000

    def __init__(self, *args, **kwargs) -> None:
        # These fields must exist before the control constructor runs because it
        # dynamically calls self._recompute().
        self._recompute_request_seq = 0
        self._recompute_latest_request_id = 0
        self._recompute_worker_running = False
        self._recompute_active_request_id: int | None = None
        self._recompute_active_generation: int | None = None
        self._recompute_active_parameters: DcmSwParameters | None = None
        self._recompute_active_profile: ZeroSpanProfile | None = None
        self._recompute_active_task: DcmRecomputeWorkerTask | None = None
        self._recompute_pending: _PendingRecompute | None = None
        self._recompute_thread_pool = QThreadPool.globalInstance()

        # One monotonically increasing version spans UI inputs, DCM/Zero Span,
        # FFT, and export. Result-specific generations remain None until that
        # layer has completed for the current inputs.
        self.analysis_generation = 0
        self._analysis_generation_inputs: tuple[
            DcmSwParameters,
            ZeroSpanProfile,
        ] | None = None
        self._waveform_generation: int | None = None
        self._zero_span_generation: int | None = None
        self._completed_analysis_generation: int | None = None
        self._committed_waveform_id: int | None = None
        self._committed_waveform_signature: str | None = None
        super().__init__(*args, **kwargs)

    def _mark_analysis_inputs_changed(self) -> int:
        """Advance generation once for each distinct physical input snapshot."""

        inputs = (deepcopy(self.parameters), deepcopy(self.profile))
        if self._analysis_generation_inputs == inputs:
            return self.analysis_generation

        self.analysis_generation += 1
        self._analysis_generation_inputs = inputs
        self._waveform_generation = None
        self._zero_span_generation = None
        if hasattr(self, "_spectrum_generation"):
            self._spectrum_generation = None
        self._completed_analysis_generation = None
        return self.analysis_generation

    def _ensure_analysis_generation(self) -> int:
        """Catch direct input or waveform replacement outside control signals."""

        self._mark_analysis_inputs_changed()
        waveform = getattr(self, "current_waveform", None)
        waveform_id = id(waveform) if waveform is not None else None
        if waveform_id == self._committed_waveform_id:
            return self.analysis_generation

        current_signature = (
            waveform_signature(waveform.time_s, waveform.voltage_v)
            if waveform is not None
            else None
        )
        if current_signature != self._committed_waveform_signature:
            self.analysis_generation += 1
            self._analysis_generation_inputs = (
                deepcopy(self.parameters),
                deepcopy(self.profile),
            )
            self._waveform_generation = None
            self._zero_span_generation = None
            if hasattr(self, "_spectrum_generation"):
                self._spectrum_generation = None
            self._completed_analysis_generation = None

        # Identical data in a replacement object is the same physical source;
        # remember its identity without manufacturing an unnecessary generation.
        self._committed_waveform_id = waveform_id
        self._committed_waveform_signature = current_signature
        return self.analysis_generation

    def _set_linked_analysis_results(
        self,
        waveform: DcmSwWaveform | None,
        zero_span: DcmZeroSpanResult | None,
        *,
        generation: int | None = None,
    ) -> None:
        result_generation = (
            self.analysis_generation if generation is None else int(generation)
        )
        if zero_span is not None:
            zero_span = replace(
                zero_span,
                analysis_generation=result_generation,
            )

        super()._set_linked_analysis_results(
            waveform,
            zero_span,
            generation=result_generation,
        )
        self._waveform_generation = (
            result_generation if waveform is not None else None
        )
        self._zero_span_generation = (
            result_generation if zero_span is not None else None
        )
        if hasattr(self, "_spectrum_generation"):
            self._spectrum_generation = None
        self._completed_analysis_generation = None
        self._committed_waveform_id = id(waveform) if waveform is not None else None
        self._committed_waveform_signature = (
            zero_span.source_waveform_signature
            if zero_span is not None
            else (
                waveform_signature(waveform.time_s, waveform.voltage_v)
                if waveform is not None
                else None
            )
        )

    def _mark_analysis_completed_if_current(self) -> bool:
        """Publish completion only when every result layer is from one generation."""

        generation = self.analysis_generation
        spectrum = getattr(self, "_spectrum_cache", None)
        spectrum_waveform = getattr(self, "_spectrum_cache_waveform", None)
        complete = bool(
            self.current_waveform is not None
            and self.current_zero_span is not None
            and spectrum is not None
            and spectrum_waveform is self.current_waveform
            and self._waveform_generation == generation
            and self._zero_span_generation == generation
            and getattr(spectrum, "analysis_generation", None) == generation
        )
        self._completed_analysis_generation = generation if complete else None
        return complete

    @staticmethod
    def _estimated_recompute_points(parameters: DcmSwParameters) -> int:
        """Mirror the generator point-count rule without allocating the waveform."""

        try:
            duration = float(parameters.total_duration_s)
            sample_rate = float(parameters.sample_rate_hz)
            product = duration * sample_rate
        except (TypeError, ValueError, OverflowError):
            return 0
        if not np.isfinite(product) or product <= 0:
            return 0
        return int(np.floor(product)) + 1

    def _recompute(self) -> None:
        if getattr(self, "_shutting_down", False):
            self._recompute_pending = None
            return
        timer = getattr(self, "_update_timer", None)
        if timer is not None and timer.isActive():
            # A direct recompute (file load/workspace restore/test hook) consumes
            # the same pending debounce request; do not run it a second time.
            timer.stop()

        request_generation = self._ensure_analysis_generation()
        self._recompute_request_seq += 1
        request_id = self._recompute_request_seq
        self._recompute_latest_request_id = request_id

        parameters = deepcopy(self.parameters)
        profile = deepcopy(self.profile)
        estimated_points = self._estimated_recompute_points(parameters)

        # Keep the established immediate path for normal customer workloads and
        # all invalid/degenerate combinations. The control implementation
        # owns the exact error/status semantics for that path.
        if (
            estimated_points <= 0
            or estimated_points < self.RECOMPUTE_BACKGROUND_THRESHOLD_POINTS
        ):
            self._recompute_pending = None
            super()._recompute()
            return

        pending = _PendingRecompute(
            request_id=request_id,
            request_generation=request_generation,
            parameters=parameters,
            profile=profile,
        )
        if self._recompute_worker_running:
            # Never queue every slider event. One active + one newest pending job
            # is the maximum amount of expensive work allowed.
            self._recompute_pending = pending
            if hasattr(self, "status_label"):
                self.status_label.setText(
                    f"大波形参数已更新（预计 {estimated_points:,} 点）；"
                    "当前后台任务结束后只计算最新参数。"
                )
            return

        self._start_recompute_worker(pending)

    def _start_recompute_worker(self, pending: _PendingRecompute) -> None:
        if getattr(self, "_shutting_down", False):
            self._recompute_pending = None
            return
        task = DcmRecomputeWorkerTask(
            request_id=pending.request_id,
            request_generation=pending.request_generation,
            parameters=pending.parameters,
            profile=pending.profile,
        )
        task.signals.finished.connect(self._on_recompute_worker_finished)

        self._recompute_worker_running = True
        self._recompute_active_request_id = pending.request_id
        self._recompute_active_generation = pending.request_generation
        self._recompute_active_parameters = pending.parameters
        self._recompute_active_profile = pending.profile
        self._recompute_active_task = task

        points = self._estimated_recompute_points(pending.parameters)
        if hasattr(self, "status_label"):
            self.status_label.setText(
                f"大波形后台联动计算中：预计 {points:,} 点 | "
                "DCM 生成 → Zero Span DDC/RBW/VBW。窗口可继续操作。"
            )
        self._recompute_thread_pool.start(task)

    def _release_recompute_worker(self) -> None:
        self._recompute_worker_running = False
        self._recompute_active_request_id = None
        self._recompute_active_generation = None
        self._recompute_active_parameters = None
        self._recompute_active_profile = None
        self._recompute_active_task = None

    def _on_recompute_worker_finished(self, result: DcmRecomputeWorkerResult) -> None:
        is_active = result.request_id == self._recompute_active_request_id
        if not is_active:
            # A delayed signal from a superseded task must not release or mutate
            # the worker that currently owns the scheduling slot.
            return
        if getattr(self, "_shutting_down", False):
            self._release_recompute_worker()
            self._recompute_pending = None
            LOGGER.info("DCM recompute worker completed during shutdown")
            return
        self._ensure_analysis_generation()
        snapshots_still_current = (
            result.request_generation == self.analysis_generation
            and result.request_generation == self._recompute_active_generation
            and self._recompute_active_parameters == self.parameters
            and self._recompute_active_profile == self.profile
        )
        is_latest = result.request_id == self._recompute_latest_request_id

        self._release_recompute_worker()

        pending = self._recompute_pending
        self._recompute_pending = None
        if (
            pending is not None
            and pending.request_id == self._recompute_latest_request_id
            and pending.request_generation == self.analysis_generation
        ):
            # An older completed result is intentionally not painted. Go directly
            # from the previous visible data to the newest requested parameters.
            self._start_recompute_worker(pending)
            return

        if not (is_latest and snapshots_still_current):
            # A control can change before the debounce timer issues its next
            # request. Never let the old worker overwrite those newer controls.
            return

        self._apply_recompute_worker_result(result)

    def _invalidate_spectrum_for_new_waveform(self) -> None:
        # The formal analysis widget owns these fields. Guard with hasattr so the
        # mixin remains compatible during parent construction and unit isolation.
        if hasattr(self, "_spectrum_cache_waveform"):
            self._spectrum_cache_waveform = None
        if hasattr(self, "_spectrum_cache"):
            self._spectrum_cache = None
        if hasattr(self, "_spectrum_error"):
            self._spectrum_error = None
        clear = getattr(self, "_clear_current_spectrum", None)
        if callable(clear):
            clear()

    def _apply_recompute_worker_result(self, result: DcmRecomputeWorkerResult) -> None:
        self._invalidate_spectrum_for_new_waveform()

        if result.dcm_error is not None or result.waveform is None:
            self._set_linked_analysis_results(
                None,
                None,
                generation=result.request_generation,
            )
            self.current_zero_span_error = None
            self._redraw(dcm_error=result.dcm_error or "DCM 波形生成失败")
            self.status_label.setText(
                f"当前 DCM 参数组合无效：{result.dcm_error or 'DCM 波形生成失败'}"
            )
            LOGGER.debug("DCM 后台实时生成参数无效: %s", result.dcm_error)
            return

        if result.zero_span_error is not None or result.zero_span is None:
            self._set_linked_analysis_results(
                result.waveform,
                None,
                generation=result.request_generation,
            )
            self.current_zero_span_error = (
                result.zero_span_error or "Zero Span 转换失败"
            )
            self._redraw(zero_span_error=self.current_zero_span_error)
            self.status_label.setText(
                "DCM 波形已按当前参数后台更新；Zero Span 当前不可计算："
                f"{self.current_zero_span_error}。"
                "可继续调整全部 DCM 参数；修正 Center / RBW / 采样率 / 模拟带宽后，"
                "Zero Span 会自动恢复。"
            )
            LOGGER.debug(
                "Zero Span 后台转换参数无效，但 DCM 继续联动: %s",
                self.current_zero_span_error,
            )
            return

        zero = result.zero_span
        waveform = result.waveform
        self._set_linked_analysis_results(
            waveform,
            zero,
            generation=result.request_generation,
        )
        self.current_zero_span_error = None
        self._redraw()
        self.status_label.setText(
            "后台实时联动完成："
            f"DCM {waveform.points} 点 | "
            f"时间 {waveform.time_s[0]*1e6:.6g}~{waveform.time_s[-1]*1e6:.6g} µs | "
            f"Center={zero.center_frequency_hz/1e6:.6g} MHz | "
            f"RBW={zero.rbw_hz/1e6:.6g} MHz | "
            f"VBW={'OFF' if zero.vbw_hz is None else f'{zero.vbw_hz/1e6:.6g} MHz'}"
        )


__all__ = ["DcmRecomputeMixin"]
