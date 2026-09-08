"""Formal DCM parameter-extractor GUI entry point.

The historical v7 implementation remains in place during the compatibility
window. Production code imports this module so future extractor work can move
behind a stable API without another version-suffixed GUI dependency.
"""

from __future__ import annotations

from ..dcm_parameter_extractor_widget_v7 import (
    DcmParameterExtractorWidget as _LegacyExtractorWidget,
)


class DcmParameterExtractorWidget(_LegacyExtractorWidget):
    """Stable extractor widget entry point."""


__all__ = ["DcmParameterExtractorWidget"]
