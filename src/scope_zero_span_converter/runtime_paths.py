"""Read-only bundled resources and writable per-user application data."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from .product import APPLICATION_ID


def resource_path(relative: str) -> Path:
    """Resolve a repository resource, independent of the working directory."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Resource path must stay inside the resource directory")
    return path


def _migrate_legacy_data(destination: Path, legacy: Path) -> None:
    """Copy once, preserving originals and never overwriting newer data."""
    marker = destination / ".legacy-migration-complete"
    if destination == legacy or marker.exists() or not legacy.is_dir():
        return
    sources = [legacy / "app_state.json"]
    for folder in ("templates", "logs"):
        sources.extend((legacy / folder).glob("*"))
    for source in sources:
        if not source.is_file() or source.is_symlink():
            continue
        target = destination / source.relative_to(legacy)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with source.open("rb") as input_file:
                with target.open("xb") as output:
                    try:
                        shutil.copyfileobj(input_file, output)
                    except OSError:
                        output.close()
                        target.unlink()
                        raise
        except FileExistsError:
            pass
    marker.touch()


def user_data_directory() -> Path:
    # Explicit override also isolates automated smoke tests from real user data.
    override = os.environ.get("SCOPE_ZERO_SPAN_DATA_DIR")
    legacy = Path.home() / APPLICATION_ID
    if override:
        path = Path(override).expanduser().resolve()
    elif sys.platform == "win32":
        path = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APPLICATION_ID
    else:
        path = legacy
    path.mkdir(parents=True, exist_ok=True)
    if not override:
        _migrate_legacy_data(path, legacy)
    return path


def writable_output_path(value: str) -> str:
    """Anchor relative packaged outputs in user data, never Program Files."""
    path = Path(value)
    if getattr(sys, "frozen", False) and not path.is_absolute():
        root = user_data_directory()
        path = (root / path).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("Relative output must stay inside the user data directory")
    return str(path)
