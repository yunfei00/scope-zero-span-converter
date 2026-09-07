from __future__ import annotations

import json
import platform
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .logging_utils import log_directory


def diagnostic_snapshot() -> dict:
    """Return non-customer-data runtime information for support diagnosis."""

    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "software": {
            "name": "scope-zero-span-converter",
            "version": __version__,
        },
        "runtime": {
            "python_version": sys.version,
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "privacy": {
            "waveform_data_included": False,
            "customer_config_included": False,
            "note": "诊断包默认只包含运行环境信息和应用日志，不包含客户波形/参数文件。",
        },
    }


def export_diagnostic_bundle(output_path: str | Path) -> Path:
    """Export runtime metadata and available rotating logs into one ZIP."""

    output_path = Path(output_path)
    if output_path.suffix.lower() != ".zip":
        output_path = output_path.with_suffix(".zip")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    snapshot = diagnostic_snapshot()
    logs = sorted(log_directory().glob("scope-zero-span-converter.log*"))

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "diagnostic.json",
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        )
        for log_path in logs:
            if log_path.is_file():
                archive.write(log_path, arcname=f"logs/{log_path.name}")

    return output_path
