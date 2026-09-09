from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QFileDialog, QMessageBox

from ..dcm_analysis_widget import DcmAnalysisWidget as _CompatibilityDcmAnalysisWidget
from ..dcm_sw_generator import DcmSwWaveform, load_dcm_sw_parameters, save_dcm_sw_parameters
from ..dcm_zero_span_link import load_zero_span_profile, save_zero_span_profile
from ..waveform_quality import waveform_signature
from ..workspace import collect_dcm_analysis_workspace
from .exporter import export_dcm_analysis_bundle
from .frequency_axis import FrequencyAxisMixin
from .plots import (
    draw_magnitude_spectrum_panel,
    draw_phase_spectrum_panel,
    draw_time_domain_panel,
    draw_zero_span_panel,
)
from .recompute import DcmRecomputeMixin
from .snapshot import AnalysisSnapshotConsistencyError, validate_analysis_snapshot
from .spectrum import DcmSpectrum, compute_dcm_spectrum
from .worker import SpectrumWorkerOptions, SpectrumWorkerTask
from .zoom_interaction import ZoomInteractionMixin


class DcmAnalysisWidget(
    FrequencyAxisMixin,
    DcmRecomputeMixin,
    ZoomInteractionMixin,
    _CompatibilityDcmAnalysisWidget,
):
    """Formal DCM analysis widget owning the production four-panel layout.

    Small DCM/Zero Span recomputes and FFTs remain synchronous to preserve the
    established instant UI. Large DCM+Zero Span recomputes and large FFTs are
    dispatched to background tasks with latest-wins scheduling. Display-only
    redraws reuse cached spectrum data and never repeat the FFT. Frequency-axis
    and Rectangle-Zoom runtime behavior are owned by the formal package rather
    than legacy v5/v6/v8/v9 method bodies.
    """

    FFT_BACKGROUND_THRESHOLD_POINTS = 250_000

    def __init__(self, parent=None) -> None:
        # Explicit file state belongs to the formal workspace. Never recover a
        # path by parsing QLabel text.
        self.current_dcm_parameters_path: str | None = None
        self.current_zero_span_profile_path: str | None = None

        # Parent construction dynamically calls _redraw(), so all FFT worker/
        # cache fields must exist before super().__init__().
        self._spectrum_cache_waveform: DcmSwWaveform | None = None
        self._spectrum_cache: DcmSpectrum | None = None
        self._spectrum_error: str | None = None
        self._spectrum_request_seq = 0
        self._spectrum_worker_running = False
        self._spectrum_active_request_id: int | None = None
        self._spectrum_active_waveform_id: int | None = None
        self._spectrum_active_task: SpectrumWorkerTask | None = None
        self._spectrum_pending_waveform: DcmSwWaveform | None = None
        self._frequency_auto_axis_pending = True
        self._spectrum_thread_pool = QThreadPool.globalInstance()

        super().__init__(parent)

    @staticmethod
    def _dialog_start_path(current_path: str | None, fallback_name: str = "") -> str:
        if current_path:
            path = Path(current_path)
            return str(path if path.is_dir() else path.parent)
        return fallback_name

    # ------------------------------------------------------------------
    # Explicit recent-file state
    # ------------------------------------------------------------------
    def load_dcm_parameters_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "加载 DCM 参数",
            self._dialog_start_path(self.current_dcm_parameters_path),
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            parameters = load_dcm_sw_parameters(path)
            self.parameters = parameters
            self._apply_parameters_to_controls(parameters)
            self.current_dcm_parameters_path = str(Path(path))
            self.dcm_file_label.setText(f"当前：{self.current_dcm_parameters_path}")
            self._recompute()
        except Exception as exc:
            QMessageBox.critical(self, "加载 DCM 参数失败", str(exc))

    def save_dcm_parameters_dialog(self) -> None:
        initial = (
            self.current_dcm_parameters_path
            if self.current_dcm_parameters_path
            else "dcm_sw_parameters.json"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存当前 DCM 参数",
            initial,
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            saved = save_dcm_sw_parameters(self.parameters, path)
            self.current_dcm_parameters_path = str(saved)
            self.dcm_file_label.setText(f"当前：{saved}")
        except Exception as exc:
            QMessageBox.critical(self, "保存 DCM 参数失败", str(exc))

    def load_zero_span_profile_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "加载 Zero Span 转换参数",
            self._dialog_start_path(self.current_zero_span_profile_path),
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            self.profile = load_zero_span_profile(path)
            self.current_zero_span_profile_path = str(Path(path))
            self._apply_profile_to_controls(self.profile)
            self._recompute()
        except Exception as exc:
            QMessageBox.critical(self, "加载转换参数失败", str(exc))

    def save_zero_span_profile_dialog(self) -> None:
        initial = (
            self.current_zero_span_profile_path
            if self.current_zero_span_profile_path
            else "zero_span_profile.json"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存 Zero Span 转换参数",
            initial,
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            saved = save_zero_span_profile(self.profile, path)
            self.current_zero_span_profile_path = str(saved)
            self.status_label.setText(f"已保存 Zero Span 转换参数：{saved}")
        except Exception as exc:
            QMessageBox.critical(self, "保存转换参数失败", str(exc))

    # ------------------------------------------------------------------
    # Snapshot-consistent one-click export
    # ------------------------------------------------------------------
    def _analysis_update_in_progress(self) -> bool:
        timer = getattr(self, "_update_timer", None)
        return bool(
            (timer is not None and timer.isActive())
            or self._recompute_worker_running
            or self._recompute_pending is not None
            or self._spectrum_worker_running
            or self._spectrum_pending_waveform is not None
        )

    def validate_current_analysis_snapshot(self):
        return validate_analysis_snapshot(
            parameters=self.parameters,
            profile=self.profile,
            waveform=self.current_waveform,
            zero_span=self.current_zero_span,
            spectrum=self._spectrum_from_current_cache(),
            analysis_updating=self._analysis_update_in_progress(),
        )

    def _show_snapshot_export_error(
        self,
        error: AnalysisSnapshotConsistencyError,
    ) -> None:
        QMessageBox.information(self, "当前分析不能导出", str(error))

    def export_analysis_bundle_dialog(self) -> None:
        try:
            self.validate_current_analysis_snapshot()
        except AnalysisSnapshotConsistencyError as exc:
            self._show_snapshot_export_error(exc)
            return

        directory = QFileDialog.getExistingDirectory(self, "选择综合分析导出目录")
        if not directory:
            return

        try:
            # A worker or debounce timer may finish/start while the native file
            # dialog is open.  Revalidate immediately before creating files.
            snapshot = self.validate_current_analysis_snapshot()
            workspace = collect_dcm_analysis_workspace(self)
            workspace["zero_span_valid"] = True
            workspace["zero_span_error"] = None
            outputs = export_dcm_analysis_bundle(
                directory,
                parameters=snapshot.parameters,
                profile=snapshot.profile,
                waveform=snapshot.waveform,
                zero_span=snapshot.zero_span,
                spectrum=snapshot.spectrum,
                figure=self.figure,
                metadata=workspace,
            )
            self.status_label.setText(
                f"已导出综合分析：{directory} | 共 {len(outputs)} 个文件"
            )
        except AnalysisSnapshotConsistencyError as exc:
            self._show_snapshot_export_error(exc)
        except Exception as exc:
            QMessageBox.critical(self, "导出综合分析失败", str(exc))

    # ------------------------------------------------------------------
    # Spectrum cache / background worker
    # ------------------------------------------------------------------
    def _set_spectrum_cache(
        self,
        waveform: DcmSwWaveform,
        spectrum: DcmSpectrum,
    ) -> None:
        self._spectrum_cache_waveform = waveform
        self._spectrum_cache = spectrum
        self._spectrum_error = None
        self._frequency_auto_axis_pending = True
        self.current_spectrum_frequency_hz = spectrum.frequency_hz
        self.current_spectrum_amplitude_dbv = spectrum.amplitude_dbv
        self.current_spectrum_phase_deg = spectrum.phase_deg
        self.current_phase_visibility_threshold_dbv = spectrum.phase_visibility_threshold_dbv

    def _clear_current_spectrum(self) -> None:
        self.current_spectrum_frequency_hz = np.asarray([], dtype=float)
        self.current_spectrum_amplitude_dbv = np.asarray([], dtype=float)
        self.current_spectrum_phase_deg = np.asarray([], dtype=float)
        self.current_phase_visibility_threshold_dbv = self.PHASE_VISIBLE_FLOOR_DBV

    def _spectrum_from_current_cache(self) -> DcmSpectrum | None:
        waveform = self.current_waveform
        if waveform is not None and waveform is self._spectrum_cache_waveform:
            return self._spectrum_cache
        return None

    def _spectrum_worker_options(self) -> SpectrumWorkerOptions:
        return SpectrumWorkerOptions(
            amplitude_floor_dbv=self.SPECTRUM_FLOOR_DBV,
            phase_visible_floor_dbv=self.PHASE_VISIBLE_FLOOR_DBV,
            phase_dynamic_range_db=self.PHASE_DYNAMIC_RANGE_DB,
        )

    def _compute_spectrum_sync(self, waveform: DcmSwWaveform) -> DcmSpectrum:
        spectrum = compute_dcm_spectrum(
            waveform.time_s,
            waveform.voltage_v,
            amplitude_floor_dbv=self.SPECTRUM_FLOOR_DBV,
            phase_visible_floor_dbv=self.PHASE_VISIBLE_FLOOR_DBV,
            phase_dynamic_range_db=self.PHASE_DYNAMIC_RANGE_DB,
        )
        self._set_spectrum_cache(waveform, spectrum)
        return spectrum

    def _start_spectrum_worker(self, waveform: DcmSwWaveform) -> None:
        if self._spectrum_worker_running:
            if id(waveform) != self._spectrum_active_waveform_id:
                # Latest-wins queue: do not pile up multiple expensive FFT jobs.
                self._spectrum_pending_waveform = waveform
            return

        self._spectrum_request_seq += 1
        request_id = self._spectrum_request_seq
        waveform_id = id(waveform)
        task = SpectrumWorkerTask(
            request_id=request_id,
            waveform_id=waveform_id,
            time_s=waveform.time_s,
            voltage_v=waveform.voltage_v,
            options=self._spectrum_worker_options(),
        )
        task.signals.finished.connect(self._on_spectrum_worker_finished)
        task.signals.failed.connect(self._on_spectrum_worker_failed)

        self._spectrum_worker_running = True
        self._spectrum_active_request_id = request_id
        self._spectrum_active_waveform_id = waveform_id
        self._spectrum_active_task = task
        self._spectrum_pending_waveform = None
        self._spectrum_thread_pool.start(task)

    def _release_spectrum_worker_and_start_pending(self) -> bool:
        self._spectrum_worker_running = False
        self._spectrum_active_request_id = None
        self._spectrum_active_waveform_id = None
        self._spectrum_active_task = None

        pending = self._spectrum_pending_waveform
        self._spectrum_pending_waveform = None
        if pending is not None and pending is self.current_waveform:
            self._start_spectrum_worker(pending)
            return True
        return False

    def _on_spectrum_worker_finished(
        self,
        request_id: int,
        waveform_id: int,
        spectrum: DcmSpectrum,
    ) -> None:
        is_active = (
            request_id == self._spectrum_active_request_id
            and waveform_id == self._spectrum_active_waveform_id
        )
        if not is_active:
            return
        current = self.current_waveform
        timer = getattr(self, "_update_timer", None)
        input_update_pending = timer is not None and timer.isActive()
        result_is_current = (
            current is not None
            and id(current) == waveform_id
            and current.parameters == self.parameters
            and not input_update_pending
            and spectrum.source_waveform_signature
            == waveform_signature(current.time_s, current.voltage_v)
        )

        if result_is_current:
            self._set_spectrum_cache(current, spectrum)

        started_pending = self._release_spectrum_worker_and_start_pending()
        if result_is_current and not started_pending:
            # Signal arrives on the GUI thread. Repaint from the finished cache;
            # this redraw does not perform another FFT.
            self._redraw(zero_span_error=self.current_zero_span_error)

    def _on_spectrum_worker_failed(
        self,
        request_id: int,
        waveform_id: int,
        message: str,
    ) -> None:
        is_active = (
            request_id == self._spectrum_active_request_id
            and waveform_id == self._spectrum_active_waveform_id
        )
        if not is_active:
            return
        current = self.current_waveform
        timer = getattr(self, "_update_timer", None)
        input_update_pending = timer is not None and timer.isActive()
        result_is_current = (
            current is not None
            and id(current) == waveform_id
            and current.parameters == self.parameters
            and not input_update_pending
        )

        if result_is_current:
            self._spectrum_cache_waveform = None
            self._spectrum_cache = None
            self._spectrum_error = str(message)
            self._clear_current_spectrum()

        started_pending = self._release_spectrum_worker_and_start_pending()
        if result_is_current and not started_pending:
            self._redraw(zero_span_error=self.current_zero_span_error)

    def _get_or_schedule_spectrum(self, waveform: DcmSwWaveform) -> DcmSpectrum | None:
        if waveform is self._spectrum_cache_waveform and self._spectrum_cache is not None:
            return self._spectrum_cache

        if waveform.points < self.FFT_BACKGROUND_THRESHOLD_POINTS:
            return self._compute_spectrum_sync(waveform)

        self._spectrum_error = None
        self._clear_current_spectrum()
        self._start_spectrum_worker(waveform)
        return None

    def _draw_frequency_panel(self, ax, waveform: DcmSwWaveform) -> None:
        spectrum = self._get_or_schedule_spectrum(waveform)
        draw_magnitude_spectrum_panel(
            ax,
            spectrum,
            center_frequency_hz=self.profile.center_frequency_hz,
            rbw_hz=self.profile.rbw_hz,
        )

        if spectrum is None:
            message = "大波形 FFT 后台计算中…"
            if self._spectrum_error:
                message = f"DCM FFT 不可计算：{self._spectrum_error}"
            ax.set_title(message)
            self._refresh_peak_table()
            self._update_marker_info()
            return

        # Preserve the established v5/v8/v9 behavior: manual coordinate input
        # affects the current frame only; a normal FFT/data refresh returns to
        # automatic bounds and writes the resulting values back to the controls.
        if hasattr(self, "freq_x_min"):
            self._apply_fixed_axis(
                ax,
                x_min=self.freq_x_min.value(),
                x_max=self.freq_x_max.value(),
                x_step=self.freq_x_step.value(),
                y_min=self.freq_y_min.value(),
                y_max=self.freq_y_max.value(),
                y_step=self.freq_y_step.value(),
            )
        if (
            not getattr(self, "_frequency_manual_redraw_once", False)
            and self._frequency_auto_axis_pending
        ):
            self._apply_frequency_auto_axis(ax)
            self._frequency_auto_axis_pending = False

        self._refresh_peak_table()
        self._update_marker_info()
        self._draw_frequency_marker_line(
            ax,
            self._current_frequency_marker(),
            phase=False,
        )

    def _draw_reserved_panel(self, ax) -> None:
        spectrum = self._spectrum_from_current_cache()
        draw_phase_spectrum_panel(
            ax,
            spectrum,
            center_frequency_hz=self.profile.center_frequency_hz,
            rbw_hz=self.profile.rbw_hz,
        )
        if spectrum is None and self.current_waveform is not None:
            if self._spectrum_error:
                ax.set_title(f"DCM 相位频谱不可计算：{self._spectrum_error}")
            elif self.current_waveform.points >= self.FFT_BACKGROUND_THRESHOLD_POINTS:
                ax.set_title("DCM 相位频谱（等待后台 FFT）")
        self._draw_frequency_marker_line(
            ax,
            self._current_frequency_marker(),
            phase=True,
        )

    # ------------------------------------------------------------------
    # Formal four-panel rendering
    # ------------------------------------------------------------------
    def _redraw(
        self,
        *,
        zero_span_error: str | None = None,
        dcm_error: str | None = None,
    ) -> None:
        self.figure.clear()

        # Keep the established physical layout and axis coupling:
        # left column shares absolute time; right column shares FFT frequency.
        ax_time = self.figure.add_subplot(221)
        ax_frequency = self.figure.add_subplot(222)
        ax_zero = self.figure.add_subplot(223, sharex=ax_time)
        ax_phase = self.figure.add_subplot(224)

        waveform = self.current_waveform
        zero_span = self.current_zero_span

        draw_time_domain_panel(ax_time, waveform, error=dcm_error)
        draw_zero_span_panel(
            ax_zero,
            waveform,
            zero_span,
            error=zero_span_error,
        )

        if waveform is None:
            self._clear_current_spectrum()
            draw_magnitude_spectrum_panel(
                ax_frequency,
                None,
                center_frequency_hz=self.profile.center_frequency_hz,
                rbw_hz=self.profile.rbw_hz,
            )
            draw_phase_spectrum_panel(
                ax_phase,
                None,
                center_frequency_hz=self.profile.center_frequency_hz,
                rbw_hz=self.profile.rbw_hz,
            )
        else:
            self._draw_frequency_panel(ax_frequency, waveform)
            self._draw_reserved_panel(ax_phase)

        # Preserve customer-configured DCM/Zero Span Y-axis hard limits. This is
        # display-only and never regenerates DCM or reruns Zero Span conversion.
        self._apply_axis_controls_if_ready(ax_time, ax_zero)

        # Right-hand phase is the exact same frequency bins as magnitude.  Keep
        # the final magnitude bounds: attaching an already-drawn phase axis can
        # otherwise autoscale the shared group from Center/RBW helper artists.
        frequency_xlim = ax_frequency.get_xlim()
        try:
            ax_phase.sharex(ax_frequency)
        except ValueError:
            pass
        ax_frequency.set_xlim(frequency_xlim, auto=False)

        self.figure.tight_layout()

        # Temporary Rectangle Zoom is applied only after base plot/axis policy.
        # Because the axes share X, time zoom also moves Zero Span and frequency
        # zoom also moves wrapped phase.
        self._apply_zoom_ranges_if_ready()

        # Commercial information/Marker overlays are last so they never expand
        # a fixed or zoomed customer view.
        self._update_zero_span_info_card()
        self._sync_time_marker_controls_to_waveform()
        self._update_time_marker_info()
        self._draw_time_marker_overlays()

        self.canvas.draw_idle()
        self._rebind_zoom_selectors()


__all__ = ["DcmAnalysisWidget"]
