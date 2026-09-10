"""File exports for the formal DCM parameter extractor."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from ..dcm_discontinuous_extractor import DcmDiscontinuousExtractionResult
from ..dcm_global_refiner import DcmGlobalRefinementResult
from ..dcm_parameter_extractor import DcmBasicExtractionResult
from ..dcm_ringing_extractor import DcmRingingExtractionResult
from ..dcm_sw_generator import DcmSwParameters, evaluate_dcm_sw_deterministic_components
from ..dcm_unified_fit import DcmUnifiedFitResult


def build_extraction_payload(
    *,
    basic: DcmBasicExtractionResult,
    ringing: DcmRingingExtractionResult | None,
    discontinuous: DcmDiscontinuousExtractionResult | None,
    global_refinement: DcmGlobalRefinementResult | None,
    current_parameters: DcmSwParameters | None,
    current_fit: DcmUnifiedFitResult | None,
    ringing_error: str | None = None,
    discontinuous_error: str | None = None,
    global_error: str | None = None,
    current_fit_error: str | None = None,
    source_csv: Path | None = None,
) -> dict:
    """Build the stable extractor JSON shape without touching GUI state."""

    payload = {
        "algorithm": "dcm_parameter_identification_v5_generator_unified",
        "source_model": "single_event_dcm_sw_v2_signed_spikes",
        "basic": basic.to_dict(),
        "edge_ringing": None if ringing is None else ringing.to_dict(),
        "discontinuous_resonance": (
            None if discontinuous is None else discontinuous.to_dict()
        ),
        "global_refinement": (
            None if global_refinement is None else global_refinement.to_dict()
        ),
        "current_generator_parameters": (
            None if current_parameters is None else asdict(current_parameters)
        ),
        "current_generator_fit": None if current_fit is None else current_fit.to_dict(),
        "note": (
            "current_generator_parameters 与 DCM SW 生成器 DcmSwParameters 字段完全一致；"
            "相位仅保留在内部自动拟合诊断中，不属于当前生成器主模型。"
        ),
    }
    if ringing_error:
        payload["edge_ringing_error"] = ringing_error
    if discontinuous_error:
        payload["discontinuous_resonance_error"] = discontinuous_error
    if global_error:
        payload["global_refinement_error"] = global_error
    if current_fit_error:
        payload["current_generator_fit_error"] = current_fit_error
    if source_csv is not None:
        payload["source_csv"] = str(source_csv)
    return payload


def save_extraction_json(path: str | Path, payload: dict) -> Path:
    destination = Path(path)
    if destination.suffix.lower() != ".json":
        destination = destination.with_suffix(".json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def save_reconstruction_csv(
    path: str | Path,
    *,
    time_s: np.ndarray,
    source_voltage_v: np.ndarray,
    parameters: DcmSwParameters,
    fit: DcmUnifiedFitResult,
) -> Path:
    """Save the current model reconstruction and research components."""

    destination = Path(path)
    if destination.suffix.lower() != ".csv":
        destination = destination.with_suffix(".csv")
    destination.parent.mkdir(parents=True, exist_ok=True)

    components = evaluate_dcm_sw_deterministic_components(time_s, parameters)
    pd.DataFrame(
        {
            # The first two columns intentionally remain a standard waveform input.
            "time_s": time_s,
            "voltage_v": fit.reconstruction_v,
            "source_voltage_v": source_voltage_v,
            "residual_v": fit.residual_v,
            "ideal_voltage_v": components.ideal_voltage_v,
            "spike_component_v": components.spike_component_v,
            "discontinuous_component_v": components.discontinuous_component_v,
        }
    ).to_csv(destination, index=False, encoding="utf-8-sig")
    return destination


__all__ = [
    "build_extraction_payload",
    "save_extraction_json",
    "save_reconstruction_csv",
]
