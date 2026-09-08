from __future__ import annotations

from threading import Event

from PySide6.QtCore import QObject, QRunnable, Signal

from .batch import BatchItemResult, BatchRunResult, run_batch
from .config import AppConfig


class BatchWorkerSignals(QObject):
    started = Signal(int)
    progress = Signal(int, int, object)
    finished = Signal(object)
    failed = Signal(str)


class BatchWorkerTask(QRunnable):
    """Run a complete batch outside the GUI thread.

    Cancellation is cooperative between jobs. The active job is allowed to
    finish its conversion/save so customer output is never intentionally left
    half-written.
    """

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.signals = BatchWorkerSignals()
        self._cancel_event = Event()
        self.setAutoDelete(True)

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_event.is_set()

    def cancel(self) -> None:
        self._cancel_event.set()

    def run(self) -> None:
        try:
            result: BatchRunResult = run_batch(
                self.config,
                start_callback=self.signals.started.emit,
                progress_callback=self._emit_progress,
                should_cancel=self._cancel_event.is_set,
            )
        except Exception as exc:
            self.signals.failed.emit(str(exc))
            return
        self.signals.finished.emit(result)

    def _emit_progress(
        self,
        current: int,
        total: int,
        item: BatchItemResult,
    ) -> None:
        self.signals.progress.emit(int(current), int(total), item)


__all__ = ["BatchWorkerSignals", "BatchWorkerTask"]
