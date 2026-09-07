from __future__ import annotations

import numpy as np

from ..dcm_analysis_widget import DcmAnalysisWidget as _CompatibilityDcmAnalysisWidget
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
