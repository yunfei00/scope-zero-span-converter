"""Stable DCM parameter-extractor package.

Application code should import ``DcmParameterExtractorWidget`` from this
package instead of depending on a concrete legacy ``*_vN`` module.
"""

from .widget import DcmParameterExtractorWidget

__all__ = ["DcmParameterExtractorWidget"]
