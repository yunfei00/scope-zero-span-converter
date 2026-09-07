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
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .dcm_analysis.markers import SpectrumMarker, spectrum_marker_at_frequency
from .dcm_analysis.peaks import SpectrumPeak, find_spectrum_peaks
from .dcm_analysis.spectrum import DcmSpectrum
from .dcm_sw_generator import DcmSwWaveform
from .dcm_zero_span_widget_v10 import DcmZeroSpanWidget as _CurrentDcmAnalysisWidget


class DcmAnalysisWidget(_CurrentDcmAnalysisWidget):
    """Commercial-stable entry point for the four-panel DCM analysis page."""

    PEAK_TABLE_TOP_N = 8

    def __init__(self, parent=None) -> None:
        # Parent construction dynamically draws the spectrum. These commercial
        # controls are built afterwards, so draw hooks must tolerate None state.
        self.peak_table: QTableWidget | None = None
        self.marker_info_label: QLabel | None = None
        self._current_peaks: list[SpectrumPeak] = []
        self.selected_marker_frequency_hz: float | None = None
        super().__init__(parent)
        self._build_peak_table()
        self._refresh_peak_table()
        self._update_marker_info()

    def _build_peak_table(self) -> None:
        group = QGroupBox("频谱峰值（Top 8，与幅度/相位频谱同源）")
        layout = QVBoxLayout(group)

        info_row = QHBoxLayout()
        self.marker_info_label = QLabel("Marker：未选择；点击下方峰值行可联动右侧幅度/相位图")
        self.marker_info_label.setWordWrap(True)
        clear_marker = QPushButton("清除 Marker")
        clear_marker.clicked.connect(self._clear_frequency_marker)
        info_row.addWidget(self.marker_info_label, 1)
        info_row.addWidget(clear_marker)
        layout.addLayout(info_row)

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
            "点击某一行会在幅度/相位图同时显示同频 Marker；"
            "相位被有效幅度门限隐藏时显示 --。"
        )
        table.cellClicked.connect(self._on_peak_table_clicked)
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

    def _current_frequency_marker(self) -> SpectrumMarker | None:
        spectrum = self._spectrum_from_current_cache()
        frequency_hz = self.selected_marker_frequency_hz
        if spectrum is None or frequency_hz is None:
            return None
        try:
            return spectrum_marker_at_frequency(spectrum, frequency_hz)
        except ValueError:
            return None

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
        self._current_peaks = peaks

        table.blockSignals(True)
        try:
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
        finally:
            table.blockSignals(False)

    def _on_peak_table_clicked(self, row: int, _column: int) -> None:
        if not 0 <= row < len(self._current_peaks):
            return
        self.selected_marker_frequency_hz = self._current_peaks[row].frequency_hz
        self._update_marker_info()
        # Marker is display-only: redraw existing cached/current data without
        # changing any DCM or Zero Span parameter.
        self._redraw(zero_span_error=self.current_zero_span_error)

    def _clear_frequency_marker(self) -> None:
        if self.selected_marker_frequency_hz is None:
            return
        self.selected_marker_frequency_hz = None
        self._update_marker_info()
        self._redraw(zero_span_error=self.current_zero_span_error)

    def _update_marker_info(self) -> None:
        label = self.marker_info_label
        if label is None:
            return
        marker = self._current_frequency_marker()
        if marker is None:
            label.setText("Marker：未选择；点击下方峰值行可联动右侧幅度/相位图")
            return

        phase_text = "--（低于有效幅度门限）"
        if marker.phase_valid:
            phase_text = f"{marker.phase_deg:.2f}°"
        label.setText(
            f"Marker：{marker.frequency_hz/1e6:.6g} MHz | "
            f"{marker.amplitude_dbv:.3f} dBV | Phase {phase_text}"
        )

    @staticmethod
    def _draw_frequency_marker_line(ax, marker: SpectrumMarker | None, *, phase: bool) -> None:
        if marker is None:
            return
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        x_mhz = marker.frequency_hz / 1e6
        ax.axvline(x_mhz, linestyle=":", linewidth=1.2)
        if phase:
            if marker.phase_valid:
                ax.plot([x_mhz], [marker.phase_deg], marker="o", markersize=4)
        else:
            ax.plot([x_mhz], [marker.amplitude_dbv], marker="o", markersize=4)
        # Adding marker artists must never autoscale a customer-selected/zoomed view.
        ax.set_xlim(xlim, auto=False)
        ax.set_ylim(ylim, auto=False)

    def _draw_frequency_panel(self, ax, waveform: DcmSwWaveform) -> None:
        # Parent computes/caches the common magnitude+phase FFT first.
        super()._draw_frequency_panel(ax, waveform)
        self._refresh_peak_table()
        self._update_marker_info()
        self._draw_frequency_marker_line(
            ax,
            self._current_frequency_marker(),
            phase=False,
        )

    def _draw_reserved_panel(self, ax) -> None:
        # v10 uses the reserved-panel hook for the phase spectrum.
        super()._draw_reserved_panel(ax)
        self._draw_frequency_marker_line(
            ax,
            self._current_frequency_marker(),
            phase=True,
        )


__all__ = ["DcmAnalysisWidget"]
