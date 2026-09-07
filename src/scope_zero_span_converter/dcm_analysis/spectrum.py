from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..waveform_quality import analyze_time_axis, require_fft_safe


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
    phase_reference_description: str = "当前FFT记录起点（record start）"
    phase_visibility_threshold_dbv: float = -120.0
    phase_dynamic_range_db: float | None = 60.0

    @property
    def points(self) -> int:
        return len(self.frequency_hz)


def compute_dcm_spectrum(
    time_s: np.ndarray,
    voltage_v: np.ndarray,
    *,
    amplitude_floor_dbv: float = -300.0,
    phase_visible_floor_dbv: float = -120.0,
    phase_dynamic_range_db: float | None = 60.0,
) -> DcmSpectrum:
    """Compute the common complex FFT source for DCM magnitude and phase.

    Processing matches the validated v0.7 display definition while adding a
    commercial-safety phase visibility rule:

    - uniform-time-axis quality gate;
    - remove DC by subtracting the record mean;
    - apply a Hann window;
    - use a real-input one-sided FFT;
    - amplitude is coherent-gain corrected peak voltage per FFT bin in dBV;
    - DC/Nyquist bins are not doubled;
    - phase is wrapped to [-180, 180] degrees;
    - phase reference is the start of the current FFT record, not an absolute
      network-analyzer/S-parameter phase reference;
    - weak-bin phase is hidden below the stricter of the absolute phase floor
      and ``peak - phase_dynamic_range_db``.

    The dynamic threshold prevents visually random phase from being presented
    as meaningful simply because a customer's noise floor happens to be above
    a fixed -120 dBV threshold.
    """

    t = np.asarray(time_s, dtype=float)
    v = np.asarray(voltage_v, dtype=float)
    if len(t) < 2 or len(t) != len(v):
        empty = np.asarray([], dtype=float)
        return DcmSpectrum(empty, empty, empty, float("nan"))

    quality = analyze_time_axis(t)
    require_fft_safe(quality)
    dt = quality.median_dt_s

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

    phase_threshold_dbv = float(phase_visible_floor_dbv)
    dynamic_range = None
    if phase_dynamic_range_db is not None:
        dynamic_range = float(phase_dynamic_range_db)
        if not np.isfinite(dynamic_range) or dynamic_range <= 0:
            raise ValueError("phase_dynamic_range_db 必须为正数或 None")
        finite_amplitude = amplitude_dbv[np.isfinite(amplitude_dbv)]
        if len(finite_amplitude):
            peak_dbv = float(np.max(finite_amplitude))
            phase_threshold_dbv = max(
                phase_threshold_dbv,
                peak_dbv - dynamic_range,
            )

    phase_deg = np.angle(complex_spectrum, deg=True).astype(float, copy=False)
    phase_deg = np.asarray(phase_deg, dtype=float).copy()
    phase_deg[amplitude_dbv < phase_threshold_dbv] = np.nan

    return DcmSpectrum(
        frequency_hz=np.asarray(frequency_hz, dtype=float),
        amplitude_dbv=np.asarray(amplitude_dbv, dtype=float),
        phase_deg=phase_deg,
        sample_interval_s=dt,
        phase_visibility_threshold_dbv=phase_threshold_dbv,
        phase_dynamic_range_db=dynamic_range,
    )
