from __future__ import annotations

from matplotlib.widgets import RectangleSelector
from PySide6.QtCore import Qt

from .zoom import ZoomBounds, ZoomTarget, normalized_bounds


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

    def _apply_zoom_ranges_if_ready(self) -> None:
        if len(self.figure.axes) < 2:
            return

        ax_time = self.figure.axes[0]
        ax_frequency = self.figure.axes[1]

        time_zoom = self._zoom_state.current("time")
        if time_zoom is not None:
            (x_min, x_max), (y_min, y_max) = time_zoom
            # Left DCM and Zero Span axes share X, so this propagates the exact
            # selected absolute-time range to the lower-left plot.
            ax_time.set_xlim(x_min, x_max, auto=False)
            ax_time.set_ylim(y_min, y_max, auto=False)
            ax_time.set_autoscalex_on(False)
            ax_time.set_autoscaley_on(False)

        frequency_zoom = self._zoom_state.current("frequency")
        if frequency_zoom is not None:
            (x_min, x_max), (y_min, y_max) = frequency_zoom
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

        # Y-axis controls are display-only. Repaint directly instead of calling
        # through the historical v6->v2 callback chain.
        self._redraw(zero_span_error=self.current_zero_span_error)


__all__ = ["ZoomInteractionMixin"]
