from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtWidgets import QFileDialog, QMessageBox

from ..dcm_analysis_widget import DcmAnalysisWidget as _CompatibilityDcmAnalysisWidget
from ..dcm_sw_generator import load_dcm_sw_parameters, save_dcm_sw_parameters
from ..dcm_zero_span_link import load_zero_span_profile, save_zero_span_profile
from .plots import (
    draw_magnitude_spectrum_panel,
    draw_phase_spectrum_panel,
    draw_time_domain_panel,
    draw_zero_span_panel,
)


class DcmAnalysisWidget(_CompatibilityDcmAnalysisWidget):
    """Formal DCM analysis widget owning the production four-panel layout.

    The compatibility widget still supplies the existing parameter controls,
    workspace, Marker, axis and Rectangle-Zoom behaviors during migration. The
    actual four-panel figure layout/rendering lives here and in ``plots.py`` so
    production code no longer depends on the legacy v4/v10 redraw methods.
    """

    def __init__(self, parent=None) -> None:
        # Explicit file state belongs to the formal workspace. Never recover a
        # path by parsing QLabel text.
        self.current_dcm_parameters_path: str | None = None
        self.current_zero_span_profile_path: str | None = None
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
            self.current_spectrum_frequency_hz = np.asarray([], dtype=float)
            self.current_spectrum_amplitude_dbv = np.asarray([], dtype=float)
            self.current_spectrum_phase_deg = np.asarray([], dtype=float)
            self.current_phase_visibility_threshold_dbv = self.PHASE_VISIBLE_FLOOR_DBV
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
            # These hooks are already migrated to formal spectrum.py + plots.py
            # in the compatibility entry and preserve frequency axis/Marker rules.
            self._draw_frequency_panel(ax_frequency, waveform)
            self._draw_reserved_panel(ax_phase)

        # Preserve customer-configured DCM/Zero Span Y-axis hard limits. This is
        # display-only and never regenerates DCM or reruns Zero Span conversion.
        self._apply_axis_controls_if_ready(ax_time, ax_zero)

        # Right-hand phase is the exact same frequency bins as magnitude.
        try:
            ax_phase.sharex(ax_frequency)
        except ValueError:
            pass
        ax_phase.set_xlim(ax_frequency.get_xlim(), auto=False)

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
