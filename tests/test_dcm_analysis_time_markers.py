from __future__ import annotations

import numpy as np
import pytest

from scope_zero_span_converter.dcm_analysis.time_markers import (
    time_marker_at_time,
    time_marker_delta,
)


def test_time_marker_snaps_to_nearest_real_sample():
    t = np.asarray([5e-6, 6e-6, 7e-6, 8e-6], dtype=float)
    v = np.asarray([0.0, 2.0, 5.0, 1.0], dtype=float)

    marker = time_marker_at_time(t, v, 6.6e-6)

    assert marker.index == 2
    assert marker.time_s == pytest.approx(7e-6)
    assert marker.voltage_v == pytest.approx(5.0)


def test_time_marker_delta_uses_b_minus_a_semantics():
    t = np.asarray([0.0, 1e-6, 2e-6, 3e-6], dtype=float)
    v = np.asarray([1.0, 4.0, 2.0, 8.0], dtype=float)

    marker_a = time_marker_at_time(t, v, 1e-6)
    marker_b = time_marker_at_time(t, v, 3e-6)
    delta = time_marker_delta(marker_a, marker_b)

    assert delta.delta_time_s == pytest.approx(2e-6)
    assert delta.delta_voltage_v == pytest.approx(4.0)


def test_time_marker_rejects_invalid_input():
    with pytest.raises(ValueError, match="等长"):
        time_marker_at_time(
            np.asarray([0.0, 1.0]),
            np.asarray([1.0]),
            0.0,
        )
