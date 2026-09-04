from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .dcm_sw_generator import (
    DcmSwWaveform,
    event_times,
    load_dcm_sw_parameters,
)


TRUTH_COLUMNS = (
    "time_s",
    "voltage_v",
    "ideal_voltage_v",
    "spike_component_v",
    "discontinuous_component_v",
    "noise_component_v",
)


def parameter_sidecar_for(csv_path: str | Path) -> Path:
    path = Path(csv_path)
    return path.with_name(f"{path.stem}_parameters.json")


def load_saved_dcm_sw_waveform(
    csv_path: str | Path,
    *,
    parameters_path: str | Path | None = None,
) -> tuple[DcmSwWaveform, Path]:
    """加载生成器保存过的 DCM SW CSV，并恢复当时的真值参数。

    CSV 本身作为历史波形真值原样恢复；不会根据当前生成算法重新生成。
    默认自动寻找 ``<csv_stem>_parameters.json``。如果参数文件被移动，可显式传入。
    """

    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"找不到 DCM SW 波形 CSV：{csv_path}")

    if parameters_path is None:
        parameters_path = parameter_sidecar_for(csv_path)
    parameters_path = Path(parameters_path)
    if not parameters_path.exists():
        raise FileNotFoundError(
            "找不到该波形对应的真值参数 JSON："
            f"{parameters_path.name}。请选择生成波形时同时保存的参数文件。"
        )

    parameters = load_dcm_sw_parameters(parameters_path)

    frame = pd.read_csv(csv_path)
    missing = [column for column in TRUTH_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(
            "该 CSV 不是完整的 DCM SW 真值波形文件，缺少列："
            + ", ".join(missing)
            + "。普通 time_s,voltage_v CSV 请在“波形研究”页面加载。"
        )

    arrays = {
        column: frame[column].to_numpy(dtype=float)
        for column in TRUTH_COLUMNS
    }
    t = arrays["time_s"]
    if len(t) < 32:
        raise ValueError("DCM SW 波形点数少于 32")
    if not all(len(values) == len(t) for values in arrays.values()):
        raise ValueError("DCM SW CSV 各真值列长度不一致")
    if not all(np.all(np.isfinite(values)) for values in arrays.values()):
        raise ValueError("DCM SW CSV 包含 NaN 或 Inf")

    dt = np.diff(t)
    if not np.all(dt > 0):
        raise ValueError("DCM SW CSV 的 time_s 必须严格递增")
    sample_rate_hz = 1.0 / float(np.median(dt))

    expected_fs = float(parameters.sample_rate_hz)
    relative_error = abs(sample_rate_hz - expected_fs) / max(abs(expected_fs), 1.0)
    if relative_error > 1e-5:
        raise ValueError(
            "CSV 时间轴采样率与参数 JSON 不一致："
            f"CSV≈{sample_rate_hz:g} Hz，JSON={expected_fs:g} Hz"
        )

    waveform = DcmSwWaveform(
        time_s=t,
        voltage_v=arrays["voltage_v"],
        ideal_voltage_v=arrays["ideal_voltage_v"],
        spike_component_v=arrays["spike_component_v"],
        discontinuous_component_v=arrays["discontinuous_component_v"],
        noise_component_v=arrays["noise_component_v"],
        sample_rate_hz=sample_rate_hz,
        parameters=parameters,
        events=event_times(parameters),
    )
    return waveform, parameters_path
