from __future__ import annotations

from dataclasses import dataclass

from ..dcm_sw_generator import DcmSwParameters, DcmSwWaveform
from ..dcm_zero_span_link import (
    DcmZeroSpanResult,
    ZeroSpanProfile,
    zero_span_profile_signature,
)
from ..waveform_quality import waveform_signature
from .spectrum import DcmSpectrum


ANALYSIS_UPDATING_MESSAGE = "当前分析仍在更新，请等待联动/FFT完成后再导出。"


class AnalysisSnapshotConsistencyError(ValueError):
    """Raised when a DCM export would mix results from different states."""


@dataclass(frozen=True)
class AnalysisSnapshot:
    generation: int | None
    completed: bool
    parameters: DcmSwParameters
    profile: ZeroSpanProfile
    waveform: DcmSwWaveform
    zero_span: DcmZeroSpanResult
    spectrum: DcmSpectrum
    waveform_signature: str
    profile_signature: str


def validate_analysis_snapshot(
    *,
    parameters: DcmSwParameters,
    profile: ZeroSpanProfile,
    waveform: DcmSwWaveform | None,
    zero_span: DcmZeroSpanResult | None,
    spectrum: DcmSpectrum | None,
    analysis_updating: bool = False,
    analysis_generation: int | None = None,
    completed_generation: int | None = None,
    waveform_generation: int | None = None,
    zero_span_generation: int | None = None,
    spectrum_generation: int | None = None,
) -> AnalysisSnapshot:
    """Validate one complete DCM/Zero Span/FFT export snapshot.

    Validation happens before any export directory or file is created.  Exact
    waveform and profile signatures deliberately catch states that point counts,
    sample rates, durations, and displayed axes alone cannot distinguish.
    """

    if analysis_updating:
        raise AnalysisSnapshotConsistencyError(ANALYSIS_UPDATING_MESSAGE)
    if analysis_generation is not None:
        generation = int(analysis_generation)
        if completed_generation != generation:
            raise AnalysisSnapshotConsistencyError(
                "当前分析快照尚未完成或已经过期，无法导出。"
            )
        layer_generations = {
            "DCM waveform": waveform_generation,
            "Zero Span": zero_span_generation,
            "FFT": spectrum_generation,
        }
        stale_layers = [
            name
            for name, result_generation in layer_generations.items()
            if result_generation != generation
        ]
        if stale_layers:
            raise AnalysisSnapshotConsistencyError(
                "当前分析包含旧 generation 结果："
                + ", ".join(stale_layers)
                + "。请等待最新计算完成后再导出。"
            )
    if waveform is None:
        raise AnalysisSnapshotConsistencyError("当前没有有效 DCM 波形，无法导出。")
    if waveform.parameters != parameters:
        raise AnalysisSnapshotConsistencyError(
            "当前 DCM 参数尚未生成对应波形，请等待联动完成后再导出。"
        )

    current_waveform_signature = waveform_signature(
        waveform.time_s,
        waveform.voltage_v,
    )

    if zero_span is None:
        raise AnalysisSnapshotConsistencyError(
            "当前 Zero Span 结果不可用或尚未更新，无法导出。"
        )
    if zero_span.source_waveform_signature != current_waveform_signature:
        raise AnalysisSnapshotConsistencyError(
            "Zero Span 结果属于旧 DCM 波形，请等待联动完成后再导出。"
        )

    current_profile_signature = zero_span_profile_signature(profile)
    if zero_span.source_profile_signature != current_profile_signature:
        raise AnalysisSnapshotConsistencyError(
            "Zero Span 结果不对应当前转换参数，请等待联动完成后再导出。"
        )
    if (
        analysis_generation is not None
        and zero_span.analysis_generation != analysis_generation
    ):
        raise AnalysisSnapshotConsistencyError(
            "Zero Span 结果属于旧 analysis generation，无法导出。"
        )

    if spectrum is None or spectrum.points == 0:
        raise AnalysisSnapshotConsistencyError(
            "当前 FFT 幅度/相位结果不可用或尚未更新，无法导出。"
        )
    if spectrum.source_waveform_signature != current_waveform_signature:
        raise AnalysisSnapshotConsistencyError(
            "FFT 幅度/相位结果属于旧 DCM 波形，请等待 FFT 完成后再导出。"
        )
    if (
        analysis_generation is not None
        and spectrum.analysis_generation != analysis_generation
    ):
        raise AnalysisSnapshotConsistencyError(
            "FFT 幅度/相位结果属于旧 analysis generation，无法导出。"
        )

    return AnalysisSnapshot(
        generation=analysis_generation,
        completed=True,
        parameters=parameters,
        profile=profile,
        waveform=waveform,
        zero_span=zero_span,
        spectrum=spectrum,
        waveform_signature=current_waveform_signature,
        profile_signature=current_profile_signature,
    )


__all__ = [
    "ANALYSIS_UPDATING_MESSAGE",
    "AnalysisSnapshot",
    "AnalysisSnapshotConsistencyError",
    "validate_analysis_snapshot",
]
