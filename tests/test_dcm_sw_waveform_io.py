import numpy as np
import pandas as pd
import pytest

from scope_zero_span_converter.dcm_sw_generator import (
    DcmSwParameters,
    generate_dcm_sw_waveform,
    save_dcm_sw_waveform,
)
from scope_zero_span_converter.dcm_sw_waveform_io import (
    load_saved_dcm_sw_waveform,
    parameter_sidecar_for,
)


def test_saved_dcm_sw_waveform_can_be_loaded_exactly(tmp_path):
    parameters = DcmSwParameters(
        rise_time_s=0.0,
        fall_time_s=0.0,
        rise_spike_amplitude_v=5.5,
        fall_spike_amplitude_v=-7.25,
        random_seed=24680,
    )
    original = generate_dcm_sw_waveform(parameters)
    csv_path, parameters_path = save_dcm_sw_waveform(
        original,
        tmp_path / "saved_dcm.csv",
    )

    loaded, restored_parameters_path = load_saved_dcm_sw_waveform(csv_path)

    assert restored_parameters_path == parameters_path
    assert loaded.parameters.rise_time_s == pytest.approx(0.0)
    assert loaded.parameters.fall_time_s == pytest.approx(0.0)
    assert loaded.parameters.rise_spike_amplitude_v == pytest.approx(5.5)
    assert loaded.parameters.fall_spike_amplitude_v == pytest.approx(-7.25)
    assert loaded.parameters.random_seed == 24680
    assert loaded.sample_rate_hz == pytest.approx(original.sample_rate_hz, rel=1e-9)

    np.testing.assert_allclose(loaded.time_s, original.time_s, rtol=0, atol=1e-18)
    np.testing.assert_allclose(loaded.voltage_v, original.voltage_v, rtol=0, atol=1e-12)
    np.testing.assert_allclose(
        loaded.ideal_voltage_v,
        original.ideal_voltage_v,
        rtol=0,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        loaded.spike_component_v,
        original.spike_component_v,
        rtol=0,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        loaded.discontinuous_component_v,
        original.discontinuous_component_v,
        rtol=0,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        loaded.noise_component_v,
        original.noise_component_v,
        rtol=0,
        atol=1e-12,
    )


def test_saved_waveform_loader_reports_missing_parameter_sidecar(tmp_path):
    csv_path = tmp_path / "missing_sidecar.csv"
    pd.DataFrame(
        {
            "time_s": np.linspace(0.0, 1e-6, 64),
            "voltage_v": np.zeros(64),
            "ideal_voltage_v": np.zeros(64),
            "spike_component_v": np.zeros(64),
            "discontinuous_component_v": np.zeros(64),
            "noise_component_v": np.zeros(64),
        }
    ).to_csv(csv_path, index=False)

    assert parameter_sidecar_for(csv_path).name == "missing_sidecar_parameters.json"
    with pytest.raises(FileNotFoundError, match="真值参数 JSON"):
        load_saved_dcm_sw_waveform(csv_path)


def test_saved_waveform_loader_rejects_plain_two_column_csv(tmp_path):
    parameters = DcmSwParameters()
    params_waveform = generate_dcm_sw_waveform(parameters)
    _, parameters_path = save_dcm_sw_waveform(
        params_waveform,
        tmp_path / "template.csv",
    )

    plain_csv = tmp_path / "plain.csv"
    pd.DataFrame(
        {
            "time_s": params_waveform.time_s,
            "voltage_v": params_waveform.voltage_v,
        }
    ).to_csv(plain_csv, index=False)

    with pytest.raises(ValueError, match="普通 time_s,voltage_v CSV"):
        load_saved_dcm_sw_waveform(
            plain_csv,
            parameters_path=parameters_path,
        )
