import json

from scope_zero_span_converter.config import AppConfig, load_config, save_config


def test_config_roundtrip(tmp_path):
    config = AppConfig()
    config.input.waveform_file = "data/waveform.csv"
    config.input.fsw_reference_file = "data/fsw.csv"
    config.signal.center_frequency_hz = 200e6
    config.signal.rbw_hz = 10e6
    config.conversion.calibration_db = -2.5
    config.conversion.use_metadata_parameters = False
    config.comparison.enabled = True
    config.output.save_conversion_metadata = True

    path = tmp_path / "config.json"
    save_config(config, path)
    loaded = load_config(path)

    assert loaded.input.waveform_file == "data/waveform.csv"
    assert loaded.input.fsw_reference_file == "data/fsw.csv"
    assert loaded.signal.center_frequency_hz == 200e6
    assert loaded.signal.rbw_hz == 10e6
    assert loaded.conversion.calibration_db == -2.5
    assert loaded.conversion.use_metadata_parameters is False
    assert loaded.comparison.enabled is True
    assert loaded.output.save_conversion_metadata is True


def test_v01_config_remains_compatible(tmp_path):
    old_config = {
        "schema_version": 1,
        "input": {
            "waveform_file": "waveform.csv",
            "metadata_file": "metadata.json",
        },
        "signal": {
            "center_frequency_hz": 200e6,
            "span_hz": 0.0,
            "rbw_hz": 10e6,
            "vbw_hz": 10e6,
        },
        "conversion": {
            "detector": "rms",
            "rbw_filter": "gaussian",
            "vbw_enabled": True,
            "resample_to_fsw_axis": True,
            "use_metadata_parameters": True,
            "impedance_ohm": 50.0,
            "calibration_db": 0.0,
        },
        "scope": {"analog_bandwidth_hz": 350e6},
        "output": {
            "directory": "output",
            "save_csv": True,
            "save_plot": True,
            "show_plot": True,
        },
    }
    path = tmp_path / "v01.json"
    path.write_text(json.dumps(old_config), encoding="utf-8")

    loaded = load_config(path)

    assert loaded.input.fsw_reference_file == ""
    assert loaded.comparison.enabled is True
    assert loaded.output.save_conversion_metadata is True
