from __future__ import annotations

import numpy as np
from matplotlib.widgets import RectangleSelector
from PySide6.QtCore import Qt

from .plots import MAX_DISPLAY_POINTS, display_indices_for_range
from .zoom import ZoomBounds, ZoomTarget, normalized_bounds


_DISPLAY_SUFFIX = "（显示抽样；分析/导出仍用全数据）"


class ZoomInteractionMixin:
    """Production Rectangle-Zoom behavior backed by formal ``ZoomState``.

    During migration the compatibility constructor still creates ``_zoom_state``
    and installs the initial canvas callbacks. All runtime callbacks and redraw
    application are implemented here so production behavior no longer depends on
    the historical v6 method bodies.
    """

    _normalized_bounds = staticmethod(normalized_bounds)

    def _disconnect_zoom_selectors(self) -> None:
        selectors = getattr(self, "_zoom_selectors", {})
        for selector in selectors.values():
            try:
                selector.set_active(False)
                selector.disconnect_events()
            except Exception:
                pass
        selectors.clear()
        axes = getattr(self, "_zoom_axes", None)
        if axes is not None:
            axes.clear()

    def _rebind_zoom_selectors(self) -> None:
        self._disconnect_zoom_selectors()
        if self.current_waveform is None or len(self.figure.axes) < 2:
            return

        self.canvas.setFocusPolicy(Qt.StrongFocus)
        ax_time = self.figure.axes[0]
        ax_frequency = self.figure.axes[1]
        self._zoom_axes = {
            "time": ax_time,
            "frequency": ax_frequency,
        }
        self._zoom_selectors = {
            "time": RectangleSelector(
                ax_time,
                lambda eclick, erelease: self._on_zoom_rectangle(
                    "time", eclick, erelease
                ),
                useblit=False,
                button=[1],
                minspanx=0,
                minspany=0,
                spancoords="data",
                interactive=False,
            ),
            "frequency": RectangleSelector(
                ax_frequency,
                lambda eclick, erelease: self._on_zoom_rectangle(
                    "frequency", eclick, erelease
                ),
                useblit=False,
                button=[1],
                minspanx=0,
                minspany=0,
                spancoords="data",
                interactive=False,
            ),
        }

    def _on_zoom_rectangle(self, target: ZoomTarget, eclick, erelease) -> None:
        if (
            eclick is None
            or erelease is None
            or eclick.xdata is None
            or eclick.ydata is None
            or erelease.xdata is None
            or erelease.ydata is None
        ):
            return

        x_bounds = normalized_bounds(eclick.xdata, erelease.xdata)
        y_bounds = normalized_bounds(eclick.ydata, erelease.ydata)
        if x_bounds is None or y_bounds is None:
            return

        bounds: ZoomBounds = (x_bounds, y_bounds)
        self._zoom_state.push(target, bounds)
        self.canvas.setFocus()
        self._redraw(zero_span_error=self.current_zero_span_error)

    def _on_zoom_canvas_press(self, event) -> None:
        if event is None:
            return
        if event.inaxes in getattr(self, "_zoom_axes", {}).values():
            self.canvas.setFocus()

    def _on_zoom_key_press(self, event) -> None:
        if getattr(event, "key", None) not in {" ", "space"}:
            return
        self._undo_last_zoom()

    def _undo_last_zoom(self) -> None:
        if self._zoom_state.undo():
            self._redraw(zero_span_error=self.current_zero_span_error)

    def _clear_zoom_target(self, target: ZoomTarget) -> None:
        self._zoom_state.clear(target)

    @staticmethod
    def _set_sampling_suffix(ax, reduced: bool) -> None:
        title = ax.get_title().replace(_DISPLAY_SUFFIX, "")
        if reduced:
            title += _DISPLAY_SUFFIX
        ax.set_title(title)

    @staticmethod
    def _visible_count(x_values: np.ndarray, x_range: tuple[float, float]) -> int:
        low, high = sorted(map(float, x_range))
        return max(
            0,
            int(np.searchsorted(x_values, high, side="right"))
            - int(np.searchsorted(x_values, low, side="left")),
        )

    def _refresh_time_display_for_range(self, x_range_us: tuple[float, float]) -> None:
        waveform = self.current_waveform
        if waveform is None or len(self.figure.axes) < 3:
            return

        ax_time = self.figure.axes[0]
        ax_zero = self.figure.axes[2]
        time_us = np.asarray(waveform.time_s, dtype=float) * 1e6
        voltage = np.asarray(waveform.voltage_v, dtype=float)
        indices = display_indices_for_range(time_us, voltage, x_range_us)
        visible = self._visible_count(time_us, x_range_us)
        reduced = len(indices) < visible

        if len(ax_time.lines) >= 1:
            ax_time.lines[0].set_data(time_us[indices], voltage[indices])
        if len(ax_time.lines) >= 2:
            ideal = np.asarray(waveform.ideal_voltage_v, dtype=float)
            ax_time.lines[1].set_data(time_us[indices], ideal[indices])
        self._set_sampling_suffix(ax_time, reduced)

        zero = self.current_zero_span
        if zero is not None and len(ax_zero.lines) >= 1:
            zero_time_us = np.asarray(zero.time_s, dtype=float) * 1e6
            zero_dbm = np.asarray(zero.amplitude_dbm, dtype=float)
            zero_indices = display_indices_for_range(
                zero_time_us,
                zero_dbm,
                x_range_us,
            )
            zero_visible = self._visible_count(zero_time_us, x_range_us)
            ax_zero.lines[0].set_data(
                zero_time_us[zero_indices],
                zero_dbm[zero_indices],
            )
            self._set_sampling_suffix(ax_zero, len(zero_indices) < zero_visible)

    def _refresh_frequency_display_for_range(
        self,
        x_range_mhz: tuple[float, float],
    ) -> None:
        if len(self.figure.axes) < 4:
            return
        spectrum_getter = getattr(self, "_spectrum_from_current_cache", None)
        spectrum = spectrum_getter() if callable(spectrum_getter) else None
        if spectrum is None:
            return

        frequency_mhz = np.asarray(spectrum.frequency_hz, dtype=float) / 1e6
        amplitude = np.asarray(spectrum.amplitude_dbv, dtype=float)
        phase = np.asarray(spectrum.phase_deg, dtype=float)
        indices = display_indices_for_range(
            frequency_mhz,
            amplitude,
            x_range_mhz,
        )
        visible = self._visible_count(frequency_mhz, x_range_mhz)
        reduced = len(indices) < visible

        ax_magnitude = self.figure.axes[1]
        ax_phase = self.figure.axes[3]
        if len(ax_magnitude.lines) >= 1:
            ax_magnitude.lines[0].set_data(
                frequency_mhz[indices],
                amplitude[indices],
            )
        if len(ax_phase.lines) >= 1:
            ax_phase.lines[0].set_data(
                frequency_mhz[indices],
                phase[indices],
            )
        self._set_sampling_suffix(ax_magnitude, reduced)
        self._set_sampling_suffix(ax_phase, reduced)

    def _apply_zoom_ranges_if_ready(self) -> None:
        if len(self.figure.axes) < 2:
            return

        ax_time = self.figure.axes[0]
        ax_frequency = self.figure.axes[1]

        time_zoom = self._zoom_state.current("time")
        if time_zoom is not None:
            (x_min, x_max), (y_min, y_max) = time_zoom
            self._refresh_time_display_for_range((x_min, x_max))
            # ax_time and lower-left Zero Span share X.
            ax_time.set_xlim(x_min, x_max, auto=False)
            ax_time.set_ylim(y_min, y_max, auto=False)
            ax_time.set_autoscalex_on(False)
            ax_time.set_autoscaley_on(False)

        frequency_zoom = self._zoom_state.current("frequency")
        if frequency_zoom is not None:
            (x_min, x_max), (y_min, y_max) = frequency_zoom
            self._refresh_frequency_display_for_range((x_min, x_max))
            ax_frequency.set_xlim(x_min, x_max, auto=False)
            ax_frequency.set_ylim(y_min, y_max, auto=False)
            ax_frequency.set_autoscalex_on(False)
            ax_frequency.set_autoscaley_on(False)

    def _on_axis_display_changed(self, *_args) -> None:
        # DCM Y-axis edits reset only the temporary time-domain zoom. Zero Span
        # Y controls do not change the time zoom unless the sender cannot be
        # resolved (matching the historical conservative behavior).
        sender = self.sender()
        dcm_axis_controls = {
            getattr(self, "dcm_y_min", None),
            getattr(self, "dcm_y_max", None),
            getattr(self, "dcm_y_step", None),
        }
        if sender is None or sender in dcm_axis_controls:
            self._clear_zoom_target("time")

        self._redraw(zero_span_error=self.current_zero_span_error)


__all__ = ["ZoomInteractionMixin"]
