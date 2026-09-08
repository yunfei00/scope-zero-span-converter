from __future__ import annotations

import numpy as np
from PySide6.QtCore import QObject, QRunnable, Signal

from ..dcm_discontinuous_extractor import DcmDiscontinuousExtractionResult
from ..dcm_global_refiner import DcmGlobalRefinementResult, refine_dcm_parameters_globally
from ..dcm_parameter_extractor import DcmBasicExtractionResult
from ..dcm_ringing_extractor import DcmRingingExtractionResult


class GlobalRefinementWorkerSignals(QObject):
    finished = Signal(int, object)
    failed = Signal(int, str)


class GlobalRefinementWorkerTask(QRunnable):
    """Run the expensive fourth-stage global refinement off the GUI thread."""

    def __init__(
        self,
        *,
        request_id: int,
        time_s: np.ndarray,
        voltage_v: np.ndarray,
        basic: DcmBasicExtractionResult,
        ringing: DcmRingingExtractionResult,
        dcm: DcmDiscontinuousExtractionResult,
        max_iterations: int = 8,
        max_optimization_points: int = 18_000,
    ) -> None:
        super().__init__()
        self.request_id = int(request_id)
        # Keep references instead of copying potentially very large customer
        # waveforms. Extraction results are immutable/read-only during this task.
        self.time_s = np.asarray(time_s, dtype=float)
        self.voltage_v = np.asarray(voltage_v, dtype=float)
        self.basic = basic
        self.ringing = ringing
        self.dcm = dcm
        self.max_iterations = int(max_iterations)
        self.max_optimization_points = int(max_optimization_points)
        self.signals = GlobalRefinementWorkerSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result: DcmGlobalRefinementResult = refine_dcm_parameters_globally(
                self.time_s,
                self.voltage_v,
                self.basic,
                self.ringing,
                self.dcm,
                max_iterations=self.max_iterations,
                max_optimization_points=self.max_optimization_points,
            )
        except Exception as exc:
            self.signals.failed.emit(self.request_id, str(exc))
            return
        self.signals.finished.emit(self.request_id, result)


__all__ = ["GlobalRefinementWorkerSignals", "GlobalRefinementWorkerTask"]
