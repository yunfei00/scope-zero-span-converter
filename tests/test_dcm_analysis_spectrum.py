from __future__ import annotations

import numpy as np

from scope_zero_span_converter.dcm_analysis.spectrum import (
    compute_dcm_spectrum,
    waveform_signature,
)


def test_dcm_spectrum_returns_common_magnitude_phase_bins():
    fs = 1e9
    n = 10_000
    t = np.arange(n, dtype=float) / fs
    v = np.sin(2.0 * np.pi * 50e6 * t)

    result = compute_dcm_spectrum(t, v)

    assert result.points == n // 2 + 1
    assert len(result.frequency_hz) == len(result.amplitude_dbv) == len(result.phase_deg)
    assert result.window == "hann"
    assert result.amplitude_definition == "single_sided_peak_dbv_per_bin"
    assert result.phase_reference == "record_start"

    peak_index = int(np.nanargmax(result.amplitude_dbv))
    assert np.isclose(result.frequency_hz[peak_index], 50e6, atol=fs / n)
    assert np.isclose(result.amplitude_dbv[peak_index], 0.0, atol=0.05)
    assert np.isfinite(result.phase_deg[peak_index])


def test_phase_floor_masks_only_low_magnitude_bins():
    fs = 1e9
    n = 4096
    t = np.arange(n, dtype=float) / fs
    v = np.sin(2.0 * np.pi * 125e6 * t)

    result = compute_dcm_spectrum(
        t,
        v,
        phase_visible_floor_dbv=-6.0,
    )

    strong = result.amplitude_dbv >= -6.0
    weak = result.amplitude_dbv < -6.0
    assert np.any(strong)
    assert np.any(weak)
    assert np.all(np.isfinite(result.phase_deg[strong]))
    assert np.all(np.isnan(result.phase_deg[weak]))


def test_invalid_spectrum_input_returns_empty_result():
    result = compute_dcm_spectrum(
        np.asarray([0.0]),
        np.asarray([1.0]),
    )
    assert result.points == 0
    assert len(result.amplitude_dbv) == 0
    assert len(result.phase_deg) == 0


def test_waveform_signature_changes_when_only_voltage_data_changes():
    fs = 1e9
    time_s = np.arange(10_000, dtype=float) / fs
    voltage_a = np.sin(2.0 * np.pi * 50e6 * time_s)
    voltage_b = voltage_a.copy()
    voltage_b[5_000] += 1e-9

    assert len(voltage_a) == len(voltage_b)
    assert waveform_signature(time_s, voltage_a) != waveform_signature(
        time_s,
        voltage_b,
    )
