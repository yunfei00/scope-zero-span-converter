"""Stable GUI entry point for DCM linked analysis.

The versioned widget modules are retained temporarily for compatibility while
commercialization refactoring is in progress. New application code must import
from this module instead of depending on a concrete ``*_vN`` implementation.
"""

from __future__ import annotations

from .dcm_zero_span_widget_v10 import DcmZeroSpanWidget as _CurrentDcmAnalysisWidget


class DcmAnalysisWidget(_CurrentDcmAnalysisWidget):
    """Commercial-stable entry point for the four-panel DCM analysis page."""


__all__ = ["DcmAnalysisWidget"]
