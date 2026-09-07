from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DcmSpectrum:
    """Single-sided DCM FFT result used by magnitude and phase views."""

    frequency_hz: np.ndarray
    amplitude_dbv: np.ndarray
    phase_deg: np.ndarray
    sample_interval_s: float
    window: str = "hann"
    amplitude_definition: str = "single_sided_peak_dbv_per_bin"
    phase_reference: str = "record_start"

    @property
    def points(self) -> int:
        return len(self.frequency_hz)


def compute_dcm_spectrum(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    *,
    amplitude_floor_dbv: float = -300.0,
    phase_visible_floor_dbv: float = -120.0,
) -> DcmSpectrum:
    """Compute the common complex FFT source for DCM magnitude and phase.

    Processing is intentionally identical to the v0.7 GUI baseline:

    - remove DC by subtracting the record mean;
    - apply a Hann window;
    - use a real-input one-sided FFT;
    - amplitude is coherent-gain corrected peak voltage per FFT bin in dBV;
    - DC/Nyquist bins are not doubled;
    - phase is wrapped to [-180, 180] degrees;
    - phase below the configured visible magnitude floor is masked as NaN.

    Time-axis quality validation is deliberately kept outside this function so
    Phase 3 can provide one shared validation policy for FFT and Zero Span.
    """

    t = np.asarray(time_s, dtype=float)
    v = np.asarray(voltage_v, dtype=float)
    if len(t) < 2 or len(t) != len(v):
        empty = np.asarray([], dtype=float)
        return DcmSpectrum(empty, empty, empty, float("nan"))

    dt = float(np.median(np.diff(t)))
    if not np.isfinite(dt) or dt <= 0:
        empty = np.asarray([], dtype=float)
        return DcmSpectrum(empty, empty, empty, dt)

    n = len(v)
    ac = v - float(np.mean(v))
    window = np.hanning(n)
    coherent_sum = float(np.sum(window))
    if coherent_sum <= 0:
        empty = np.asarray([], dtype=float)
        return DcmSpectrum(empty, empty, empty, dt)

    complex_spectrum = np.fft.rfft(ac * window)
    amplitude_peak_v = 2.0 * np.abs(complex_spectrum) / coherent_sum
    if len(amplitude_peak_v):
        amplitude_peak_v[0] *= 0.5
        if n % 2 == 0 and len(amplitude_peak_v) > 1:
            amplitude_peak_v[-1] *= 0.5

    floor_v = 10.0 ** (float(amplitude_floor_dbv) / 20.0)
    amplitude_dbv = 20.0 * np.log10(np.maximum(amplitude_peak_v, floor_v))
    frequency_hz = np.fft.rfftfreq(n, d=dt)

    phase_deg = np.angle(complex_spectrum, deg=True).astype(float, copy=False)
    phase_deg = np.asarray(phase_deg, dtype=float).copy()
    phase_deg[amplitude_dbv < float(phase_visible_floor_dbv)] = np.nan

    return DcmSpectrum(
        frequency_hz=np.asarray(frequency_hz, dtype=float),
        amplitude_dbv=np.asarray(amplitude_dbv, dtype=float),
        phase_deg=phase_deg,
        sample_interval_s=dt,
    )
