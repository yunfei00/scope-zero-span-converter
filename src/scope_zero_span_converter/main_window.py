"""Formal application main-window entry point.

``gui_v05`` remains a migration implementation. New application startup code
imports this module so commercialization work can move individual behaviors into
stable, versionless modules without creating another ``gui_v06.py`` layer.
"""

from __future__ import annotations

from .gui_v05 import MainWindow as _CompatibilityMainWindow
from .waveform_research_display import redraw_waveform_research


class MainWindow(_CompatibilityMainWindow):
    """Production main window with formal research-page rendering."""

    def _redraw_waveform_and_conversion(self) -> None:
        redraw_waveform_research(self)


__all__ = ["MainWindow"]
