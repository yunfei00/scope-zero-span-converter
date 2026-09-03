from pathlib import Path

from scope_zero_span_converter.config import AppConfig
import scope_zero_span_converter.templates as templates


def test_template_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(
        templates,
        "user_data_directory",
        lambda: tmp_path / "user-data",
    )

    config = AppConfig()
    config.signal.center_frequency_hz = 210e6
    config.signal.rbw_hz = 5e6
    config.conversion.calibration_db = -1.25

    path = templates.save_template("客户 210M", config)
    assert path.exists()
    assert templates.list_templates() == ["客户 210M"]

    loaded = templates.load_template("客户 210M")
    assert loaded.signal.center_frequency_hz == 210e6
    assert loaded.signal.rbw_hz == 5e6
    assert loaded.conversion.calibration_db == -1.25

    templates.delete_template("客户 210M")
    assert templates.list_templates() == []
