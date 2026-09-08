from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

from scope_zero_span_converter.config import AppConfig
from scope_zero_span_converter.roi_worker import RoiConversionWorkerTask


def test_roi_worker_converts_region_without_qwidget_access(tmp_path):
    fs = 1e9
    t = np.arange(4000, dtype=float) / fs
    voltage = 0.2 * np.cos(2.0 * np.pi * 200e6 * t)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text("{}", encoding="utf-8")

    cfg = AppConfig()
    cfg.signal.center_frequency_hz = 200e6
    cfg.signal.rbw_hz = 10e6
    cfg.signal.vbw_hz = 10e6
    cfg.conversion.use_metadata_parameters = False
    cfg.scope.analog_bandwidth_hz = 350e6

    completed = []
    failures = []
    task = RoiConversionWorkerTask(
        request_id=23,
        time_s=t,
        voltage_v=voltage,
        metadata_path=metadata_path,
        config=cfg,
        origin_s=5e-6,
    )
    task.signals.finished.connect(completed.append)
    task.signals.failed.connect(lambda request_id, message: failures.append((request_id, message)))

    task.run()

    assert not failures
    assert len(completed) == 1
    payload = completed[0]
    assert payload.request_id == 23
    assert payload.origin_s == 5e-6
    assert len(payload.conversion.time_s) == len(t)
    assert payload.conversion.center_frequency_hz == 200e6
    assert payload.conversion.rbw_hz == 10e6
