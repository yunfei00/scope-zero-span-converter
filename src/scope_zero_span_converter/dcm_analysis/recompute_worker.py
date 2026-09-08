from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, Signal

from ..dcm_sw_generator import DcmSwParameters, DcmSwWaveform, generate_dcm_sw_waveform
from ..dcm_zero_span_link import (
    DcmZeroSpanResult,
    ZeroSpanProfile,
    convert_dcm_waveform_to_zero_span,
)


@dataclass(frozen=True)
class DcmRecomputeWorkerResult:
    request_id: int
    waveform: DcmSwWaveform | None
    zero_span: DcmZeroSpanResult | None
    dcm_error: str | None = None
    zero_span_error: str | None = None


class DcmRecomputeWorkerSignals(QObject):
    finished = Signal(object)


class DcmRecomputeWorkerTask(QRunnable):
    """Generate DCM and run linked Zero Span conversion outside the GUI thread."""

    def __init__(
        self,
        *,
        request_id: int,
        parameters: DcmSwParameters,
        profile: ZeroSpanProfile,
    ) -> None:
        super().__init__()
        self.request_id = int(request_id)
        self.parameters = deepcopy(parameters)
        self.profile = deepcopy(profile)
        self.signals = DcmRecomputeWorkerSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            waveform = generate_dcm_sw_waveform(self.parameters)
        except Exception as exc:
            self.signals.finished.emit(
                DcmRecomputeWorkerResult(
                    request_id=self.request_id,
                    waveform=None,
                    zero_span=None,
                    dcm_error=str(exc),
                )
            )
            return

        try:
            zero_span = convert_dcm_waveform_to_zero_span(waveform, self.profile)
        except Exception as exc:
            self.signals.finished.emit(
                DcmRecomputeWorkerResult(
                    request_id=self.request_id,
                    waveform=waveform,
                    zero_span=None,
                    zero_span_error=str(exc),
                )
            )
            return

        self.signals.finished.emit(
            DcmRecomputeWorkerResult(
                request_id=self.request_id,
                waveform=waveform,
                zero_span=zero_span,
            )
        )


__all__ = [
    "DcmRecomputeWorkerResult",
    "DcmRecomputeWorkerSignals",
    "DcmRecomputeWorkerTask",
]
