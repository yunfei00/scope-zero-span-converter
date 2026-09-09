from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QObject, QRunnable, Signal

from .spectrum import DcmSpectrum, compute_dcm_spectrum


class SpectrumWorkerSignals(QObject):
    """Thread-safe signals emitted by a one-shot spectrum task."""

    # Python object is intentional for waveform_id: CPython object identities
    # routinely exceed Qt's signed 32-bit ``int`` range on 64-bit platforms.
    finished = Signal(int, object, object)
    failed = Signal(int, object, str)


@dataclass(frozen=True)
class SpectrumWorkerOptions:
    amplitude_floor_dbv: float = -300.0
    phase_visible_floor_dbv: float = -120.0
    phase_dynamic_range_db: float | None = 60.0


class SpectrumWorkerTask(QRunnable):
    """Compute one DCM spectrum without touching any QWidget.

    Arrays are referenced, not copied. DCM waveform arrays are immutable by
    convention after generation, so a large 5M-point waveform is not duplicated
    on the GUI thread just to hand it to the worker.
    """

    def __init__(
        self,
        *,
        request_id: int,
        waveform_id: int,
        time_s: np.ndarray,
        voltage_v: np.ndarray,
        options: SpectrumWorkerOptions | None = None,
    ) -> None:
        super().__init__()
        self.request_id = int(request_id)
        self.waveform_id = int(waveform_id)
        self.time_s = np.asarray(time_s, dtype=float)
        self.voltage_v = np.asarray(voltage_v, dtype=float)
        self.options = options or SpectrumWorkerOptions()
        self.signals = SpectrumWorkerSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            spectrum: DcmSpectrum = compute_dcm_spectrum(
                self.time_s,
                self.voltage_v,
                amplitude_floor_dbv=self.options.amplitude_floor_dbv,
                phase_visible_floor_dbv=self.options.phase_visible_floor_dbv,
                phase_dynamic_range_db=self.options.phase_dynamic_range_db,
            )
        except Exception as exc:
            self.signals.failed.emit(
                self.request_id,
                self.waveform_id,
                str(exc),
            )
            return

        self.signals.finished.emit(
            self.request_id,
            self.waveform_id,
            spectrum,
        )


__all__ = [
    "SpectrumWorkerOptions",
    "SpectrumWorkerSignals",
    "SpectrumWorkerTask",
]
