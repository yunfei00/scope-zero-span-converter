"""Legacy import shim for the original two-panel DCM/Zero Span widget."""

from __future__ import annotations

from .dcm_analysis.controls import DcmAnalysisControls


class DcmZeroSpanWidget(DcmAnalysisControls):
    """Backward-compatible name retained for isolated legacy callers."""


__all__ = ["DcmZeroSpanWidget"]
