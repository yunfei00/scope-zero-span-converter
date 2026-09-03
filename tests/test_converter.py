import json

import numpy as np
import pandas as pd
import pytest

from scope_zero_span_converter.config import AppConfig
from scope_zero_span_converter.converter import convert


def test_200mhz_cw_converts_to_stable_zerospan(tmp_path):
    fs = 1e9
    duration = 10e-6
    t = np.arange(int(fs * duration)) / fs

    peak_v = 0.2
    waveform = peak_v * np.cos(2 * np.pi * 200e6 * t)

    waveform_path = tmp_path / "waveform.csv"
    pd.DataFrame({"time_s": t, "voltage_v": waveform}).to_csv(
        waveform_path,
        index=False,
    )

    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps({}), encoding="utf-8")

    config = AppConfig()
    config.signal.center_frequency_hz = 200e6
    config.signal.rbw_hz = 10e6
    config.signal.vbw_hz = 10e6
    config.conversion.use_metadata_parameters = False
    config.conversion.resample_to_fsw_axis = False
    config.conversion.impedance_ohm = 50.0
    config.scope.analog_bandwidth_hz = 350e6

    result = convert(waveform_path, metadata_path, config)

    # 0.2 Vpeak -> 0.1414 Vrms -> 0.4 mW -> about -3.98 dBm.
    quarter = len(result.amplitude_dbm) // 4
    middle = result.amplitude_dbm[quarter:-quarter]
    assert np.median(middle) == pytest.approx(-3.9794, abs=0.5)
    assert np.std(middle) < 0.5
