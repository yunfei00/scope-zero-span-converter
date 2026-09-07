"""Commercial DCM analysis modules.

New DCM analysis implementation code belongs in this package. The legacy
versioned widget modules remain temporarily as compatibility shims while the
GUI is migrated in stages.
"""

from .axis import (
    apply_fixed_xy_axis,
    apply_fixed_y_axis,
    automatic_bounds,
    fixed_ticks,
    major_tick_step,
    nice_step,
)
from .markers import SpectrumMarker, spectrum_marker_at_frequency
from .peaks import SpectrumPeak, find_spectrum_peaks
from .spectrum import DcmSpectrum, compute_dcm_spectrum
from .time_markers import (
    TimeMarker,
    TimeMarkerDelta,
    time_marker_at_time,
    time_marker_delta,
)
from .zoom import ZoomBounds, ZoomState, ZoomTarget, normalized_bounds

__all__ = [
    "DcmSpectrum",
    "compute_dcm_spectrum",
    "SpectrumPeak",
    "find_spectrum_peaks",
    "SpectrumMarker",
    "spectrum_marker_at_frequency",
    "TimeMarker",
    "TimeMarkerDelta",
    "time_marker_at_time",
    "time_marker_delta",
    "fixed_ticks",
    "nice_step",
    "automatic_bounds",
    "major_tick_step",
    "apply_fixed_y_axis",
    "apply_fixed_xy_axis",
    "ZoomTarget",
    "ZoomBounds",
    "ZoomState",
    "normalized_bounds",
]
