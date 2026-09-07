import json

from scope_zero_span_converter.app_state import AppState, load_state, save_state
from scope_zero_span_converter.config import AppConfig
import scope_zero_span_converter.app_state as app_state


def test_app_state_roundtrip_uses_stable_tab_id_and_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(
        app_state,
        "state_path",
        lambda: tmp_path / "app_state.json",
    )

    config = AppConfig()
    config.input.waveform_file = "demo/waveform.csv"
    config.batch.source_directory = "batch-data"
    config.signal.center_frequency_hz = 200e6

    workspace = {
        "dcm_analysis": {
            "schema_version": 1,
            "markers": {"frequency_hz": 60e6},
        }
    }
    save_state(
        AppState(
            config=config,
            selected_tab=3,
            selected_tab_id="dcm_analysis",
            selected_template="客户模板",
            workspace=workspace,
        )
    )

    loaded = load_state()
    assert loaded is not None
    assert loaded.config.input.waveform_file == "demo/waveform.csv"
    assert loaded.config.batch.source_directory == "batch-data"
    assert loaded.selected_tab == 3
    assert loaded.selected_tab_id == "dcm_analysis"
    assert loaded.selected_template == "客户模板"
    assert loaded.workspace == workspace

    raw = json.loads((tmp_path / "app_state.json").read_text(encoding="utf-8"))
    assert raw["schema_version"] == 3
    assert raw["selected_tab_id"] == "dcm_analysis"
    assert raw["workspace"]["dcm_analysis"]["markers"]["frequency_hz"] == 60e6


def test_app_state_loads_legacy_numeric_tab_index(tmp_path, monkeypatch):
    path = tmp_path / "app_state.json"
    monkeypatch.setattr(app_state, "state_path", lambda: path)

    config = AppConfig()
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "config": {
                    "schema_version": config.schema_version,
                },
                "selected_tab": 2,
                "selected_template": "",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    loaded = load_state()
    assert loaded is not None
    assert loaded.selected_tab == 2
    assert loaded.selected_tab_id == ""
    assert loaded.workspace == {}


def test_app_state_ignores_invalid_workspace_shape(tmp_path, monkeypatch):
    path = tmp_path / "app_state.json"
    monkeypatch.setattr(app_state, "state_path", lambda: path)

    path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "config": {"schema_version": AppConfig().schema_version},
                "workspace": ["invalid"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    loaded = load_state()
    assert loaded is not None
    assert loaded.workspace == {}
