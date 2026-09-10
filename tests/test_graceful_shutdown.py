from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from scope_zero_span_converter.app import collect_app_state
from scope_zero_span_converter.dcm_analysis.widget import DcmAnalysisWidget
from scope_zero_span_converter.main_window import MainWindow
import scope_zero_span_converter.main_window as main_window_module


def _qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _CloseEvent:
    def __init__(self) -> None:
        self.accepted = False
        self.ignored = False

    def accept(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.ignored = True


class _CancelableTask:
    def __init__(self) -> None:
        self.cancel_calls = 0

    def cancel(self) -> None:
        self.cancel_calls += 1


class _NonCancelableTask:
    def __init__(self) -> None:
        self.cancel_calls = 0

    def cancel(self) -> None:
        self.cancel_calls += 1


class _ManualPool:
    def __init__(self) -> None:
        self.tasks = []

    def start(self, task) -> None:
        self.tasks.append(task)


def _window() -> MainWindow:
    _qapp()
    return MainWindow()


def test_close_without_workers_accepts_immediately_and_prepares_state_collection():
    window = _window()
    event = _CloseEvent()

    window.closeEvent(event)

    assert event.accepted is True
    assert event.ignored is False
    assert window._shutdown_requested is True
    assert window._shutdown_ready is True
    state = collect_app_state(window)
    assert state.selected_tab_id == window.tab_id_for_index(window.tabs.currentIndex())
    assert "dcm_analysis" in state.workspace


def test_close_with_worker_can_return_without_changing_running_state(monkeypatch):
    window = _window()
    task = _NonCancelableTask()
    window._conversion_task = task
    monkeypatch.setattr(window, "_confirm_safe_shutdown", lambda: False)
    event = _CloseEvent()

    window.closeEvent(event)

    assert event.ignored is True
    assert event.accepted is False
    assert window._shutdown_requested is False
    assert window._conversion_task is task
    assert window.convert_button.isEnabled() is True


def test_safe_close_enters_shutdown_once_and_second_close_waits(monkeypatch):
    window = _window()
    window._conversion_task = _NonCancelableTask()
    confirmations = []
    monkeypatch.setattr(
        window,
        "_confirm_safe_shutdown",
        lambda: confirmations.append(True) or True,
    )
    first = _CloseEvent()
    second = _CloseEvent()

    window.closeEvent(first)
    window.closeEvent(second)

    assert confirmations == [True]
    assert first.ignored is True
    assert second.ignored is True
    assert window._shutdown_requested is True
    assert window._shutdown_ready is False
    assert window._shutdown_poll_timer.isActive() is True
    assert window._shutdown_poll_timer.interval() == 75


def test_begin_shutdown_clears_pending_and_stops_every_debounce_timer(monkeypatch):
    window = _window()
    monkeypatch.setattr(main_window_module.QTimer, "singleShot", lambda *_args: None)
    window._roi_pending_payload = object()
    window.dcm_analysis_tab._spectrum_pending_waveform = (
        window.dcm_analysis_tab.current_waveform
    )
    window.dcm_analysis_tab._spectrum_pending_generation = 123
    window.dcm_analysis_tab._recompute_pending = object()
    for timer in (
        window._conversion_timer,
        window._roi_controls_timer,
        window.dcm_analysis_tab._update_timer,
        window.dcm_extractor_tab._parameter_timer,
        window.dcm_generator_tab._auto_timer,
    ):
        timer.start()

    window.begin_shutdown(auto_close=False)

    assert window._roi_pending_payload is None
    assert window.dcm_analysis_tab._spectrum_pending_waveform is None
    assert window.dcm_analysis_tab._spectrum_pending_generation is None
    assert window.dcm_analysis_tab._recompute_pending is None
    assert all(
        not timer.isActive()
        for timer in (
            window._conversion_timer,
            window._roi_controls_timer,
            window.dcm_analysis_tab._update_timer,
            window.dcm_extractor_tab._parameter_timer,
            window.dcm_generator_tab._auto_timer,
        )
    )


def test_shutdown_blocks_new_roi_spectrum_recompute_and_refinement_workers():
    window = _window()
    roi_pool = _ManualPool()
    spectrum_pool = _ManualPool()
    recompute_pool = _ManualPool()
    refine_pool = _ManualPool()
    window._worker_pool = roi_pool
    window.dcm_analysis_tab._spectrum_thread_pool = spectrum_pool
    window.dcm_analysis_tab._recompute_thread_pool = recompute_pool
    window.dcm_extractor_tab._global_refinement_pool = refine_pool
    window.begin_shutdown(auto_close=False)

    window.run_full_conversion()
    window.run_batch_conversion()
    window._start_roi_worker((1, None, None, None, None, 0.0))
    waveform = window.dcm_analysis_tab.current_waveform
    assert waveform is not None
    window.dcm_analysis_tab._start_spectrum_worker(waveform)
    window.dcm_analysis_tab._start_recompute_worker(object())
    window.dcm_extractor_tab.run_global_refinement()

    assert roi_pool.tasks == []
    assert spectrum_pool.tasks == []
    assert recompute_pool.tasks == []
    assert refine_pool.tasks == []


def test_shutdown_cancels_batch_and_all_refinements_but_not_full_conversion():
    window = _window()
    batch = _CancelableTask()
    full = _NonCancelableTask()
    refinement = _CancelableTask()
    window._batch_task = batch
    window._conversion_task = full
    window.dcm_extractor_tab._global_refinement_tasks[41] = refinement
    window.dcm_extractor_tab._global_refinement_active_request_id = 41
    window.dcm_extractor_tab._global_refinement_task = refinement

    window.begin_shutdown(auto_close=False)

    assert batch.cancel_calls == 1
    assert refinement.cancel_calls == 1
    assert full.cancel_calls == 0
    assert window._conversion_task is full
    assert window.has_active_background_tasks() is True


def test_full_conversion_terminal_controls_automatic_shutdown(monkeypatch):
    window = _window()
    full = _NonCancelableTask()
    window._conversion_task = full
    scheduled = []
    monkeypatch.setattr(
        main_window_module.QTimer,
        "singleShot",
        lambda delay, callback: scheduled.append((delay, callback)),
    )
    window.begin_shutdown()

    assert window._shutdown_ready is False
    assert scheduled == []

    window._on_full_conversion_finished(object())

    assert window._conversion_task is None
    assert window._shutdown_ready is True
    assert window._shutdown_close_scheduled is True
    assert len(scheduled) == 1

    final_event = _CloseEvent()
    window.closeEvent(final_event)
    assert final_event.accepted is True


def test_late_roi_terminal_during_shutdown_only_releases_task(monkeypatch):
    window = _window()
    task = object()
    window._roi_task = task
    window._roi_active_request_id = 17
    window._roi_pending_payload = object()
    monkeypatch.setattr(
        window,
        "_redraw_waveform_and_conversion",
        lambda: (_ for _ in ()).throw(AssertionError("must not redraw")),
    )
    monkeypatch.setattr(main_window_module.QTimer, "singleShot", lambda *_args: None)
    window.begin_shutdown()
    payload = type("Payload", (), {"request_id": 17})()

    window._on_roi_worker_finished(payload)

    assert window._roi_task is None
    assert window._roi_pending_payload is None
    assert window._shutdown_ready is True


def test_late_spectrum_and_recompute_terminals_do_not_redraw():
    analysis = DcmAnalysisWidget()
    waveform = analysis.current_waveform
    assert waveform is not None
    analysis._spectrum_worker_running = True
    analysis._spectrum_active_task = object()
    analysis._spectrum_active_request_id = 7
    analysis._spectrum_active_waveform_id = id(waveform)
    analysis._recompute_worker_running = True
    analysis._recompute_active_task = object()
    analysis._recompute_active_request_id = 9
    analysis._redraw = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("must not redraw")
    )
    analysis.begin_shutdown()

    analysis._on_spectrum_worker_finished(7, id(waveform), object())
    result = type("Result", (), {"request_id": 9})()
    analysis._on_recompute_worker_finished(result)

    assert analysis._spectrum_active_task is None
    assert analysis._recompute_active_task is None
    assert analysis.has_active_background_tasks() is False


def test_worker_failures_during_shutdown_do_not_open_dialogs(monkeypatch):
    window = _window()
    window._conversion_task = _NonCancelableTask()
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("must not open a dialog")
        ),
    )
    monkeypatch.setattr(main_window_module.QTimer, "singleShot", lambda *_args: None)
    window.begin_shutdown()

    window._on_full_conversion_failed("controlled failure")

    assert window._conversion_task is None
    assert window._shutdown_ready is True


def test_extractor_shutdown_keeps_task_tracked_until_terminal_and_suppresses_dialog(
    monkeypatch,
):
    window = _window()
    extractor = window.dcm_extractor_tab
    task = _CancelableTask()
    extractor._global_refinement_tasks[12] = task
    extractor._global_refinement_active_request_id = 12
    extractor._global_refinement_task = task
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("must not open a dialog")
        ),
    )

    extractor.begin_shutdown()

    assert task.cancel_calls == 1
    assert extractor.has_active_background_tasks() is True
    extractor._on_global_refinement_failed(12, "controlled failure")
    assert extractor.has_active_background_tasks() is False
    assert extractor._global_refinement_task is None


def test_shutdown_polling_starts_only_while_waiting_and_finishes_once(monkeypatch):
    window = _window()
    assert window._shutdown_poll_timer.isActive() is False
    window._conversion_task = _NonCancelableTask()
    scheduled = []
    monkeypatch.setattr(
        main_window_module.QTimer,
        "singleShot",
        lambda delay, callback: scheduled.append((delay, callback)),
    )

    window.begin_shutdown()
    assert window._shutdown_poll_timer.isActive() is True
    window._maybe_finish_shutdown()
    assert scheduled == []

    window._conversion_task = None
    window._maybe_finish_shutdown()
    window._maybe_finish_shutdown()

    assert window._shutdown_poll_timer.isActive() is False
    assert window._shutdown_ready is True
    assert len(scheduled) == 1
