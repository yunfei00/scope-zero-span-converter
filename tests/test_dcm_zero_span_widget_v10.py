from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_zero_span_widget_v10 import DcmZeroSpanWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_phase_panel_replaces_reserved_panel_and_uses_same_fft_bins(qapp):
    del qapp
    widget = DcmZeroSpanWidget()

    assert len(widget.figure.axes) == 4
    ax_frequency = widget.figure.axes[1]
    ax_phase = widget.figure.axes[3]
    assert "幅度频谱" in ax_frequency.get_title()
    assert "相位频谱" in ax_phase.get_title()

    frequency = widget.current_spectrum_frequency_hz
    amplitude = widget.current_spectrum_amplitude_dbv
    phase = widget.current_spectrum_phase_deg
    assert len(frequency) > 0
    assert len(frequency) == len(amplitude) == len(phase)

    valid_phase = phase[np.isfinite(phase)]
    assert len(valid_phase) > 0
    assert np.all(valid_phase >= -180.0 - 1e-12)
    assert np.all(valid_phase <= 180.0 + 1e-12)


def test_low_amplitude_phase_is_hidden(qapp):
    del qapp
    widget = DcmZeroSpanWidget()

    amplitude = widget.current_spectrum_amplitude_dbv
    phase = widget.current_spectrum_phase_deg
    low = amplitude < widget.PHASE_VISIBLE_FLOOR_DBV

    # 默认 DCM 波形包含噪声；某些依赖版本/数值环境下，整个 FFT 噪声底可能都高于
    # -120 dBV，因此不能假定默认波形一定存在 low bin。这里验证门限语义本身：
    # 只要出现低于门限的 bin，其相位必须全部隐藏；所有可见相位则必须来自门限以上。
    assert np.all(np.isnan(phase[low]))

    visible = np.isfinite(phase)
    assert np.any(visible)
    assert np.all(amplitude[visible] >= widget.PHASE_VISIBLE_FLOOR_DBV)


def test_magnitude_and_phase_share_frequency_axis(qapp):
    del qapp
    widget = DcmZeroSpanWidget()

    ax_frequency = widget.figure.axes[1]
    ax_phase = widget.figure.axes[3]
    assert ax_phase.get_shared_x_axes().joined(ax_frequency, ax_phase)
    assert np.allclose(ax_frequency.get_xlim(), ax_phase.get_xlim())
    assert np.allclose(ax_phase.get_ylim(), (-180.0, 180.0))
    assert np.allclose(
        ax_phase.get_yticks(),
        [-180.0, -120.0, -60.0, 0.0, 60.0, 120.0, 180.0],
    )


def test_manual_frequency_range_updates_phase_x_for_current_view(qapp):
    del qapp
    widget = DcmZeroSpanWidget()

    spins = (
        widget.freq_x_min,
        widget.freq_x_max,
        widget.freq_x_step,
        widget.freq_y_min,
        widget.freq_y_max,
        widget.freq_y_step,
    )
    for spin in spins:
        spin.blockSignals(True)
    try:
        widget.freq_x_min.setValue(100.0)
        widget.freq_x_max.setValue(400.0)
        widget.freq_x_step.setValue(50.0)
        widget.freq_y_min.setValue(-140.0)
        widget.freq_y_max.setValue(0.0)
        widget.freq_y_step.setValue(20.0)
    finally:
        for spin in spins:
            spin.blockSignals(False)

    widget._on_frequency_axis_changed()

    ax_frequency = widget.figure.axes[1]
    ax_phase = widget.figure.axes[3]
    assert np.allclose(ax_frequency.get_xlim(), (100.0, 400.0))
    assert np.allclose(ax_phase.get_xlim(), (100.0, 400.0))


def test_frequency_zoom_x_is_synchronized_to_phase(qapp):
    del qapp
    widget = DcmZeroSpanWidget()

    widget._zoom_ranges["frequency"] = ((150.0, 250.0), (-120.0, -20.0))
    widget._redraw(zero_span_error=widget.current_zero_span_error)

    ax_frequency = widget.figure.axes[1]
    ax_phase = widget.figure.axes[3]
    assert np.allclose(ax_frequency.get_xlim(), (150.0, 250.0))
    assert np.allclose(ax_phase.get_xlim(), (150.0, 250.0))
    assert np.allclose(ax_frequency.get_ylim(), (-120.0, -20.0))
    assert np.allclose(ax_phase.get_ylim(), (-180.0, 180.0))


def test_dcm_recompute_updates_magnitude_and_phase_together(qapp):
    del qapp
    widget = DcmZeroSpanWidget()
    before_amplitude = widget.current_spectrum_amplitude_dbv.copy()
    before_phase = widget.current_spectrum_phase_deg.copy()

    control = widget._parameter_controls["spike_ringing_frequency_hz"]
    control.setValue(120.0)
    widget._on_parameter_changed("spike_ringing_frequency_hz", control.value())
    widget._recompute()

    after_amplitude = widget.current_spectrum_amplitude_dbv
    after_phase = widget.current_spectrum_phase_deg
    assert len(after_amplitude) == len(before_amplitude)
    assert len(after_phase) == len(before_phase)
    assert not np.allclose(before_amplitude, after_amplitude)

    # NaN 掩码会随幅度变化，比较相位时只在双方都有效的频点上判断。
    common = np.isfinite(before_phase) & np.isfinite(after_phase)
    assert np.any(common)
    assert not np.allclose(before_phase[common], after_phase[common])
