from __future__ import annotations

import json

import numpy as np
import pandas as pd

from scope_zero_span_converter.batch import run_batch
from scope_zero_span_converter.config import AppConfig


def test_batch_summary_contains_waveform_quality_fields(tmp_path):
    source = tmp_path / "source" / "case_a"
    source.mkdir(parents=True)

    fs = 1e9
    t = np.arange(4000, dtype=float) / fs
    v = 0.2 * np.cos(2.0 * np.pi * 200e6 * t)
    pd.DataFrame({"time_s": t, "voltage_v": v}).to_csv(
        source / "waveform.csv",
        index=False,
    )
    (source / "metadata.json").write_text("{}", encoding="utf-8")

    cfg = AppConfig()
    cfg.conversion.use_metadata_parameters = False
    cfg.comparison.enabled = False
    cfg.output.save_plot = False
    cfg.output.show_plot = False
    cfg.batch.source_directory = str(tmp_path / "source")
    cfg.batch.output_directory = str(tmp_path / "batch_output")

    result = run_batch(cfg)
    assert result.succeeded == 1
    item = result.items[0]
    assert item.quality_status == "pass"
    assert item.dt_max_deviation_percent is not None
    assert item.max_gap_ratio is not None

    summary = json.loads(result.summary_json.read_text(encoding="utf-8"))
    payload = summary["items"][0]
    assert payload["quality_status"] == "pass"
    assert "dt_max_deviation_percent" in payload
    assert "max_gap_ratio" in payload

    csv_df = pd.read_csv(result.summary_csv)
    assert "quality_status" in csv_df.columns
    assert "dt_max_deviation_percent" in csv_df.columns
    assert "max_gap_ratio" in csv_df.columns
