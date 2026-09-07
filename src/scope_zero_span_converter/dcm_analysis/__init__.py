"""Commercial DCM analysis modules.

New DCM analysis implementation code belongs in this package. The legacy
versioned widget modules remain temporarily as compatibility shims while the
GUI is migrated in stages.
"""

from .spectrum import DcmSpectrum, compute_dcm_spectrum

__all__ = ["DcmSpectrum", "compute_dcm_spectrum"]
