from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .converter import EPS_W, apply_vbw, gaussian_rbw_baseband
from .dcm_sw_generator import DcmSwWaveform


@dataclass
class ZeroSpanProfile:
    """DCM → Zero Span 页面使用的稳定转换配置。"""

    center_frequency_hz: float = 200e6
    rbw_hz: float = 10e6
    vbw_hz: float = 10e6
    vbw_enabled: bool = True
    impedance_ohm: float = 50.0
    calibration_db: float = 0.0
    scope_analog_bandwidth_hz: float = 350e6

    def validate(self, sample_rate_hz: float | None = None) -> None:
        if self.center_frequency_hz <= 0:
            raise ValueError("Center Frequency 必须 > 0")
        if self.rbw_hz <= 0:
            raise ValueError("RBW 必须 > 0")
        if self.vbw_hz <= 0:
            raise ValueError("VBW 必须 > 0")
        if self.impedance_ohm <= 0:
            raise ValueError("阻抗必须 > 0")
        if self.scope_analog_bandwidth_hz <= 0:
            raise ValueError("示波器模拟带宽必须 > 0")

        top_hz = self.center_frequency_hz + self.rbw_hz / 2.0
        if top_hz > self.scope_analog_bandwidth_hz:
            raise ValueError(
                "Center+RBW/2 超出示波器模拟带宽："
                f"{top_hz:g} > {self.scope_analog_bandwidth_hz:g} Hz"
            )
        if sample_rate_hz is not None and top_hz >= sample_rate_hz / 2.0:
            raise ValueError(
                "采样率不足："
                f"Center+RBW/2={top_hz:g} Hz, Nyquist={sample_rate_hz/2:g} Hz"
            )


@dataclass(frozen=True)
class DcmZeroSpanResult:
    time_s: np.ndarray
    amplitude_dbm: np.ndarray
    envelope_v_rms: np.ndarray
    power_w: np.ndarray
    sample_rate_hz: float
    center_frequency_hz: float
    rbw_hz: float
    vbw_hz: float | None


def convert_dcm_waveform_to_zero_span(
    waveform: DcmSwWaveform,
    profile: ZeroSpanProfile,
) -> DcmZeroSpanResult:
    """复用已验证 Zero Span 核心，把当前 DCM 波形转换成 Time vs dBm。

    与旧“波形研究”不同，这里故意保留 DCM 波形的绝对时间轴，确保上下两图
    可以直接联动观察。例如输入 5~17 us，输出同样保持 5~17 us。
    """

    t = np.asarray(waveform.time_s, dtype=float)
    v = np.asarray(waveform.voltage_v, dtype=float)
    if len(t) < 32 or len(t) != len(v):
        raise ValueError("DCM 波形无效或点数不足")
    dt = np.diff(t)
    if np.any(dt <= 0):
        raise ValueError("DCM 波形 time_s 必须严格递增")
    sample_rate_hz = 1.0 / float(np.median(dt))
    profile.validate(sample_rate_hz)

    baseband = gaussian_rbw_baseband(
        t,
        v,
        sample_rate_hz,
        profile.center_frequency_hz,
        profile.rbw_hz,
    )
    envelope_v_rms = np.abs(baseband) / np.sqrt(2.0)
    power_w = envelope_v_rms**2 / profile.impedance_ohm

    effective_vbw = profile.vbw_hz if profile.vbw_enabled else None
    filtered_power_w = apply_vbw(power_w, sample_rate_hz, effective_vbw)
    amplitude_dbm = (
        10.0 * np.log10(np.maximum(filtered_power_w, EPS_W) / 1e-3)
        + profile.calibration_db
    )

    return DcmZeroSpanResult(
        time_s=t.copy(),
        amplitude_dbm=amplitude_dbm,
        envelope_v_rms=envelope_v_rms,
        power_w=filtered_power_w,
        sample_rate_hz=sample_rate_hz,
        center_frequency_hz=profile.center_frequency_hz,
        rbw_hz=profile.rbw_hz,
        vbw_hz=effective_vbw,
    )


def zero_span_profile_to_dict(profile: ZeroSpanProfile) -> dict:
    return {
        "schema_version": 1,
        "profile_type": "dcm_zero_span",
        "span_hz": 0.0,
        "detector": "rms",
        "rbw_filter": "gaussian",
        "parameters": asdict(profile),
    }


def zero_span_profile_from_dict(raw: dict) -> ZeroSpanProfile:
    if not isinstance(raw, dict):
        raise ValueError("Zero Span 参数 JSON 根节点必须是对象")
    if int(raw.get("schema_version", 1)) != 1:
        raise ValueError("当前只支持 Zero Span profile schema_version=1")
    if abs(float(raw.get("span_hz", 0.0))) > 1e-9:
        raise ValueError("当前页面只支持 Zero Span，span_hz 必须为 0")
    params = raw.get("parameters", raw)
    if not isinstance(params, dict):
        raise ValueError("Zero Span parameters 必须是对象")
    allowed = set(ZeroSpanProfile.__dataclass_fields__)
    unexpected = sorted(set(params) - allowed)
    if unexpected:
        raise ValueError("Zero Span 参数包含未知字段：" + ", ".join(unexpected))
    profile = ZeroSpanProfile(**params)
    profile.validate()
    return profile


def save_zero_span_profile(profile: ZeroSpanProfile, path: str | Path) -> Path:
    profile.validate()
    path = Path(path)
    if path.suffix.lower() != ".json":
        path = path.with_suffix(".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(zero_span_profile_to_dict(profile), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load_zero_span_profile(path: str | Path) -> ZeroSpanProfile:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return zero_span_profile_from_dict(raw)
