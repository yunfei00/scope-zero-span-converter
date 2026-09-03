from __future__ import annotations

import re
from pathlib import Path

from .config import AppConfig, load_config, save_config


_TEMPLATE_NAME_RE = re.compile(r"^[\w\-\u4e00-\u9fff ]+$")


def user_data_directory() -> Path:
    return Path.home() / "ScopeZeroSpanConverter"


def template_directory() -> Path:
    path = user_data_directory() / "templates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_template_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("模板名称不能为空")
    if not _TEMPLATE_NAME_RE.match(name):
        raise ValueError("模板名称只能包含中文、字母、数字、空格、下划线和连字符")
    return name


def template_path(name: str) -> Path:
    return template_directory() / f"{sanitize_template_name(name)}.json"


def list_templates() -> list[str]:
    return sorted(path.stem for path in template_directory().glob("*.json"))


def save_template(name: str, config: AppConfig, *, overwrite: bool = True) -> Path:
    path = template_path(name)
    if path.exists() and not overwrite:
        raise FileExistsError(f"模板已存在：{name}")
    save_config(config, path)
    return path


def load_template(name: str) -> AppConfig:
    path = template_path(name)
    if not path.exists():
        raise FileNotFoundError(f"找不到模板：{name}")
    return load_config(path)


def delete_template(name: str) -> None:
    path = template_path(name)
    if not path.exists():
        raise FileNotFoundError(f"找不到模板：{name}")
    path.unlink()
