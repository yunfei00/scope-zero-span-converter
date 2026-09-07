"""Stable GUI entry point for DCM linked analysis.

The versioned widget modules are retained temporarily for compatibility while
commercialization refactoring is in progress. New application code must import
from this module instead of depending on a concrete ``*_vN`` implementation.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .dcm_analysis.peaks import find_spectrum_peaks
from .dcm_analysis.spectrum import DcmSpectrum
from .dcm_sw_generator import DcmSwWaveform
from .dcm_zero_span_widget_v10 import DcmZeroSpanWidget as _CurrentDcmAnalysisWidget


class DcmAnalysisWidget(_CurrentDcmAnalysisWidget):
    """Commercial-stable entry point for the four-panel DCM analysis page."""

    PEAK_TABLE_TOP_N = 8

    def __init__(self, parent=None) -> None:
        # Parent construction dynamically draws the spectrum. The table is built
        # afterwards, so draw hooks must tolerate this initial None state.
        self.peak_table: QTableWidget | None = None
        super().__init__(parent)
        self._build_peak_table()
        self._refresh_peak_table()

    def _build_peak_table(self) -> None:
        group = QGroupBox("频谱峰值（Top 8，与幅度/相位频谱同源）")
        layout = QVBoxLayout(group)

        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(["#", "频率 (MHz)", "幅度 (dBV)", "相位 (°)"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setMaximumHeight(230)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        table.setToolTip(
            "峰值直接来自右侧当前 DCM FFT 的同一组 frequency bins。"
            "相位被有效幅度门限隐藏时显示 --。"
        )
        layout.addWidget(table)
        self.peak_table = table

        # Base widget keeps one final stretch item. Insert before it so the table
        # remains part of the left scroll content instead of being pushed below it.
        insert_index = max(0, self.left_layout.count() - 1)
        self.left_layout.insertWidget(insert_index, group)

    def _spectrum_from_current_cache(self) -> DcmSpectrum | None:
        frequency = np.asarray(self.current_spectrum_frequency_hz, dtype=float)
        amplitude = np.asarray(self.current_spectrum_amplitude_dbv, dtype=float)
        phase = np.asarray(self.current_spectrum_phase_deg, dtype=float)
        if not (len(frequency) == len(amplitude) == len(phase)) or len(frequency) < 3:
            return None

        if self.current_waveform is None or len(self.current_waveform.time_s) < 2:
            return None
        dt = float(np.median(np.diff(np.asarray(self.current_waveform.time_s, dtype=float))))
        if not np.isfinite(dt) or dt <= 0:
            return None

        return DcmSpectrum(
            frequency_hz=frequency,
            amplitude_dbv=amplitude,
            phase_deg=phase,
            sample_interval_s=dt,
            phase_visibility_threshold_dbv=float(
                getattr(
                    self,
                    "current_phase_visibility_threshold_dbv",
                    self.PHASE_VISIBLE_FLOOR_DBV,
                )
            ),
            phase_dynamic_range_db=float(self.PHASE_DYNAMIC_RANGE_DB),
        )

    def _refresh_peak_table(self) -> None:
        table = self.peak_table
        if table is None:
            return

        spectrum = self._spectrum_from_current_cache()
        peaks = (
            find_spectrum_peaks(
                spectrum,
                top_n=self.PEAK_TABLE_TOP_N,
                relative_floor_db=80.0,
                min_frequency_hz=0.0,
                min_separation_bins=2,
            )
            if spectrum is not None
            else []
        )

        table.setRowCount(len(peaks))
        for row, peak in enumerate(peaks):
            values = (
                str(peak.rank),
                f"{peak.frequency_hz / 1e6:.6g}",
                f"{peak.amplitude_dbv:.3f}",
                "--" if not peak.phase_valid else f"{peak.phase_deg:.2f}",
            )
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))

    def _draw_frequency_panel(self, ax, waveform: DcmSwWaveform) -> None:
        # Parent computes/caches the common magnitude+phase FFT first.
        super()._draw_frequency_panel(ax, waveform)
        self._refresh_peak_table()


__all__ = ["DcmAnalysisWidget"]
