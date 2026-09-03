from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class InputConfig:
    waveform_file: str = "waveform.csv"
    metadata_file: str = "metadata.json"


@dataclass
class SignalConfig:
    center_frequency_hz: float = 200e6
    span_hz: float = 0.0
    rbw_hz: float = 10e6
    vbw_hz: float = 10e6


@dataclass
class ConversionConfig:
    detector: str = "rms"
    rbw_filter: str = "gaussian"
    vbw_enabled: bool = True
    resample_to_fsw_axis: bool = True
    use_metadata_parameters: bool = True
    impedance_ohm: float = 50.0
    calibration_db: float = 0.0


@dataclass
class ScopeConfig:
    analog_bandwidth_hz: float = 350e6


@dataclass
class OutputConfig:
    directory: str = "output"
    save_csv: bool = True
    save_plot: bool = True
    show_plot: bool = True


@dataclass
class AppConfig:
    schema_version: int = 1
    input: InputConfig = field(default_factory=InputConfig)
    signal: SignalConfig = field(default_factory=SignalConfig)
    conversion: ConversionConfig = field(default_factory=ConversionConfig)
    scope: ScopeConfig = field(default_factory=ScopeConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"不支持的配置 schema_version: {self.schema_version}")
        if self.signal.center_frequency_hz <= 0:
            raise ValueError("center_frequency_hz 必须 > 0")
        if abs(self.signal.span_hz) > 1e-9:
            raise ValueError("当前版本只支持 Zero Span，span_hz 必须为 0")
        if self.signal.rbw_hz <= 0:
            raise ValueError("rbw_hz 必须 > 0")
        if self.signal.vbw_hz <= 0:
            raise ValueError("vbw_hz 必须 > 0")
        if self.conversion.detector.lower() != "rms":
            raise ValueError("v0.1 当前只支持 RMS detector")
        if self.conversion.rbw_filter.lower() != "gaussian":
            raise ValueError("v0.1 当前只支持 Gaussian RBW filter")
        if self.conversion.impedance_ohm <= 0:
            raise ValueError("impedance_ohm 必须 > 0")
        if self.scope.analog_bandwidth_hz <= 0:
            raise ValueError("analog_bandwidth_hz 必须 > 0")


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    config = AppConfig(
        schema_version=int(raw.get("schema_version", 1)),
        input=InputConfig(**raw.get("input", {})),
        signal=SignalConfig(**raw.get("signal", {})),
        conversion=ConversionConfig(**raw.get("conversion", {})),
        scope=ScopeConfig(**raw.get("scope", {})),
        output=OutputConfig(**raw.get("output", {})),
    )
    config.validate()
    return config


def save_config(config: AppConfig, path: str | Path) -> None:
    config.validate()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(asdict(config), f, ensure_ascii=False, indent=2)
        f.write("\n")
