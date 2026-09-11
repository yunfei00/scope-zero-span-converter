from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from PIL import Image

from scope_zero_span_converter import __version__
from scope_zero_span_converter import product, runtime_paths
from scope_zero_span_converter.config import load_config

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("windows_metadata", ROOT / "packaging/windows_metadata.py")
build_metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_metadata)


@pytest.mark.parametrize("version,expected", [
    ("1.0.0", (1, 0, 0, 0)), ("0.8.0.dev0", (0, 8, 0, 0)),
    ("2.10.3.dev42", (2, 10, 3, 42)), ("65535.0.0", (65535, 0, 0, 0)),
])
def test_windows_version_tuple(version, expected):
    assert build_metadata.windows_version(version) == expected


@pytest.mark.parametrize("version", ["v1.0.0", "1.0", "1.0.0rc1", "-1.0.0", "65536.0.0", "1.0.0.dev65536"])
def test_windows_version_rejects_unsupported_values(version):
    with pytest.raises(ValueError):
        build_metadata.windows_version(version)


def test_product_and_installer_metadata_share_source(tmp_path):
    metadata = build_metadata.generate(tmp_path)
    assert metadata["version"] == __version__
    assert metadata["product_name"] == product.PRODUCT_NAME
    assert metadata["publisher"] == product.PUBLISHER
    assert metadata["app_id"] == product.INSTALLER_APP_ID
    assert metadata["executable"] == product.EXECUTABLE_NAME
    text = (tmp_path / "version-info.txt").read_text(encoding="utf-8")
    for field in ("FileDescription", "ProductName", "ProductVersion", "FileVersion", "CompanyName", "LegalCopyright", "OriginalFilename"):
        assert field in text
    assert __version__ in text
    assert __version__ in (tmp_path / "installer-defines.iss").read_text()


def test_resources_are_independent_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runtime_paths.resource_path("configs/default.json") == ROOT / "configs/default.json"
    load_config(runtime_paths.resource_path("configs/default.json")).validate()
    with pytest.raises(ValueError):
        runtime_paths.resource_path("../outside")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert runtime_paths.resource_path("assets/app.ico") == tmp_path / "assets/app.ico"


def test_icon_has_all_windows_sizes():
    with Image.open(ROOT / "assets/app.ico") as icon:
        assert {(size, size) for size in (16, 24, 32, 48, 64, 128, 256)} <= icon.ico.sizes()


def test_windows_user_data_migrates_without_overwriting(tmp_path, monkeypatch):
    monkeypatch.delenv("SCOPE_ZERO_SPAN_DATA_DIR", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    legacy = tmp_path / "home" / product.APPLICATION_ID
    (legacy / "templates").mkdir(parents=True)
    (legacy / "app_state.json").write_text('{"selected_tab": 2}')
    (legacy / "templates/customer.json").write_text('{"schema_version": 1}')
    destination = tmp_path / "local" / product.APPLICATION_ID
    destination.mkdir(parents=True)
    (destination / "app_state.json").write_text('{"selected_tab": 4}')
    assert runtime_paths.user_data_directory() == destination
    assert (destination / "app_state.json").read_text() == '{"selected_tab": 4}'
    assert (destination / "templates/customer.json").read_bytes() == (legacy / "templates/customer.json").read_bytes()
    assert (legacy / "app_state.json").is_file()
    (destination / "templates/customer.json").unlink()
    runtime_paths.user_data_directory()
    assert not (destination / "templates/customer.json").exists()


def test_data_override_and_packaged_outputs_are_writable(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOPE_ZERO_SPAN_DATA_DIR", str(tmp_path / "user-data"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert Path(runtime_paths.writable_output_path("output")) == tmp_path / "user-data/output"
    assert runtime_paths.writable_output_path(str(tmp_path / "chosen")) == str(tmp_path / "chosen")
    with pytest.raises(ValueError):
        runtime_paths.writable_output_path("../outside")
    monkeypatch.setattr(sys, "frozen", False)
    assert runtime_paths.writable_output_path("output") == "output"


def test_failed_legacy_copy_preserves_original_and_can_retry(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy"
    destination = tmp_path / "destination"
    legacy.mkdir()
    destination.mkdir()
    original = legacy / "app_state.json"
    original.write_bytes(b'{"config": {"schema_version": 1}}')
    copy = runtime_paths.shutil.copyfileobj

    def interrupted_copy(source, target):
        target.write(b"partial")
        raise OSError("simulated disk failure")

    monkeypatch.setattr(runtime_paths.shutil, "copyfileobj", interrupted_copy)
    with pytest.raises(OSError):
        runtime_paths._migrate_legacy_data(destination, legacy)
    assert original.read_bytes() == b'{"config": {"schema_version": 1}}'
    assert not (destination / "app_state.json").exists()
    assert not (destination / ".legacy-migration-complete").exists()
    monkeypatch.setattr(runtime_paths.shutil, "copyfileobj", copy)
    runtime_paths._migrate_legacy_data(destination, legacy)
    assert (destination / "app_state.json").read_bytes() == original.read_bytes()


def test_real_entrypoint_smoke_creates_five_tabs_and_preserves_state(tmp_path):
    environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=str(ROOT / "src"), SCOPE_ZERO_SPAN_DATA_DIR=str(tmp_path / "user"))
    (tmp_path / "user").mkdir()
    state = tmp_path / "user/app_state.json"
    state.write_text("customer-state-must-not-be-read-or-overwritten")
    report = tmp_path / "smoke.json"
    result = subprocess.run([sys.executable, str(ROOT / "run_gui.py"), "--smoke-test", "--smoke-report", str(report)], env=environment, cwd=tmp_path, timeout=90, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["version"] == __version__
    assert payload["platform"] == "offscreen"
    assert payload["tabs"] == ["waveform_research", "dcm_generator", "dcm_extractor", "dcm_analysis", "batch_conversion"]
    assert state.read_text() == "customer-state-must-not-be-read-or-overwritten"


def test_release_requires_successful_windows_build_and_tag_push():
    workflow = (ROOT / ".github/workflows/release.yml").read_text()
    assert "workflow_dispatch:" in workflow
    assert "needs: build-windows" in workflow
    assert "if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')" in workflow
    assert "continue-on-error" not in workflow
    assert "packaging/ScopeZeroSpanConverter.spec" in workflow
    installer = (ROOT / "packaging/windows/ScopeZeroSpanConverter.iss").read_text()
    assert "AppId={{#StableAppId}" in installer
    assert "Flags: unchecked" in installer
    assert not any(line.strip() == "[UninstallDelete]" for line in installer.splitlines())
