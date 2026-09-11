"""Collect actual wheel license files and metadata into the distributable."""

from __future__ import annotations

from importlib import metadata
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sys
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def collect(destination: Path) -> list[dict]:
    destination.mkdir(parents=True, exist_ok=True)
    for source in json.loads((ROOT / "packaging/license-sources.json").read_text(encoding="utf-8")):
        with urlopen(source["url"], timeout=60) as response:
            content = response.read()
        if hashlib.sha256(content).hexdigest() != source["sha256"]:
            raise RuntimeError(f'License checksum mismatch: {source["filename"]}')
        (destination / source["filename"]).write_bytes(content)
    inventory = []
    for distribution in sorted(metadata.distributions(), key=lambda item: item.metadata["Name"].lower()):
        name = distribution.metadata["Name"]
        if name.lower() == "scope-zero-span-converter":
            continue
        license_paths = []
        for relative in distribution.files or []:
            parts = [part.lower() for part in relative.parts]
            if not any(part.startswith(("license", "licence", "copying", "notice")) for part in parts):
                continue
            source = Path(distribution.locate_file(relative))
            if source.is_file():
                safe_parts = [part for part in relative.parts if part not in ("..", ".")]
                target = destination / name / Path(*safe_parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                license_paths.append(target.relative_to(destination).as_posix())
        inventory.append({
            "name": name, "version": distribution.version,
            "license_expression": distribution.metadata.get("License-Expression"),
            "license": distribution.metadata.get("License"),
            "classifiers": [value for value in distribution.metadata.get_all("Classifier", []) if value.startswith("License ::")],
            "project_urls": distribution.metadata.get_all("Project-URL", []),
            "license_files": license_paths,
        })
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.exists():
        python_license = Path(sys.base_prefix) / "LICENSE"
    if not python_license.is_file():
        raise RuntimeError("CPython license file missing from build runtime")
    shutil.copyfile(python_license, destination / "PYTHON-LICENSE.txt")
    (destination / "dependency-inventory.json").write_text(json.dumps({
        "python": platform.python_version(), "packages": inventory,
        "note": "Build-environment inventory; not every installed optional Qt module is included in the EXE.",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    required = {"numpy", "pandas", "matplotlib", "pyside6_essentials", "pyinstaller"}
    missing = [item["name"] for item in inventory if item["name"].lower().replace("-", "_") in required and not item["license_files"]]
    if missing:
        raise RuntimeError(f"Required license files missing: {missing}")
    return inventory


if __name__ == "__main__":
    collect(ROOT / "build/packaging/notices")
