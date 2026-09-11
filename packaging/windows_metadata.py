"""Generate all Windows build metadata from the product and version modules."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import runpy

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "src/scope_zero_span_converter/_version.py"


def windows_version(version: str) -> tuple[int, int, int, int]:
    """X.Y.Z[.devN] -> X.Y.Z.N (release W=0); text retains .devN."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:\.dev(\d+))?", version)
    if match is None:
        raise ValueError(f"Unsupported Windows release version: {version}")
    parts = tuple(int(value or 0) for value in match.groups())
    if any(value > 65535 for value in parts):
        raise ValueError("Windows version components must fit an unsigned 16-bit integer")
    return parts


def product_metadata() -> dict:
    identity = runpy.run_path(str(ROOT / "src/scope_zero_span_converter/product.py"))
    version = runpy.run_path(str(VERSION_FILE))["__version__"]
    return {
        "product_name": identity["PRODUCT_NAME"],
        "application_id": identity["APPLICATION_ID"],
        "executable": identity["EXECUTABLE_NAME"],
        "publisher": identity["PUBLISHER"],
        "copyright": identity["COPYRIGHT"],
        "app_id": identity["INSTALLER_APP_ID"],
        "project_url": identity["PROJECT_URL"],
        "version": version,
        "windows_version": windows_version(version),
        "installer_filename": f'{identity["APPLICATION_ID"]}-Setup-{version}.exe',
        "portable_filename": f'{identity["APPLICATION_ID"]}-v{version}-Windows-x64.zip',
    }


def version_resource(metadata: dict) -> str:
    version = metadata["version"]
    fields = {
        "FileDescription": metadata["product_name"],
        "ProductName": metadata["product_name"],
        "ProductVersion": version,
        "FileVersion": version,
        "CompanyName": metadata["publisher"],
        "LegalCopyright": metadata["copyright"],
        "OriginalFilename": metadata["executable"],
    }
    strings = ",\n".join(f"StringStruct({key!r}, {value!r})" for key, value in fields.items())
    numeric = tuple(metadata["windows_version"])
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={numeric!r}, prodvers={numeric!r},
    mask=0x3f, flags={2 if '.dev' in version else 0}, OS=0x40004,
    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [{strings}])]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])])])
"""


def generate(destination: Path) -> dict:
    metadata = product_metadata()
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (destination / "version-info.txt").write_text(version_resource(metadata), encoding="utf-8")
    defines = {
        "ProductName": metadata["product_name"], "AppName": metadata["application_id"],
        "AppVersion": metadata["version"], "AppPublisher": metadata["publisher"],
        "AppCopyright": metadata["copyright"], "AppExe": metadata["executable"],
        "StableAppId": metadata["app_id"], "ProjectUrl": metadata["project_url"],
        "NumericVersion": ".".join(map(str, metadata["windows_version"])),
        "SetupBaseName": Path(metadata["installer_filename"]).stem,
    }
    (destination / "installer-defines.iss").write_text(
        "\n".join(f'#define {key} "{value}"' for key, value in defines.items()) + "\n", encoding="utf-8"
    )
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag")
    args = parser.parse_args()
    if args.tag is not None:
        if not re.fullmatch(r"v\d+\.\d+\.\d+", args.tag):
            parser.error("Release tags must be vX.Y.Z")
        windows_version(args.tag[1:])
        VERSION_FILE.write_text(f'"""Version injected by the tag build."""\n\n__version__ = "{args.tag[1:]}"\n', encoding="utf-8")
    print(json.dumps(generate(ROOT / "build/packaging"), indent=2))
