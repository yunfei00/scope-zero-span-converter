from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import AppConfig, config_from_dict
from .templates import user_data_directory


@dataclass
class AppState:
    config: AppConfig
    # selected_tab 保留用于兼容旧 app_state.json；新版本优先使用 selected_tab_id。
    selected_tab: int = 0
    selected_tab_id: str = ""
    selected_template: str = ""


def state_path() -> Path:
    path = user_data_directory()
    path.mkdir(parents=True, exist_ok=True)
    return path / "app_state.json"


def load_state() -> AppState | None:
    path = state_path()
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        config_raw = raw.get("config", {})
        if not isinstance(config_raw, dict):
            return None
        return AppState(
            config=config_from_dict(config_raw),
            selected_tab=int(raw.get("selected_tab", 0)),
            selected_tab_id=str(raw.get("selected_tab_id", "")),
            selected_template=str(raw.get("selected_template", "")),
        )
    except Exception:
        return None


def save_state(state: AppState) -> Path:
    path = state_path()
    payload = {
        "schema_version": 2,
        "config": asdict(state.config),
        # 两者同时保存：ID 是正式字段，index 仅为旧版本回退兼容。
        "selected_tab_id": state.selected_tab_id,
        "selected_tab": state.selected_tab,
        "selected_template": state.selected_template,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
