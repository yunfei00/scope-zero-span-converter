from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QRunnable, Signal

from .config import AppConfig
from .waveform_research import WaveformResearchConversion, convert_waveform_region


@dataclass(frozen=True)
class RoiConversionWorkerResult:
    request_id: int
    conversion: WaveformResearchConversion
    origin_s: float


class RoiConversionWorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(int, str)


class RoiConversionWorkerTask(QRunnable):
    """Convert one large ROI without touching Qt widgets."""

    def __init__(
        self,
        *,
        request_id: int,
        time_s: np.ndarray,
        voltage_v: np.ndarray,
        metadata_path: str | Path,
        config: AppConfig,
        origin_s: float,
    ) -> None:
        super().__init__()
        self.request_id = int(request_id)
        self.time_s = np.asarray(time_s, dtype=float)
        self.voltage_v = np.asarray(voltage_v, dtype=float)
        self.metadata_path = Path(metadata_path)
        self.config = deepcopy(config)
        self.origin_s = float(origin_s)
        self.signals = RoiConversionWorkerSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            conversion = convert_waveform_region(
                self.time_s,
                self.voltage_v,
                self.metadata_path,
                self.config,
            )
        except Exception as exc:
            self.signals.failed.emit(self.request_id, str(exc))
            return

        self.signals.finished.emit(
            RoiConversionWorkerResult(
                request_id=self.request_id,
                conversion=conversion,
                origin_s=self.origin_s,
            )
        )


__all__ = [
    "RoiConversionWorkerResult",
    "RoiConversionWorkerSignals",
    "RoiConversionWorkerTask",
]
