"""Stable DCM waveform-generator package.

Application code should import ``DcmSwGeneratorWidget`` from this package
instead of depending on a concrete legacy ``*_vN`` module.
"""

from .widget import DcmSwGeneratorWidget

__all__ = ["DcmSwGeneratorWidget"]
