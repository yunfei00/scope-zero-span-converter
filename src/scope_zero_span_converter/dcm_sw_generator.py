from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd


MAX_POINTS = 5_000_000
MODEL_NAME = "single_event_dcm_sw_v2_signed_spikes"
LEGACY_MODEL_NAME = "single_event_dcm_sw_v1"


@dataclass
class DcmSwParameters:
    """单个 DCM 开关事件的可重复合成参数。

    时间定义：
    - switching_start_s: 上升沿开始时间。
    - on_time_s: 上升沿结束后的高电平稳定保持时间。
    - freewheel_time_s: 下降沿结束后的续流低电平稳定保持时间。
    - rise_time_s / fall_time_s 允许为 0；0 表示理想瞬时阶跃。
    - DCM 断续谐振从续流阶段结束后开始，并持续衰减到显示窗口结束。

    尖峰幅度使用“有符号电压偏移量”：
    - rise_spike_amplitude_v > 0 表示向上尖峰，< 0 表示向下尖峰；
    - fall_spike_amplitude_v > 0 表示向上尖峰，< 0 表示向下尖峰。
    默认上升沿为 +3 V、下降沿为 -4 V。
    两者使用同一组寄生振荡频率和指数衰减速率。

    noise_rms_v 表示高斯底噪的 RMS（标准差）。
    """

    baseline_voltage_v: float = 0.0
    on_high_voltage_v: float = 12.0
    freewheel_low_voltage_v: float = 1.0

    total_duration_s: float = 20e-6
    switching_start_s: float = 2e-6
    on_time_s: float = 3e-6
    freewheel_time_s: float = 2.5e-6
    rise_time_s: float = 40e-9
    fall_time_s: float = 50e-9

    rise_spike_amplitude_v: float = 3.0
    fall_spike_amplitude_v: float = -4.0
    spike_ringing_frequency_hz: float = 60e6
    spike_decay_rate_per_s: float = 8e6

    discontinuous_initial_amplitude_v: float = 2.5
    discontinuous_resonance_frequency_hz: float = 5e6
    discontinuous_decay_rate_per_s: float = 0.8e6

    noise_rms_v: float = 0.02
    sample_rate_hz: float = 2e9
    random_seed: int = 12345

    def validate(self) -> None:
        if self.total_duration_s <= 0:
            raise ValueError("总显示时长必须 > 0")
        if self.switching_start_s < 0:
            raise ValueError("开关起始时间不能 < 0")
        for name, value in (
            ("导通时间", self.on_time_s),
            ("续流时间", self.freewheel_time_s),
            ("上升沿时间", self.rise_time_s),
            ("下降沿时间", self.fall_time_s),
        ):
            if value < 0:
                raise ValueError(f"{name}不能 < 0")
        if self.sample_rate_hz <= 0:
            raise ValueError("采样率必须 > 0")
        if self.noise_rms_v < 0:
            raise ValueError("示波器底噪 RMS 不能 < 0")
        if self.spike_ringing_frequency_hz < 0:
            raise ValueError("尖峰寄生振荡频率不能 < 0")
        if self.discontinuous_resonance_frequency_hz < 0:
            raise ValueError("断续谐振频率不能 < 0")
        if self.spike_decay_rate_per_s < 0:
            raise ValueError("尖峰衰减速率不能 < 0")
        if self.discontinuous_decay_rate_per_s < 0:
            raise ValueError("断续谐振衰减速率不能 < 0")

        event_end = (
            self.switching_start_s
            + self.rise_time_s
            + self.on_time_s
            + self.fall_time_s
            + self.freewheel_time_s
        )
        if event_end >= self.total_duration_s:
            raise ValueError(
                "总显示时长不足：必须覆盖开关起始 + 上升沿 + 导通 + 下降沿 + 续流，"
                f"当前事件结束于 {event_end:g} s"
            )

        highest_frequency = max(
            self.spike_ringing_frequency_hz,
            self.discontinuous_resonance_frequency_hz,
        )
        if highest_frequency > 0 and highest_frequency >= self.sample_rate_hz / 2.0:
            raise ValueError(
                "采样率不足，会导致合成振铃混叠："
                f"最高振铃频率={highest_frequency:g} Hz, "
                f"Nyquist={self.sample_rate_hz/2:g} Hz"
            )

        points = int(np.floor(self.total_duration_s * self.sample_rate_hz)) + 1
        if points < 32:
            raise ValueError("总点数少于 32，请提高采样率或总显示时长")
        if points > MAX_POINTS:
            raise ValueError(
                f"预计生成 {points} 点，超过当前 GUI 安全上限 {MAX_POINTS} 点；"
                "请降低采样率或缩短总显示时长"
            )


@dataclass(frozen=True)
class DcmSwEventTimes:
    rise_start_s: float
    rise_end_s: float
    high_end_s: float
    fall_end_s: float
    freewheel_end_s: float


@dataclass(frozen=True)
class DcmSwDeterministicComponents:
    """DCM 正向模型的确定性分量。

    生成器和参数提取页的人工重建必须共同使用这一结果，避免维护两套模型。
    不包含随机噪声；deterministic_voltage_v 即当前模型可解释的完整波形。
    """

    ideal_voltage_v: np.ndarray
    spike_component_v: np.ndarray
    discontinuous_component_v: np.ndarray

    @property
    def deterministic_voltage_v(self) -> np.ndarray:
        return self.ideal_voltage_v + self.spike_component_v + self.discontinuous_component_v


@dataclass
class DcmSwWaveform:
    time_s: np.ndarray
    voltage_v: np.ndarray
    ideal_voltage_v: np.ndarray
    spike_component_v: np.ndarray
    discontinuous_component_v: np.ndarray
    noise_component_v: np.ndarray
    sample_rate_hz: float
    parameters: DcmSwParameters
    events: DcmSwEventTimes

    @property
    def points(self) -> int:
        return len(self.time_s)


def event_times(parameters: DcmSwParameters) -> DcmSwEventTimes:
    p = parameters
    rise_start = p.switching_start_s
    rise_end = rise_start + p.rise_time_s
    high_end = rise_end + p.on_time_s
    fall_end = high_end + p.fall_time_s
    freewheel_end = fall_end + p.freewheel_time_s
    return DcmSwEventTimes(
        rise_start_s=rise_start,
        rise_end_s=rise_end,
        high_end_s=high_end,
        fall_end_s=fall_end,
        freewheel_end_s=freewheel_end,
    )


def _half_cosine_transition(
    time_s: np.ndarray,
    start_s: float,
    duration_s: float,
    start_v: float,
    end_v: float,
) -> np.ndarray:
    if duration_s <= 0:
        return np.where(time_s >= start_s, end_v, start_v)
    u = np.clip((time_s - start_s) / duration_s, 0.0, 1.0)
    smooth = 0.5 - 0.5 * np.cos(np.pi * u)
    return start_v + (end_v - start_v) * smooth


def _damped_cosine(
    time_s: np.ndarray,
    start_s: float,
    amplitude_v: float,
    frequency_hz: float,
    decay_rate_per_s: float,
) -> np.ndarray:
    dt = time_s - start_s
    active = dt >= 0
    out = np.zeros_like(time_s, dtype=float)
    if not np.any(active) or amplitude_v == 0:
        return out
    local_t = dt[active]
    oscillation = np.cos(2.0 * np.pi * frequency_hz * local_t) if frequency_hz else 1.0
    out[active] = amplitude_v * np.exp(-decay_rate_per_s * local_t) * oscillation
    return out


def evaluate_dcm_sw_deterministic_components(
    time_s: np.ndarray,
    parameters: DcmSwParameters,
) -> DcmSwDeterministicComponents:
    """在给定时间轴上评估生成器唯一的确定性 DCM SW 正向模型。

    该函数不加入随机噪声，也不重新采样时间轴。参数提取页的人工校正使用它，
    因而“生成器参数 = 提取器可调参数 = 实际重建模型”。
    """

    t = np.asarray(time_s, dtype=float)
    if t.ndim != 1 or len(t) == 0:
        raise ValueError("time_s 必须是一维非空数组")
    if not np.all(np.isfinite(t)):
        raise ValueError("time_s 包含 NaN 或 Inf")

    p = parameters
    events = event_times(p)
    ideal = np.full(len(t), p.baseline_voltage_v, dtype=float)

    rise_mask = (t >= events.rise_start_s) & (t < events.rise_end_s)
    if np.any(rise_mask):
        ideal[rise_mask] = _half_cosine_transition(
            t[rise_mask],
            events.rise_start_s,
            p.rise_time_s,
            p.baseline_voltage_v,
            p.on_high_voltage_v,
        )

    high_mask = (t >= events.rise_end_s) & (t < events.high_end_s)
    ideal[high_mask] = p.on_high_voltage_v

    fall_mask = (t >= events.high_end_s) & (t < events.fall_end_s)
    if np.any(fall_mask):
        ideal[fall_mask] = _half_cosine_transition(
            t[fall_mask],
            events.high_end_s,
            p.fall_time_s,
            p.on_high_voltage_v,
            p.freewheel_low_voltage_v,
        )

    freewheel_mask = (t >= events.fall_end_s) & (t < events.freewheel_end_s)
    ideal[freewheel_mask] = p.freewheel_low_voltage_v
    ideal[t >= events.freewheel_end_s] = p.baseline_voltage_v

    rise_spike = _damped_cosine(
        t,
        events.rise_end_s,
        p.rise_spike_amplitude_v,
        p.spike_ringing_frequency_hz,
        p.spike_decay_rate_per_s,
    )
    fall_spike = _damped_cosine(
        t,
        events.fall_end_s,
        p.fall_spike_amplitude_v,
        p.spike_ringing_frequency_hz,
        p.spike_decay_rate_per_s,
    )
    spike_component = rise_spike + fall_spike

    discontinuous_component = _damped_cosine(
        t,
        events.freewheel_end_s,
        p.discontinuous_initial_amplitude_v,
        p.discontinuous_resonance_frequency_hz,
        p.discontinuous_decay_rate_per_s,
    )

    return DcmSwDeterministicComponents(
        ideal_voltage_v=ideal,
        spike_component_v=spike_component,
        discontinuous_component_v=discontinuous_component,
    )


def generate_dcm_sw_waveform(parameters: DcmSwParameters) -> DcmSwWaveform:
    """生成一个已知参数、可重复的单事件 DCM SW 合成波形。"""

    parameters.validate()
    p = parameters
    events = event_times(p)

    points = int(np.floor(p.total_duration_s * p.sample_rate_hz)) + 1
    t = np.arange(points, dtype=float) / p.sample_rate_hz
    components = evaluate_dcm_sw_deterministic_components(t, p)

    rng = np.random.default_rng(int(p.random_seed))
    noise_component = rng.normal(0.0, p.noise_rms_v, size=points)
    voltage = components.deterministic_voltage_v + noise_component

    return DcmSwWaveform(
        time_s=t,
        voltage_v=voltage,
        ideal_voltage_v=components.ideal_voltage_v,
        spike_component_v=components.spike_component_v,
        discontinuous_component_v=components.discontinuous_component_v,
        noise_component_v=noise_component,
        sample_rate_hz=p.sample_rate_hz,
        parameters=p,
        events=events,
    )


def parameters_to_dict(parameters: DcmSwParameters) -> dict:
    return {"schema_version": 1, "model": MODEL_NAME, "parameters": asdict(parameters)}


def _extract_parameter_payload(raw: dict) -> tuple[dict, dict]:
    """兼容生成器原生 JSON 与 DCM 参数提取页导出的分析 JSON。"""

    if "current_generator_parameters" in raw:
        params = raw.get("current_generator_parameters")
        if not isinstance(params, dict):
            raise ValueError("参数提取结果中 current_generator_parameters 必须是对象")
        return params, {"model": raw.get("source_model", MODEL_NAME)}

    current_fit = raw.get("current_generator_fit")
    if isinstance(current_fit, dict) and isinstance(current_fit.get("parameters"), dict):
        return current_fit["parameters"], {"model": raw.get("source_model", MODEL_NAME)}

    params = raw.get("parameters", raw)
    if not isinstance(params, dict):
        raise ValueError("parameters 必须是对象")
    return params, raw


def parameters_from_dict(raw: dict) -> DcmSwParameters:
    if not isinstance(raw, dict):
        raise ValueError("DCM SW 参数 JSON 根节点必须是对象")
    schema_version = int(raw.get("schema_version", 1))
    if schema_version != 1:
        raise ValueError(f"不支持的 DCM SW 参数 schema_version: {schema_version}")

    params_raw, metadata = _extract_parameter_payload(raw)
    params_raw = dict(params_raw)

    if metadata.get("model") == LEGACY_MODEL_NAME and "fall_spike_amplitude_v" in params_raw:
        params_raw["fall_spike_amplitude_v"] = -abs(float(params_raw["fall_spike_amplitude_v"]))

    allowed = set(DcmSwParameters.__dataclass_fields__)
    unexpected = sorted(set(params_raw) - allowed)
    if unexpected:
        raise ValueError(
            "参数 JSON 包含当前 DCM SW 模型不支持的字段：" + ", ".join(unexpected)
        )

    parameters = DcmSwParameters(**params_raw)
    parameters.validate()
    return parameters


def load_dcm_sw_parameters(path: str | Path) -> DcmSwParameters:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return parameters_from_dict(raw)


def save_dcm_sw_parameters(parameters: DcmSwParameters, path: str | Path) -> Path:
    parameters.validate()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(parameters_to_dict(parameters), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def save_dcm_sw_waveform(
    waveform: DcmSwWaveform,
    csv_path: str | Path,
    *,
    save_parameters_json: bool = True,
) -> tuple[Path, Path | None]:
    """保存最终波形以及每个已知组成分量，便于后续提取算法做真值对照。"""

    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "time_s": waveform.time_s,
            "voltage_v": waveform.voltage_v,
            "ideal_voltage_v": waveform.ideal_voltage_v,
            "spike_component_v": waveform.spike_component_v,
            "discontinuous_component_v": waveform.discontinuous_component_v,
            "noise_component_v": waveform.noise_component_v,
        }
    ).to_csv(csv_path, index=False, encoding="utf-8-sig")

    parameters_path: Path | None = None
    if save_parameters_json:
        parameters_path = csv_path.with_name(f"{csv_path.stem}_parameters.json")
        payload = parameters_to_dict(waveform.parameters)
        payload["derived_events"] = asdict(waveform.events)
        payload["generated"] = {
            "points": waveform.points,
            "sample_rate_hz": waveform.sample_rate_hz,
            "csv_file": csv_path.name,
        }
        parameters_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return csv_path, parameters_path
