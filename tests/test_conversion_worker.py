from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd

from scope_zero_span_converter.config import AppConfig
from scope_zero_span_converter.conversion_worker import FullConversionWorkerTask


def test_full_conversion_worker_saves_csv_png_and_metadata_without_qwidget(tmp_path):
    fs = 1e9
    t = np.arange(4000, dtype=float) / fs
    voltage = 0.2 * np.cos(2.0 * np.pi * 200e6 * t)
    waveform_path = tmp_path / "waveform.csv"
    metadata_path = tmp_path / "metadata.json"
    pd.DataFrame({"time_s": t, "voltage_v": voltage}).to_csv(
        waveform_path,
        index=False,
    )
    metadata_path.write_text("{}", encoding="utf-8")

    cfg = AppConfig()
    cfg.input.waveform_file = str(waveform_path)
    cfg.input.metadata_file = str(metadata_path)
    cfg.signal.center_frequency_hz = 200e6
    cfg.signal.rbw_hz = 10e6
    cfg.signal.vbw_hz = 10e6
    cfg.conversion.use_metadata_parameters = False
    cfg.comparison.enabled = False
    cfg.scope.analog_bandwidth_hz = 350e6
    cfg.output.directory = str(tmp_path / "output")
    cfg.output.save_csv = True
    cfg.output.save_plot = True
    cfg.output.save_conversion_metadata = True
    cfg.output.show_plot = True  # Worker must not open an interactive Qt plot.

    completed = []
    failures = []
    task = FullConversionWorkerTask(cfg)
    task.signals.finished.connect(completed.append)
    task.signals.failed.connect(failures.append)

    task.run()

    assert not failures
    assert len(completed) == 1
    payload = completed[0]
    result = payload.conversion
    assert result.output_csv is not None and result.output_csv.exists()
    assert result.output_plot is not None and result.output_plot.exists()
    assert result.output_metadata is not None and result.output_metadata.exists()
    assert payload.config.output.show_plot is True

    metadata = json.loads(result.output_metadata.read_text(encoding="utf-8"))
    assert metadata["config_snapshot"]["output"]["show_plot"] is True
    assert metadata["effective_parameters"]["center_frequency_hz"] == 200e6
