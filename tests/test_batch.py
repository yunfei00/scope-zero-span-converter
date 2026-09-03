import json

import numpy as np
import pandas as pd

from scope_zero_span_converter.batch import discover_batch_jobs, run_batch
from scope_zero_span_converter.config import AppConfig


def _write_case(directory, *, good=True):
    directory.mkdir(parents=True, exist_ok=True)
    fs = 1e9
    duration = 4e-6
    t = np.arange(int(fs * duration)) / fs
    waveform = 0.2 * np.cos(2 * np.pi * 200e6 * t)
    pd.DataFrame({"time_s": t, "voltage_v": waveform}).to_csv(
        directory / "waveform.csv",
        index=False,
    )
    if good:
        (directory / "metadata.json").write_text("{}", encoding="utf-8")


def test_discover_and_run_batch(tmp_path):
    source = tmp_path / "source"
    _write_case(source / "case_a", good=True)
    _write_case(source / "case_b", good=True)
    _write_case(source / "missing_metadata", good=False)

    cfg = AppConfig()
    cfg.conversion.use_metadata_parameters = False
    cfg.comparison.enabled = False
    cfg.output.save_plot = False
    cfg.output.show_plot = False
    cfg.batch.source_directory = str(source)
    cfg.batch.output_directory = str(tmp_path / "batch_output")
    cfg.batch.recursive = True

    jobs = discover_batch_jobs(cfg)
    assert [job.name for job in jobs] == ["case_a", "case_b"]

    result = run_batch(cfg)
    assert result.jobs_found == 2
    assert result.succeeded == 2
    assert result.failed == 0
    assert result.summary_csv is not None and result.summary_csv.exists()
    assert result.summary_json is not None and result.summary_json.exists()

    for case in ("case_a", "case_b"):
        output = tmp_path / "batch_output" / case
        assert (output / "zero_span_from_scope.csv").exists()
        assert (output / "conversion_metadata.json").exists()

    summary = json.loads(result.summary_json.read_text(encoding="utf-8"))
    assert summary["jobs_found"] == 2
    assert summary["succeeded"] == 2
    assert summary["failed"] == 0


def test_batch_continues_after_failed_case(tmp_path):
    source = tmp_path / "source"
    _write_case(source / "good", good=True)
    _write_case(source / "bad", good=True)

    # 让 bad 的 waveform 失效，但保留 metadata，使它仍然被扫描成任务。
    pd.DataFrame({"time_s": [0.0, 1e-9], "voltage_v": [0.0, 0.0]}).to_csv(
        source / "bad" / "waveform.csv",
        index=False,
    )

    cfg = AppConfig()
    cfg.conversion.use_metadata_parameters = False
    cfg.comparison.enabled = False
    cfg.output.save_plot = False
    cfg.output.show_plot = False
    cfg.batch.source_directory = str(source)
    cfg.batch.output_directory = str(tmp_path / "batch_output")
    cfg.batch.continue_on_error = True

    result = run_batch(cfg)
    assert result.jobs_found == 2
    assert result.succeeded == 1
    assert result.failed == 1
    statuses = {item.name: item.status for item in result.items}
    assert statuses["good"] == "success"
    assert statuses["bad"] == "failed"
