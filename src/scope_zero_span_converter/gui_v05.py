"""Compatibility imports for the historical v0.5 GUI module.

All production behavior now belongs to stable, versionless modules.  Keep these
aliases temporarily so existing integrations do not break during legacy
cleanup.
"""

from __future__ import annotations

from .dcm_analysis.widget import DcmAnalysisWidget
from .main_window import MainWindow

__all__ = ["DcmAnalysisWidget", "MainWindow"]
