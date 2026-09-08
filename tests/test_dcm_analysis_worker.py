from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_analysis.widget import DcmAnalysisWidget
from scope_zero_span_converter.dcm_analysis.worker import SpectrumWorkerTask
from scope_zero_span_converter.dcm_sw_generator import DcmSwParameters, generate_dcm_sw_waveform


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_spectrum_worker_task_computes_without_qwidget_access():
    waveform = generate_dcm_sw_waveform(
        DcmSwParameters(total_duration_s=2e-6, switching_start_s=0.2e-6, on_time_s=0.3e-6,
                        freewheel_time_s=0.3e-6, sample_rate_hz=200e6,
                        spike_ringing_frequency_hz=20e6,
                        discontinuous_resonance_frequency_hz=5e6)
    )
    captured = []
    failures = []
    task = SpectrumWorkerTask(
        request_id=7,
        waveform_id=123,
        time_s=waveform.time_s,
        voltage_v=waveform.voltage_v,
    )
    task.signals.finished.connect(lambda request, wid, spectrum: captured.append((request, wid, spectrum)))
    task.signals.failed.connect(lambda request, wid, message: failures.append((request, wid, message)))

    task.run()

    assert not failures
    assert len(captured) == 1
    request_id, waveform_id, spectrum = captured[0]
    assert request_id == 7
    assert waveform_id == 123
    assert spectrum.points > 10
    assert len(spectrum.frequency_hz) == len(spectrum.amplitude_dbv) == len(spectrum.phase_deg)


def test_formal_widget_reuses_fft_cache_on_display_only_redraw(qapp, monkeypatch):
    del qapp
    widget = DcmAnalysisWidget()
    assert widget.current_waveform is not None
    assert widget._spectrum_cache is not None
    cached = widget._spectrum_cache

    def fail_if_recomputed(*_args, **_kwargs):
        raise AssertionError("display-only redraw must reuse cached FFT")

    monkeypatch.setattr(
        "scope_zero_span_converter.dcm_analysis.widget.compute_dcm_spectrum",
        fail_if_recomputed,
    )
    widget._redraw(zero_span_error=widget.current_zero_span_error)

    assert widget._spectrum_cache is cached


def test_large_waveform_path_schedules_worker_instead_of_sync_fft(qapp, monkeypatch):
    del qapp
    widget = DcmAnalysisWidget()
    waveform = widget.current_waveform
    assert waveform is not None

    widget._spectrum_cache_waveform = None
    widget._spectrum_cache = None
    widget.FFT_BACKGROUND_THRESHOLD_POINTS = 1
    scheduled = []
    monkeypatch.setattr(widget, "_start_spectrum_worker", lambda value: scheduled.append(value))

    result = widget._get_or_schedule_spectrum(waveform)

    assert result is None
    assert scheduled == [waveform]
