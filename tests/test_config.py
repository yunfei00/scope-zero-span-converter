from scope_zero_span_converter.config import AppConfig, load_config, save_config


def test_config_roundtrip(tmp_path):
    config = AppConfig()
    config.input.waveform_file = "data/waveform.csv"
    config.signal.center_frequency_hz = 200e6
    config.signal.rbw_hz = 10e6
    config.conversion.calibration_db = -2.5
    config.conversion.use_metadata_parameters = False

    path = tmp_path / "config.json"
    save_config(config, path)
    loaded = load_config(path)

    assert loaded.input.waveform_file == "data/waveform.csv"
    assert loaded.signal.center_frequency_hz == 200e6
    assert loaded.signal.rbw_hz == 10e6
    assert loaded.conversion.calibration_db == -2.5
    assert loaded.conversion.use_metadata_parameters is False
