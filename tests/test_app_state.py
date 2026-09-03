from scope_zero_span_converter.app_state import AppState, load_state, save_state
from scope_zero_span_converter.config import AppConfig
import scope_zero_span_converter.app_state as app_state


def test_app_state_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(
        app_state,
        "state_path",
        lambda: tmp_path / "app_state.json",
    )

    config = AppConfig()
    config.input.waveform_file = "demo/waveform.csv"
    config.batch.source_directory = "batch-data"
    config.signal.center_frequency_hz = 200e6

    save_state(
        AppState(
            config=config,
            selected_tab=1,
            selected_template="客户模板",
        )
    )

    loaded = load_state()
    assert loaded is not None
    assert loaded.config.input.waveform_file == "demo/waveform.csv"
    assert loaded.config.batch.source_directory == "batch-data"
    assert loaded.selected_tab == 1
    assert loaded.selected_template == "客户模板"
