from __future__ import annotations

import os
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_analysis.recompute_worker import DcmRecomputeWorkerTask
from scope_zero_span_converter.dcm_analysis.widget import DcmAnalysisWidget
from scope_zero_span_converter.dcm_sw_generator import DcmSwParameters
from scope_zero_span_converter.dcm_zero_span_link import ZeroSpanProfile


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _ManualPool:
    def __init__(self) -> None:
        self.tasks = []

    def start(self, task) -> None:
        self.tasks.append(task)


def test_recompute_worker_returns_dcm_and_zero_span(qapp):
    del qapp
    captured = []
    task = DcmRecomputeWorkerTask(
        request_id=7,
        parameters=DcmSwParameters(sample_rate_hz=200e6, total_duration_s=4e-6),
        profile=ZeroSpanProfile(
            center_frequency_hz=40e6,
            rbw_hz=5e6,
            vbw_hz=5e6,
            scope_analog_bandwidth_hz=100e6,
        ),
    )
    task.signals.finished.connect(captured.append)
    task.run()

    assert len(captured) == 1
    result = captured[0]
    assert result.request_id == 7
    assert result.dcm_error is None
    assert result.zero_span_error is None
    assert result.waveform is not None
    assert result.zero_span is not None
    assert len(result.zero_span.time_s) == result.waveform.points


def test_large_recompute_keeps_only_latest_pending_result(qapp):
    del qapp
    widget = DcmAnalysisWidget()
    original_waveform = widget.current_waveform
    assert original_waveform is not None

    pool = _ManualPool()
    widget._recompute_thread_pool = pool
    widget.RECOMPUTE_BACKGROUND_THRESHOLD_POINTS = 1

    widget.parameters = replace(widget.parameters, on_high_voltage_v=15.0)
    widget._recompute()
    assert len(pool.tasks) == 1
    assert widget._recompute_worker_running is True

    widget.parameters = replace(widget.parameters, on_high_voltage_v=17.0)
    widget._recompute()
    assert len(pool.tasks) == 1
    assert widget._recompute_pending is not None
    assert widget._recompute_pending.parameters.on_high_voltage_v == pytest.approx(17.0)

    # Completing the stale 15 V job must not paint it. It should only launch
    # the newest pending 17 V request.
    pool.tasks[0].run()
    assert len(pool.tasks) == 2
    assert widget.current_waveform is original_waveform
    assert pool.tasks[1].parameters.on_high_voltage_v == pytest.approx(17.0)

    pool.tasks[1].run()
    assert widget._recompute_worker_running is False
    assert widget.current_waveform is not None
    assert widget.current_waveform.parameters.on_high_voltage_v == pytest.approx(17.0)
    assert widget.current_zero_span is not None


def test_worker_cannot_overwrite_parameter_changed_inside_debounce_window(qapp):
    del qapp
    widget = DcmAnalysisWidget()
    original_waveform = widget.current_waveform
    assert original_waveform is not None

    pool = _ManualPool()
    widget._recompute_thread_pool = pool
    widget.RECOMPUTE_BACKGROUND_THRESHOLD_POINTS = 1

    widget.parameters = replace(widget.parameters, on_high_voltage_v=14.0)
    widget._recompute()
    assert len(pool.tasks) == 1

    # Model the real GUI debounce window: _on_parameter_changed() has already
    # replaced self.parameters, but the 120 ms timer has not called _recompute().
    widget.parameters = replace(widget.parameters, on_high_voltage_v=19.0)
    pool.tasks[0].run()

    assert widget._recompute_worker_running is False
    assert widget.current_waveform is original_waveform
    assert widget.parameters.on_high_voltage_v == pytest.approx(19.0)
