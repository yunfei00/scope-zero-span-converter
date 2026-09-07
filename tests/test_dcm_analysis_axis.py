from __future__ import annotations

import numpy as np
from matplotlib.figure import Figure

from scope_zero_span_converter.dcm_analysis.axis import (
    apply_fixed_xy_axis,
    apply_fixed_y_axis,
    automatic_bounds,
    fixed_ticks,
    major_tick_step,
    nice_step,
)


def test_fixed_ticks_never_extend_beyond_maximum():
    ticks = fixed_ticks(-5.0, 5.0, 2.0)
    assert np.allclose(ticks, [-5.0, -3.0, -1.0, 1.0, 3.0, 5.0])
    assert float(np.max(ticks)) <= 5.0


def test_nice_step_uses_1_2_5_decades():
    assert nice_step(0.07) == 0.1
    assert nice_step(1.1) == 2.0
    assert nice_step(2.1) == 5.0
    assert nice_step(7.0) == 10.0


def test_automatic_bounds_add_margin_and_ignore_nonfinite():
    low, high = automatic_bounds(
        np.asarray([np.nan, -40.0, -20.0, np.inf]),
        fallback=(-200.0, 20.0),
        relative_margin=0.05,
        minimum_margin=2.0,
    )
    assert low == -42.0
    assert high == -18.0


def test_major_tick_step_ignores_duplicate_and_nonfinite_ticks():
    step = major_tick_step([0.0, 10.0, 10.0, 20.0, np.nan, 30.0])
    assert step == 10.0


def test_fixed_xy_axis_stays_locked_when_data_exceeds_window():
    figure = Figure()
    ax = figure.add_subplot(111)
    ax.plot([0.0, 5.0, 10.0], [-100.0, 0.0, 100.0])

    apply_fixed_xy_axis(
        ax,
        x_min=2.0,
        x_max=8.0,
        x_step=2.0,
        y_min=-5.0,
        y_max=5.0,
        y_step=2.5,
    )

    assert ax.get_xlim() == (2.0, 8.0)
    assert ax.get_ylim() == (-5.0, 5.0)
    assert ax.get_autoscalex_on() is False
    assert ax.get_autoscaley_on() is False


def test_fixed_y_axis_stays_locked_when_waveform_exceeds_window():
    figure = Figure()
    ax = figure.add_subplot(111)
    ax.plot([0.0, 1.0], [-100.0, 100.0])

    apply_fixed_y_axis(ax, -10.0, 10.0, 5.0)

    assert ax.get_ylim() == (-10.0, 10.0)
    assert ax.get_autoscaley_on() is False
