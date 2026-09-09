"""Compatibility import for the historical v0.4 main window.

Production startup uses :mod:`scope_zero_span_converter.main_window`.  The
versioned module remains importable for downstream scripts while the legacy
surface is retired in a later cleanup phase.
"""

from __future__ import annotations

from .research_workspace import ResearchWorkspaceWindow as MainWindow, main

__all__ = ["MainWindow", "main"]
