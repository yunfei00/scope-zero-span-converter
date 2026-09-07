from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .spectrum import DcmSpectrum


@dataclass(frozen=True)
class SpectrumPeak:
    rank: int
    bin_index: int
    frequency_hz: float
    amplitude_dbv: float
    phase_deg: float | None

    @property
    def phase_valid(self) -> bool:
        return self.phase_deg is not None and np.isfinite(self.phase_deg)


def find_spectrum_peaks(
    spectrum: DcmSpectrum,
    *,
    top_n: int = 8,
    relative_floor_db: float = 80.0,
    min_frequency_hz: float = 0.0,
    min_separation_bins: int = 2,
) -> list[SpectrumPeak]:
    """Return strongest local maxima from the already-computed DCM spectrum.

    This intentionally operates on ``DcmSpectrum`` rather than recomputing an
    FFT, ensuring Peak Table, magnitude plot and phase plot all reference the
    same frequency bins and phase-validity policy.

    Candidate peaks must:
    - be finite local maxima (end bins are excluded);
    - be above ``peak - relative_floor_db``;
    - meet ``min_frequency_hz``;
    - be separated from already-selected stronger peaks by at least the
      requested number of FFT bins.
    """

    if top_n <= 0:
        return []
    if relative_floor_db <= 0 or not np.isfinite(relative_floor_db):
        raise ValueError("relative_floor_db 必须为正数")
    if min_separation_bins < 1:
        raise ValueError("min_separation_bins 必须至少为 1")

    frequency = np.asarray(spectrum.frequency_hz, dtype=float)
    amplitude = np.asarray(spectrum.amplitude_dbv, dtype=float)
    phase = np.asarray(spectrum.phase_deg, dtype=float)
    if not (len(frequency) == len(amplitude) == len(phase)) or len(amplitude) < 3:
        return []

    finite = np.isfinite(frequency) & np.isfinite(amplitude)
    if not np.any(finite):
        return []

    peak_level = float(np.max(amplitude[finite]))
    floor_dbv = peak_level - float(relative_floor_db)

    middle = np.arange(1, len(amplitude) - 1, dtype=int)
    candidate_mask = (
        finite[middle]
        & (frequency[middle] >= float(min_frequency_hz))
        & (amplitude[middle] >= amplitude[middle - 1])
        & (amplitude[middle] > amplitude[middle + 1])
        & (amplitude[middle] >= floor_dbv)
    )
    candidates = middle[candidate_mask]
    if len(candidates) == 0:
        return []

    # Strongest-first selection with a small bin-distance suppression prevents
    # one broadened/leaky lobe from occupying many rows of the customer table.
    ordered = candidates[np.argsort(amplitude[candidates])[::-1]]
    selected: list[int] = []
    for index in ordered:
        if any(abs(int(index) - existing) < min_separation_bins for existing in selected):
            continue
        selected.append(int(index))
        if len(selected) >= int(top_n):
            break

    peaks: list[SpectrumPeak] = []
    for rank, index in enumerate(selected, start=1):
        phase_value = float(phase[index]) if np.isfinite(phase[index]) else None
        peaks.append(
            SpectrumPeak(
                rank=rank,
                bin_index=index,
                frequency_hz=float(frequency[index]),
                amplitude_dbv=float(amplitude[index]),
                phase_deg=phase_value,
            )
        )
    return peaks
