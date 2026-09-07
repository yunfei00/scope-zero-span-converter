from __future__ import annotations

import json
import logging
import zipfile
from logging.handlers import RotatingFileHandler

import pytest

import scope_zero_span_converter.diagnostics as diagnostics
import scope_zero_span_converter.logging_utils as logging_utils
from scope_zero_span_converter import __version__


def test_configured_file_logger_uses_rotation_policy():
    logger = logging_utils.configure_logging()
    rotating = [handler for handler in logger.handlers if isinstance(handler, RotatingFileHandler)]

    assert rotating
    handler = rotating[0]
    assert handler.maxBytes == 10 * 1024 * 1024
    assert handler.backupCount == 5


def test_diagnostic_bundle_contains_runtime_and_logs_but_no_customer_data(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "scope-zero-span-converter.log").write_text(
        "2026-09-07 | INFO | demo\n",
        encoding="utf-8",
    )
    (log_dir / "scope-zero-span-converter.log.1").write_text(
        "older log\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(diagnostics, "log_directory", lambda: log_dir)

    output = diagnostics.export_diagnostic_bundle(tmp_path / "support_bundle")

    assert output.suffix == ".zip"
    assert output.exists()
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert "diagnostic.json" in names
        assert "logs/scope-zero-span-converter.log" in names
        assert "logs/scope-zero-span-converter.log.1" in names

        payload = json.loads(archive.read("diagnostic.json").decode("utf-8"))
        assert payload["software"]["version"] == __version__
        assert payload["privacy"]["waveform_data_included"] is False
        assert payload["privacy"]["customer_config_included"] is False
        assert "runtime" in payload


def test_diagnostic_snapshot_does_not_embed_customer_waveform_or_config_keys():
    payload = diagnostics.diagnostic_snapshot()
    serialized = json.dumps(payload, ensure_ascii=False).lower()

    assert '"waveform_file"' not in serialized
    assert '"metadata_file"' not in serialized
    assert '"config_snapshot"' not in serialized
