from __future__ import annotations

import math
from typing import Iterable

import numpy as np
from matplotlib.ticker import FixedLocator


def fixed_ticks(minimum: float, maximum: float, step: float) -> np.ndarray:
    """Return bounded major ticks without ever extending beyond ``maximum``."""
    if not (math.isfinite(minimum) and math.isfinite(maximum) and math.isfinite(step)):
        return np.asarray([], dtype=float)
    if maximum <= minimum or step <= 0:
        return np.asarray([], dtype=float)

    span = maximum - minimum
    count = int(math.floor(span / step + 1e-12)) + 1
    # Protect the GUI from an accidentally tiny step that would generate huge
    # tick arrays and make Matplotlib effectively unresponsive.
    count = min(count, 10_001)
    ticks = minimum + np.arange(count, dtype=float) * step
    tolerance = max(abs(maximum), abs(minimum), 1.0) * 1e-12
    return ticks[ticks <= maximum + tolerance]


def nice_step(value: float) -> float:
    """Round a requested display step to a conventional 1/2/5×10^n value."""
    if not math.isfinite(value) or value <= 0:
        return 1.0
    exponent = math.floor(math.log10(value))
    scale = 10.0**exponent
    normalized = value / scale
    if normalized <= 1.0:
        nice = 1.0
    elif normalized <= 2.0:
        nice = 2.0
    elif normalized <= 5.0:
        nice = 5.0
    else:
        nice = 10.0
    return nice * scale


def automatic_bounds(
    values: Iterable[float] | np.ndarray,
    *,
    fallback: tuple[float, float],
    relative_margin: float = 0.05,
    minimum_margin: float = 2.0,
) -> tuple[float, float]:
    """Compute stable automatic bounds for one displayed axis."""
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if len(finite) == 0:
        return float(fallback[0]), float(fallback[1])

    low = float(np.min(finite))
    high = float(np.max(finite))
    if math.isclose(low, high):
        margin = max(abs(high) * relative_margin, minimum_margin)
    else:
        margin = max((high - low) * relative_margin, minimum_margin)
    return low - margin, high + margin


def major_tick_step(ticks: Iterable[float] | np.ndarray) -> float | None:
    """Infer the dominant positive spacing from a Matplotlib major-tick list."""
    values = np.asarray(ticks, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 2:
        return None

    differences = np.diff(np.sort(np.unique(values)))
    differences = differences[np.isfinite(differences) & (differences > 0)]
    if len(differences) == 0:
        return None

    step = float(np.median(differences))
    if not math.isfinite(step) or step <= 0:
        return None
    return step


def _enable_clipping(ax) -> None:
    for line in ax.lines:
        line.set_clip_on(True)
    for patch in ax.patches:
        patch.set_clip_on(True)


def apply_fixed_y_axis(ax, minimum: float, maximum: float, step: float) -> None:
    """Hard-lock a Y display window; over-range samples are clipped, not autoscaled."""
    valid_range = math.isfinite(minimum) and math.isfinite(maximum) and maximum > minimum

    if valid_range:
        ax.set_autoscaley_on(False)
        ax.margins(y=0.0)

    ticks = fixed_ticks(minimum, maximum, step)
    if len(ticks):
        ax.yaxis.set_major_locator(FixedLocator(ticks))

    _enable_clipping(ax)

    if valid_range:
        ax.set_ylim(float(minimum), float(maximum), auto=False)
        ax.set_autoscaley_on(False)

    ax.grid(True, which="major", alpha=0.25)


def apply_fixed_xy_axis(
    ax,
    *,
    x_min: float,
    x_max: float,
    x_step: float,
    y_min: float,
    y_max: float,
    y_step: float,
) -> None:
    """Hard-lock X/Y display windows while preserving Matplotlib clipping."""
    valid_x = math.isfinite(x_min) and math.isfinite(x_max) and x_max > x_min
    valid_y = math.isfinite(y_min) and math.isfinite(y_max) and y_max > y_min

    if valid_x:
        ax.set_autoscalex_on(False)
        x_ticks = fixed_ticks(x_min, x_max, x_step)
        if len(x_ticks):
            ax.xaxis.set_major_locator(FixedLocator(x_ticks))

    if valid_y:
        ax.set_autoscaley_on(False)
        y_ticks = fixed_ticks(y_min, y_max, y_step)
        if len(y_ticks):
            ax.yaxis.set_major_locator(FixedLocator(y_ticks))

    _enable_clipping(ax)

    if valid_x:
        ax.set_xlim(float(x_min), float(x_max), auto=False)
        ax.set_autoscalex_on(False)
    if valid_y:
        ax.set_ylim(float(y_min), float(y_max), auto=False)
        ax.set_autoscaley_on(False)

    ax.grid(True, which="major", alpha=0.25)
