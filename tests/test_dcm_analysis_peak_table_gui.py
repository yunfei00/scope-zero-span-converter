from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_analysis.peaks import find_spectrum_peaks
from scope_zero_span_converter.dcm_analysis_widget import DcmAnalysisWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_peak_table_matches_current_cached_spectrum(qapp):
    del qapp
    widget = DcmAnalysisWidget()
    spectrum = widget._spectrum_from_current_cache()
    assert spectrum is not None

    peaks = find_spectrum_peaks(
        spectrum,
        top_n=widget.PEAK_TABLE_TOP_N,
        relative_floor_db=80.0,
        min_frequency_hz=0.0,
        min_separation_bins=2,
    )
    assert peaks
    assert widget.peak_table is not None
    assert widget.peak_table.rowCount() == len(peaks)

    first = peaks[0]
    assert float(widget.peak_table.item(0, 1).text()) == pytest.approx(
        first.frequency_hz / 1e6,
        rel=1e-5,
    )
    assert float(widget.peak_table.item(0, 2).text()) == pytest.approx(
        first.amplitude_dbv,
        abs=0.001,
    )
    expected_phase = "--" if not first.phase_valid else f"{first.phase_deg:.2f}"
    assert widget.peak_table.item(0, 3).text() == expected_phase


def test_peak_table_refreshes_after_dcm_parameter_change(qapp):
    del qapp
    widget = DcmAnalysisWidget()
    before = [
        widget.peak_table.item(row, 1).text()
        for row in range(widget.peak_table.rowCount())
    ]

    control = widget._parameter_controls["spike_ringing_frequency_hz"]
    control.setValue(140.0)
    widget._on_parameter_changed("spike_ringing_frequency_hz", control.value())
    widget._recompute()

    after = [
        widget.peak_table.item(row, 1).text()
        for row in range(widget.peak_table.rowCount())
    ]
    assert after
    assert before != after
