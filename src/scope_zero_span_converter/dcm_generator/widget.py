"""Formal DCM waveform-generator GUI entry point.

The historical v3 implementation remains in place during the compatibility
window. Production code imports this module so future generator work can move
behind a stable API without another version-suffixed GUI dependency.
"""

from __future__ import annotations

from ..dcm_sw_generator_widget_v3 import DcmSwGeneratorWidget as _LegacyGeneratorWidget


class DcmSwGeneratorWidget(_LegacyGeneratorWidget):
    """Stable generator widget entry point."""


__all__ = ["DcmSwGeneratorWidget"]
