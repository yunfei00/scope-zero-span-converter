from __future__ import annotations

from scope_zero_span_converter.dcm_analysis.zoom import ZoomState, normalized_bounds


def test_normalized_bounds_orders_drag_direction_and_rejects_tiny_span():
    assert normalized_bounds(5.0, 2.0) == (2.0, 5.0)
    assert normalized_bounds(1.0, 1.0) is None


def test_zoom_state_supports_multilevel_undo():
    state = ZoomState()
    first = ((1.0, 5.0), (-2.0, 2.0))
    second = ((2.0, 3.0), (-1.0, 1.0))

    state.push("time", first)
    state.push("time", second)
    assert state.current("time") == second

    assert state.undo() is True
    assert state.current("time") == first
    assert state.undo() is True
    assert state.current("time") is None
    assert state.undo() is False


def test_clear_removes_only_target_history():
    state = ZoomState()
    state.push("time", ((1.0, 5.0), (-2.0, 2.0)))
    state.push("frequency", ((100.0, 200.0), (-80.0, -20.0)))
    state.push("time", ((2.0, 4.0), (-1.0, 1.0)))

    state.clear("time")

    assert state.current("time") is None
    assert state.current("frequency") == ((100.0, 200.0), (-80.0, -20.0))
    assert all(target != "time" for target, _previous in state.history)
