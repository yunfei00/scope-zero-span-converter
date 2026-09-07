from __future__ import annotations

from matplotlib.figure import Figure

from scope_zero_span_converter.dcm_analysis.plots import (
    draw_magnitude_spectrum_panel,
    draw_phase_spectrum_panel,
    draw_time_domain_panel,
    draw_zero_span_panel,
)
from scope_zero_span_converter.dcm_analysis.spectrum import compute_dcm_spectrum
from scope_zero_span_converter.dcm_sw_generator import DcmSwParameters, generate_dcm_sw_waveform
from scope_zero_span_converter.dcm_zero_span_link import (
    ZeroSpanProfile,
    convert_dcm_waveform_to_zero_span,
)


def _data():
    waveform = generate_dcm_sw_waveform(DcmSwParameters(noise_rms_v=0.0))
    zero_span = convert_dcm_waveform_to_zero_span(waveform, ZeroSpanProfile())
    spectrum = compute_dcm_spectrum(waveform.time_s, waveform.voltage_v)
    return waveform, zero_span, spectrum


def test_formal_plot_layer_draws_four_physical_views():
    waveform, zero_span, spectrum = _data()
    figure = Figure(figsize=(8, 6))
    ax_time = figure.add_subplot(221)
    ax_mag = figure.add_subplot(222)
    ax_zero = figure.add_subplot(223, sharex=ax_time)
    ax_phase = figure.add_subplot(224)

    draw_time_domain_panel(ax_time, waveform)
    draw_zero_span_panel(ax_zero, waveform, zero_span)
    draw_magnitude_spectrum_panel(
        ax_mag,
        spectrum,
        center_frequency_hz=200e6,
        rbw_hz=10e6,
    )
    draw_phase_spectrum_panel(
        ax_phase,
        spectrum,
        center_frequency_hz=200e6,
        rbw_hz=10e6,
    )

    assert len(ax_time.lines) >= 2
    assert "DCM SW 时域波形" in ax_time.get_title()
    assert "Zero Span" in ax_zero.get_title()
    assert ax_zero.get_xlabel() == "绝对时间 (µs)"
    assert len(ax_zero.lines) >= 1

    assert "DCM 幅度频谱" in ax_mag.get_title()
    assert ax_mag.get_ylabel() == "幅度 (dBV)"
    assert len(ax_mag.lines) >= 2  # FFT + Center reference
    assert len(ax_mag.patches) >= 1  # RBW region

    assert "DCM 相位频谱" in ax_phase.get_title()
    assert ax_phase.get_ylabel() == "相位 (°)"
    assert ax_phase.get_ylim() == (-180.0, 180.0)
    assert len(ax_phase.lines) >= 2  # phase + Center reference
    assert len(ax_phase.patches) >= 1


def test_zero_span_plot_keeps_absolute_time_axis_when_conversion_invalid():
    waveform, _zero_span, _spectrum = _data()
    figure = Figure()
    ax = figure.add_subplot(111)

    draw_zero_span_panel(
        ax,
        waveform,
        None,
        error="Center+RBW/2 超出示波器模拟带宽",
    )

    expected_start_us = waveform.time_s[0] * 1e6
    expected_end_us = waveform.time_s[-1] * 1e6
    assert ax.get_xlim()[0] == expected_start_us
    assert ax.get_xlim()[1] == expected_end_us
    assert "等待有效转换参数" in ax.get_title()
    assert any("模拟带宽" in text.get_text() for text in ax.texts)


def test_frequency_plot_warns_when_center_exceeds_nyquist_without_faking_span():
    _waveform, _zero_span, spectrum = _data()
    figure = Figure()
    ax = figure.add_subplot(111)

    draw_magnitude_spectrum_panel(
        ax,
        spectrum,
        center_frequency_hz=1.2e9,
        rbw_hz=10e6,
    )

    assert any("超出当前 Nyquist" in text.get_text() for text in ax.texts)
    # This is still a waveform FFT view. No fake FSW start/stop sweep is created.
    assert ax.get_xlim()[0] == 0.0
