from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .spectrum import DcmSpectrum


@dataclass(frozen=True)
class SpectrumMarker:
    requested_frequency_hz: float
    bin_index: int
    frequency_hz: float
    amplitude_dbv: float
    phase_deg: float | None

    @property
    def phase_valid(self) -> bool:
        return bool(self.phase_deg is not None and np.isfinite(self.phase_deg))

    @property
    def frequency_error_hz(self) -> float:
        return self.frequency_hz - self.requested_frequency_hz


def spectrum_marker_at_frequency(
    spectrum: DcmSpectrum,
    requested_frequency_hz: float,
) -> SpectrumMarker:
    """Resolve a marker to the nearest actual FFT bin.

    Phase is deliberately read from the same bin as magnitude. Requests outside
    the available frequency axis are rejected instead of silently clamped.
    """

    requested = float(requested_frequency_hz)
    if not np.isfinite(requested):
        raise ValueError("Marker 频率必须是有限数值")

    frequency = np.asarray(spectrum.frequency_hz, dtype=float)
    amplitude = np.asarray(spectrum.amplitude_dbv, dtype=float)
    phase = np.asarray(spectrum.phase_deg, dtype=float)
    if not (len(frequency) == len(amplitude) == len(phase)) or len(frequency) == 0:
        raise ValueError("当前频谱没有可用 Marker 数据")
    if not np.all(np.isfinite(frequency)):
        raise ValueError("频率轴包含无效值")

    low = float(frequency[0])
    high = float(frequency[-1])
    if requested < low or requested > high:
        raise ValueError(
            f"Marker 频率 {requested:g} Hz 超出当前频谱范围 {low:g}~{high:g} Hz"
        )

    position = int(np.searchsorted(frequency, requested))
    if position <= 0:
        index = 0
    elif position >= len(frequency):
        index = len(frequency) - 1
    else:
        left = position - 1
        right = position
        index = left if abs(frequency[left] - requested) <= abs(frequency[right] - requested) else right

    phase_value = float(phase[index]) if np.isfinite(phase[index]) else None
    return SpectrumMarker(
        requested_frequency_hz=requested,
        bin_index=index,
        frequency_hz=float(frequency[index]),
        amplitude_dbv=float(amplitude[index]),
        phase_deg=phase_value,
    )
