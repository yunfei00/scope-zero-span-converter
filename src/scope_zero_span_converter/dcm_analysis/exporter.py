from __future__ import annotations

import json
import math
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .. import __version__
from ..dcm_sw_generator import DcmSwParameters, DcmSwWaveform
from ..dcm_zero_span_link import DcmZeroSpanResult, ZeroSpanProfile
from .snapshot import validate_analysis_snapshot
from .spectrum import DcmSpectrum


EXPORT_SCHEMA_VERSION = 1
_ZOOM_STATE_KEYS = {"zoom_history", "zoom_state", "zoom_stack"}


def _json_safe(value: Any) -> Any:
    """Convert metadata to strict JSON and strip temporary navigation state."""

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
            if str(key) not in _ZOOM_STATE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def export_dcm_analysis_bundle(
    directory: str | Path,
    *,
    parameters: DcmSwParameters,
    profile: ZeroSpanProfile,
    waveform: DcmSwWaveform,
    zero_span: DcmZeroSpanResult,
    spectrum: DcmSpectrum,
    figure: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Export the current DCM analysis workspace as customer-readable files.

    The bundle intentionally contains explicit physical data tables instead of a
    serialized GUI cache. Rectangle-zoom history is therefore never exported.
    """

    snapshot = validate_analysis_snapshot(
        parameters=parameters,
        profile=profile,
        waveform=waveform,
        zero_span=zero_span,
        spectrum=spectrum,
    )
    waveform_signature = snapshot.waveform_signature
    profile_signature = snapshot.profile_signature

    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, Path] = {}

    time_csv = root / "dcm_time_domain.csv"
    pd.DataFrame(
        {
            "time_s": waveform.time_s,
            "voltage_v": waveform.voltage_v,
            "ideal_voltage_v": waveform.ideal_voltage_v,
            "spike_component_v": waveform.spike_component_v,
            "discontinuous_component_v": waveform.discontinuous_component_v,
            "noise_component_v": waveform.noise_component_v,
        }
    ).to_csv(time_csv, index=False, encoding="utf-8-sig")
    outputs["time_domain_csv"] = time_csv

    if zero_span is not None:
        zero_csv = root / "zero_span_time_power.csv"
        pd.DataFrame(
            {
                "time_s": zero_span.time_s,
                "amplitude_dbm": zero_span.amplitude_dbm,
                "envelope_v_rms": zero_span.envelope_v_rms,
                "power_w": zero_span.power_w,
            }
        ).to_csv(zero_csv, index=False, encoding="utf-8-sig")
        outputs["zero_span_csv"] = zero_csv

    if spectrum is not None and spectrum.points:
        spectrum_csv = root / "dcm_spectrum.csv"
        pd.DataFrame(
            {
                "frequency_hz": spectrum.frequency_hz,
                "amplitude_dbv": spectrum.amplitude_dbv,
                "phase_deg": spectrum.phase_deg,
            }
        ).to_csv(spectrum_csv, index=False, encoding="utf-8-sig")
        outputs["spectrum_csv"] = spectrum_csv

    if figure is not None:
        png_path = root / "dcm_analysis_four_panel.png"
        figure.savefig(png_path, dpi=180, bbox_inches="tight")
        outputs["four_panel_png"] = png_path

    payload: dict[str, Any] = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "export_type": "dcm_analysis_bundle",
        "software_version": __version__,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "semantics": {
            "zero_span": "fixed RF center; power versus time; span_hz=0",
            "spectrum": "DCM waveform single-sided FFT",
            "phase_reference": (
                spectrum.phase_reference if spectrum is not None else "record_start"
            ),
            "zoom_history_exported": False,
        },
        "analysis_snapshot": {
            "waveform_signature": waveform_signature,
            "zero_span_source_waveform_signature": zero_span.source_waveform_signature,
            "zero_span_profile_signature": profile_signature,
            "fft_source_waveform_signature": spectrum.source_waveform_signature,
        },
        "dcm_parameters": asdict(parameters),
        "zero_span_profile": asdict(profile),
        "data_files": {
            **{key: path.name for key, path in outputs.items()},
            "metadata_json": "analysis_metadata.json",
        },
    }
    if zero_span is not None:
        payload["zero_span_result"] = {
            "sample_rate_hz": zero_span.sample_rate_hz,
            "center_frequency_hz": zero_span.center_frequency_hz,
            "rbw_hz": zero_span.rbw_hz,
            "vbw_hz": zero_span.vbw_hz,
            "points": len(zero_span.time_s),
            "source_waveform_signature": zero_span.source_waveform_signature,
            "source_profile_signature": zero_span.source_profile_signature,
        }
    if spectrum is not None:
        payload["fft"] = {
            "points": spectrum.points,
            "sample_interval_s": spectrum.sample_interval_s,
            "window": spectrum.window,
            "amplitude_definition": spectrum.amplitude_definition,
            "phase_reference": spectrum.phase_reference,
            "phase_reference_description": spectrum.phase_reference_description,
            "phase_visibility_threshold_dbv": spectrum.phase_visibility_threshold_dbv,
            "phase_dynamic_range_db": spectrum.phase_dynamic_range_db,
            "source_waveform_signature": spectrum.source_waveform_signature,
        }
    if metadata:
        payload["workspace"] = metadata

    metadata_path = root / "analysis_metadata.json"
    metadata_path.write_text(
        json.dumps(
            _json_safe(payload),
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    outputs["metadata_json"] = metadata_path
    return outputs
