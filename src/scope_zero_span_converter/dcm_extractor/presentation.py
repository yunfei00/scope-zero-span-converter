"""Plot and staged-status presentation for the formal DCM extractor."""

from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from ..dcm_discontinuous_extractor import DcmDiscontinuousExtractionResult
from ..dcm_global_refiner import DcmGlobalRefinementResult
from ..dcm_parameter_extractor import DcmBasicExtractionResult
from ..dcm_ringing_extractor import DcmRingingExtractionResult
from ..dcm_sw_generator import event_times
from ..dcm_unified_fit import DcmUnifiedFitResult


def staged_summary(
    basic: DcmBasicExtractionResult,
    ringing: DcmRingingExtractionResult | None,
    discontinuous: DcmDiscontinuousExtractionResult | None,
    global_refinement: DcmGlobalRefinementResult | None,
    *,
    ringing_error: str | None,
    discontinuous_error: str | None,
    global_error: str | None,
) -> tuple[str, str]:
    """Return confidence and warning text while preserving partial results."""

    if discontinuous is not None and ringing is not None:
        combined = (
            0.35 * basic.overall_confidence
            + 0.30 * ringing.overall_confidence
            + 0.35 * discontinuous.confidence
        )
        confidence = (
            f"综合参考置信度：{combined*100:.1f}% | "
            f"基础 {basic.overall_confidence*100:.1f}% | "
            f"尖峰/振铃 {ringing.overall_confidence*100:.1f}% | "
            f"DCM {discontinuous.confidence*100:.1f}%"
        )
    elif discontinuous is not None:
        combined = 0.55 * basic.overall_confidence + 0.45 * discontinuous.confidence
        confidence = (
            f"综合参考置信度：{combined*100:.1f}% | "
            f"基础 {basic.overall_confidence*100:.1f}% | "
            f"DCM {discontinuous.confidence*100:.1f}% | 尖峰/振铃未完成"
        )
    elif ringing is not None:
        combined = 0.5 * basic.overall_confidence + 0.5 * ringing.overall_confidence
        confidence = (
            f"综合参考置信度：{combined*100:.1f}% | "
            f"基础 {basic.overall_confidence*100:.1f}% | "
            f"尖峰/振铃 {ringing.overall_confidence*100:.1f}% | DCM 未完成"
        )
    else:
        confidence = (
            f"基础参数总体置信度：{basic.overall_confidence*100:.1f}% | "
            "尖峰/振铃、DCM：未完成"
        )

    warnings = list(basic.warnings)
    if ringing is not None:
        warnings.extend(ringing.warnings)
    elif ringing_error:
        warnings.append(f"尖峰/寄生振铃拟合未完成：{ringing_error}")
    if discontinuous is not None:
        warnings.extend(discontinuous.warnings)
    elif discontinuous_error:
        warnings.append(f"DCM 断续谐振拟合未完成：{discontinuous_error}")
    if global_refinement is not None:
        warnings.extend(global_refinement.warnings)
    elif global_error:
        warnings.append(f"全局联合精修未完成：{global_error}")

    if warnings:
        warning = "注意：\n" + "\n".join(
            f"• {item}" for item in dict.fromkeys(warnings)
        )
    elif discontinuous is not None:
        warning = (
            "基础分段、开关沿寄生振铃和 DCM 断续谐振均未发现明显低置信度项。"
            "最终残差已用于估计示波器底噪。"
        )
    else:
        warning = "已保留当前成功阶段的结果；可根据提示检查后级拟合。"
    return confidence, warning


def draw_extraction(
    *,
    figure: Figure,
    canvas: FigureCanvas,
    show_residual: bool,
    time_s: np.ndarray | None,
    voltage_v: np.ndarray | None,
    basic: DcmBasicExtractionResult | None,
    ringing: DcmRingingExtractionResult | None,
    discontinuous: DcmDiscontinuousExtractionResult | None,
    global_refinement: DcmGlobalRefinementResult | None,
    current_fit: DcmUnifiedFitResult | None,
) -> None:
    """Render every available stage from full algorithm arrays."""

    figure.clear()
    if time_s is None or voltage_v is None:
        canvas.draw()
        return

    residual_visible = show_residual and basic is not None
    if residual_visible:
        main_ax = figure.add_subplot(211)
        residual_ax = figure.add_subplot(212, sharex=main_ax)
    else:
        main_ax = figure.add_subplot(111)
        residual_ax = None

    x_us = time_s * 1e6
    main_ax.plot(x_us, voltage_v, linewidth=0.8, label="CSV 实测波形")

    if basic is not None:
        main_ax.plot(
            x_us,
            basic.fitted_ideal_voltage_v,
            linewidth=1.1,
            linestyle="--",
            label="基础理想轨迹",
        )
        if ringing is not None:
            main_ax.plot(
                x_us,
                basic.fitted_ideal_voltage_v + ringing.fitted_spike_component_v,
                linewidth=0.9,
                alpha=0.85,
                label="基础 + 尖峰/寄生振铃拟合",
            )
        if discontinuous is not None:
            spike = (
                np.zeros_like(time_s, dtype=float)
                if ringing is None
                else ringing.fitted_spike_component_v
            )
            main_ax.plot(
                x_us,
                basic.fitted_ideal_voltage_v
                + spike
                + discontinuous.fitted_discontinuous_component_v,
                linewidth=1.05,
                alpha=0.9,
                label="基础 + 尖峰/振铃 + DCM 完整拟合",
            )
        if global_refinement is not None:
            main_ax.plot(
                x_us,
                global_refinement.optimized_reconstruction_v,
                linewidth=1.25,
                alpha=0.95,
                label="全局联合精修重建波形",
            )
        if current_fit is not None:
            main_ax.plot(
                x_us,
                current_fit.reconstruction_v,
                linewidth=1.45,
                alpha=0.95,
                label="生成器同源当前重建波形",
            )

        markers = (
            (basic.switching_start_s, "开关起始"),
            (basic.rise_end_s, "上升结束"),
            (basic.fall_start_s, "下降开始"),
            (basic.fall_end_s, "下降结束"),
            (basic.freewheel_end_s, "断续开始"),
        )
        for index, (time_value, label) in enumerate(markers):
            main_ax.axvline(time_value * 1e6, linestyle=":", alpha=0.55)
            main_ax.text(
                time_value * 1e6,
                0.98 - (index % 2) * 0.08,
                label,
                transform=main_ax.get_xaxis_transform(),
                rotation=90,
                va="top",
                ha="right",
                fontsize=8,
            )

        if current_fit is not None:
            events = event_times(current_fit.parameters)
            for value, label in (
                (events.rise_start_s, "当前开关起始"),
                (events.high_end_s, "当前下降沿开始"),
                (events.freewheel_end_s, "当前 DCM 起点"),
            ):
                main_ax.axvline(value * 1e6, linestyle=":", alpha=0.55, label=label)

        if residual_ax is not None:
            residual_ax.plot(x_us, basic.residual_v, linewidth=0.65, label="基础残差")
            if ringing is not None:
                residual_ax.plot(
                    x_us,
                    ringing.fitted_spike_component_v,
                    linewidth=0.85,
                    label="尖峰/寄生振铃拟合分量",
                )
                residual_ax.plot(
                    x_us,
                    ringing.residual_after_spike_v,
                    linewidth=0.65,
                    alpha=0.9,
                    label="扣除开关沿后的残差",
                )
            if discontinuous is not None:
                residual_ax.plot(
                    x_us,
                    discontinuous.fitted_discontinuous_component_v,
                    linewidth=0.9,
                    label="DCM 断续谐振拟合分量",
                )
                residual_ax.plot(
                    x_us,
                    discontinuous.final_residual_v,
                    linewidth=0.65,
                    alpha=0.9,
                    label="最终残差 ≈ 噪声 + 模型误差",
                )
            if global_refinement is not None:
                residual_ax.plot(
                    x_us,
                    global_refinement.final_residual_v,
                    linewidth=0.75,
                    alpha=0.95,
                    label="联合精修最终残差",
                )
            if current_fit is not None:
                residual_ax.plot(
                    x_us,
                    current_fit.residual_v,
                    linewidth=0.8,
                    alpha=0.95,
                    label="生成器同源当前残差",
                )
            residual_ax.axhline(0.0, linewidth=0.7, alpha=0.5)
            residual_ax.set_title(
                "逐阶段残差：基础残差 → 扣除开关沿 → 扣除 DCM → 最终残差"
            )
            residual_ax.set_ylabel("残差电压 (V)")
            residual_ax.set_xlabel("时间 (µs)")
            residual_ax.grid(True, alpha=0.3)
            residual_ax.legend()

    main_ax.set_title("DCM SW 参数反演：实测波形与逐阶段拟合轨迹")
    main_ax.set_ylabel("电压 (V)")
    if residual_ax is None:
        main_ax.set_xlabel("时间 (µs)")
    main_ax.grid(True, alpha=0.3)
    main_ax.legend()
    figure.tight_layout()
    canvas.draw()


__all__ = ["draw_extraction", "staged_summary"]
