from __future__ import annotations

import math

import numpy as np
from matplotlib.ticker import MaxNLocator

from .axis import apply_fixed_xy_axis, automatic_bounds, major_tick_step, nice_step


class FrequencyAxisMixin:
    """Production frequency-axis behavior independent of legacy v5/v8/v9 logic."""

    def __init__(self, *args, **kwargs) -> None:
        # Legacy constructors can dynamically redraw before their own v8 flag is
        # initialized, so the formal entry establishes it first.
        self._frequency_manual_redraw_once = False
        super().__init__(*args, **kwargs)

    def _apply_fixed_axis(
        self,
        ax,
        *,
        x_min: float,
        x_max: float,
        x_step: float,
        y_min: float,
        y_max: float,
        y_step: float,
    ) -> None:
        apply_fixed_xy_axis(
            ax,
            x_min=x_min,
            x_max=x_max,
            x_step=x_step,
            y_min=y_min,
            y_max=y_max,
            y_step=y_step,
        )

    def _apply_frequency_auto_axis(self, ax) -> None:
        frequency_hz = np.asarray(self.current_spectrum_frequency_hz, dtype=float)
        amplitude_dbv = np.asarray(self.current_spectrum_amplitude_dbv, dtype=float)
        if len(frequency_hz) == 0:
            return

        frequency_mhz = frequency_hz / 1e6
        finite_x = frequency_mhz[np.isfinite(frequency_mhz)]
        if len(finite_x) == 0:
            return

        x_min = float(np.min(finite_x))
        x_max = float(np.max(finite_x))
        if x_max <= x_min:
            x_max = x_min + 1.0
        y_min, y_max = automatic_bounds(
            amplitude_dbv,
            fallback=(-200.0, 20.0),
            relative_margin=0.05,
            minimum_margin=2.0,
        )

        ax.xaxis.set_major_locator(MaxNLocator(nbins=10))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=10))
        ax.set_autoscalex_on(True)
        ax.set_autoscaley_on(True)
        ax.set_xlim(x_min, x_max, auto=True)
        ax.set_ylim(y_min, y_max, auto=True)
        ax.grid(True, which="major", alpha=0.25)

        self._sync_frequency_axis_controls_from_plot(ax)

    def _sync_frequency_axis_controls_from_plot(self, ax) -> None:
        required = (
            "freq_x_min",
            "freq_x_max",
            "freq_x_step",
            "freq_y_min",
            "freq_y_max",
            "freq_y_step",
        )
        if not all(hasattr(self, name) for name in required):
            return

        x_min, x_max = map(float, ax.get_xlim())
        y_min, y_max = map(float, ax.get_ylim())
        if not all(math.isfinite(value) for value in (x_min, x_max, y_min, y_max)):
            return
        if x_max <= x_min or y_max <= y_min:
            return

        x_step = major_tick_step(ax.get_xticks())
        y_step = major_tick_step(ax.get_yticks())
        if x_step is None:
            x_step = nice_step((x_max - x_min) / 10.0)
        if y_step is None:
            y_step = nice_step((y_max - y_min) / 10.0)

        controls_and_values = (
            (self.freq_x_min, x_min),
            (self.freq_x_max, x_max),
            (self.freq_x_step, x_step),
            (self.freq_y_min, y_min),
            (self.freq_y_max, y_max),
            (self.freq_y_step, y_step),
        )
        for control, _value in controls_and_values:
            control.blockSignals(True)
        try:
            for control, value in controls_and_values:
                control.setValue(float(value))
        finally:
            for control, _value in controls_and_values:
                control.blockSignals(False)

    def _on_frequency_axis_changed(self, *_args) -> None:
        # Frequency-axis fields are display-only. They must never regenerate the
        # DCM source or rerun Zero Span/FFT. A base-axis edit intentionally drops
        # only the temporary frequency Rectangle Zoom.
        clear_zoom = getattr(self, "_clear_zoom_target", None)
        if callable(clear_zoom):
            clear_zoom("frequency")

        self._frequency_manual_redraw_once = True
        try:
            self._redraw(zero_span_error=self.current_zero_span_error)
        finally:
            self._frequency_manual_redraw_once = False


__all__ = ["FrequencyAxisMixin"]
