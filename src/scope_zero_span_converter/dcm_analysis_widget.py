"""Stable GUI entry point for DCM linked analysis.

The versioned widget modules are retained temporarily for compatibility while
commercialization refactoring is in progress. New application code must import
from this module instead of depending on a concrete ``*_vN`` implementation.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .dcm_analysis.exporter import export_dcm_analysis_bundle
from .dcm_analysis.markers import SpectrumMarker, spectrum_marker_at_frequency
from .dcm_analysis.peaks import SpectrumPeak, find_spectrum_peaks
from .dcm_analysis.plots import (
    draw_magnitude_spectrum_panel,
    draw_phase_spectrum_panel,
)
from .dcm_analysis.spectrum import DcmSpectrum, compute_dcm_spectrum, waveform_signature
from .dcm_analysis.time_markers import (
    TimeMarker,
    time_marker_at_time,
    time_marker_delta,
)
from .dcm_sw_generator import DcmSwWaveform
from .dcm_zero_span_widget_v10 import DcmZeroSpanWidget as _CurrentDcmAnalysisWidget
from .workspace import collect_dcm_analysis_workspace


class DcmAnalysisWidget(_CurrentDcmAnalysisWidget):
    """Commercial-stable entry point for the four-panel DCM analysis page."""

    PEAK_TABLE_TOP_N = 8

    def __init__(self, parent=None) -> None:
        # Parent construction dynamically draws the spectrum. These commercial
        # controls are built afterwards, so draw hooks must tolerate None state.
        self.zero_span_info_label: QLabel | None = None
        self.peak_table: QTableWidget | None = None
        self.marker_info_label: QLabel | None = None
        self._current_peaks: list[SpectrumPeak] = []
        self.selected_marker_frequency_hz: float | None = None

        self.time_marker_a_enable: QCheckBox | None = None
        self.time_marker_b_enable: QCheckBox | None = None
        self.time_marker_a_time_us: QDoubleSpinBox | None = None
        self.time_marker_b_time_us: QDoubleSpinBox | None = None
        self.time_marker_info_label: QLabel | None = None
        self._time_marker_defaults_initialized = False

        super().__init__(parent)
        self._build_zero_span_info_card()
        self._build_peak_table()
        self._build_time_marker_controls()
        self._build_analysis_export_group()
        self._update_zero_span_info_card()
        self._refresh_peak_table()
        self._update_marker_info()
        self._sync_time_marker_controls_to_waveform()
        self._update_time_marker_info()

    # ------------------------------------------------------------------
    # Zero Span Center / RBW information card
    # ------------------------------------------------------------------
    def _build_zero_span_info_card(self) -> None:
        group = QGroupBox("Zero Span 测量窗口（Center / RBW）")
        layout = QVBoxLayout(group)
        label = QLabel()
        label.setWordWrap(True)
        label.setToolTip(
            "这里显示的是 FSW Zero Span 的固定中心频率和 RBW 接收带宽，"
            "不是普通扫频的 Start/Stop 频率范围。通带边界按 Center±RBW/2 展示。"
        )
        layout.addWidget(label)
        self.zero_span_info_label = label

        insert_index = max(0, self.left_layout.count() - 1)
        self.left_layout.insertWidget(insert_index, group)

    def _update_zero_span_info_card(self) -> None:
        label = self.zero_span_info_label
        profile = getattr(self, "profile", None)
        if label is None:
            return
        if profile is None:
            label.setText("等待 Zero Span 参数。")
            return

        center_hz = float(profile.center_frequency_hz)
        rbw_hz = float(profile.rbw_hz)
        lower_hz = center_hz - rbw_hz / 2.0
        upper_hz = center_hz + rbw_hz / 2.0
        vbw_text = "OFF"
        if profile.vbw_enabled:
            vbw_text = f"{profile.vbw_hz/1e6:.6g} MHz"

        waveform = self.current_waveform
        sample_text = "Fs / Nyquist：等待有效 DCM 波形"
        if waveform is not None and len(waveform.time_s) >= 2:
            dt = np.diff(np.asarray(waveform.time_s, dtype=float))
            positive_dt = dt[np.isfinite(dt) & (dt > 0)]
            if len(positive_dt):
                sample_rate_hz = 1.0 / float(np.median(positive_dt))
                sample_text = (
                    f"Fs={sample_rate_hz/1e9:.6g} GSa/s | "
                    f"Nyquist={sample_rate_hz/2e6:.6g} MHz"
                )

        valid = self.current_zero_span is not None and not self.current_zero_span_error
        status = "有效" if valid else "不可计算"
        lines = [
            f"状态：{status} | Span=0 Hz | Detector=RMS | RBW Filter=Gaussian",
            f"Center={center_hz/1e6:.6g} MHz | RBW={rbw_hz/1e6:.6g} MHz | "
            f"3 dB 接收带宽≈{lower_hz/1e6:.6g}~{upper_hz/1e6:.6g} MHz",
            f"VBW={vbw_text} | Scope Analog BW={profile.scope_analog_bandwidth_hz/1e6:.6g} MHz | "
            f"{sample_text}",
        ]
        if self.current_zero_span_error:
            lines.append(f"原因：{self.current_zero_span_error}")
        label.setText("\n".join(lines))

    # ------------------------------------------------------------------
    # Frequency peak table / marker
    # ------------------------------------------------------------------
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
            source_waveform_signature=waveform_signature(
                self.current_waveform.time_s,
                self.current_waveform.voltage_v,
            ),
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

    # ------------------------------------------------------------------
    # Time-domain A/B markers
    # ------------------------------------------------------------------
    @staticmethod
    def _new_time_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(9)
        spin.setRange(-1e9, 1e9)
        spin.setSingleStep(0.01)
        spin.setSuffix(" µs")
        spin.setKeyboardTracking(False)
        return spin

    def _build_time_marker_controls(self) -> None:
        group = QGroupBox("时域 Marker A / B（与 Zero Span 时间轴联动）")
        layout = QVBoxLayout(group)

        marker_a_row = QHBoxLayout()
        self.time_marker_a_enable = QCheckBox("启用 A")
        self.time_marker_a_time_us = self._new_time_spin()
        marker_a_row.addWidget(self.time_marker_a_enable)
        marker_a_row.addWidget(QLabel("时间"))
        marker_a_row.addWidget(self.time_marker_a_time_us, 1)
        layout.addLayout(marker_a_row)

        marker_b_row = QHBoxLayout()
        self.time_marker_b_enable = QCheckBox("启用 B")
        self.time_marker_b_time_us = self._new_time_spin()
        marker_b_row.addWidget(self.time_marker_b_enable)
        marker_b_row.addWidget(QLabel("时间"))
        marker_b_row.addWidget(self.time_marker_b_time_us, 1)
        layout.addLayout(marker_b_row)

        action_row = QHBoxLayout()
        self.time_marker_info_label = QLabel(
            "A/B 未启用。Marker 会吸附到当前波形最近的真实采样点。"
        )
        self.time_marker_info_label.setWordWrap(True)
        clear_btn = QPushButton("清除 A/B")
        clear_btn.clicked.connect(self._clear_time_markers)
        action_row.addWidget(self.time_marker_info_label, 1)
        action_row.addWidget(clear_btn)
        layout.addLayout(action_row)

        for control in (
            self.time_marker_a_enable,
            self.time_marker_b_enable,
        ):
            control.toggled.connect(self._on_time_marker_changed)
        for control in (
            self.time_marker_a_time_us,
            self.time_marker_b_time_us,
        ):
            control.valueChanged.connect(self._on_time_marker_changed)

        insert_index = max(0, self.left_layout.count() - 1)
        self.left_layout.insertWidget(insert_index, group)

    def _sync_time_marker_controls_to_waveform(self) -> None:
        waveform = self.current_waveform
        spins = (self.time_marker_a_time_us, self.time_marker_b_time_us)
        if waveform is None or any(spin is None for spin in spins) or len(waveform.time_s) == 0:
            return

        start_us = float(waveform.time_s[0]) * 1e6
        end_us = float(waveform.time_s[-1]) * 1e6
        if end_us < start_us:
            start_us, end_us = end_us, start_us
        span_us = end_us - start_us

        for spin in spins:
            assert spin is not None
            spin.blockSignals(True)
            try:
                spin.setRange(start_us, end_us)
            finally:
                spin.blockSignals(False)

        if not self._time_marker_defaults_initialized:
            self._time_marker_defaults_initialized = True
            default_a = start_us + 0.25 * span_us
            default_b = start_us + 0.75 * span_us
            for spin, value in zip(spins, (default_a, default_b), strict=True):
                assert spin is not None
                spin.blockSignals(True)
                try:
                    spin.setValue(value)
                finally:
                    spin.blockSignals(False)

    def _time_marker_from_control(
        self,
        enabled: QCheckBox | None,
        spin: QDoubleSpinBox | None,
    ) -> TimeMarker | None:
        waveform = self.current_waveform
        if (
            waveform is None
            or enabled is None
            or spin is None
            or not enabled.isChecked()
            or len(waveform.time_s) == 0
        ):
            return None
        try:
            return time_marker_at_time(
                waveform.time_s,
                waveform.voltage_v,
                spin.value() * 1e-6,
            )
        except ValueError:
            return None

    def _current_time_markers(self) -> tuple[TimeMarker | None, TimeMarker | None]:
        return (
            self._time_marker_from_control(
                self.time_marker_a_enable,
                self.time_marker_a_time_us,
            ),
            self._time_marker_from_control(
                self.time_marker_b_enable,
                self.time_marker_b_time_us,
            ),
        )

    def _update_time_marker_info(self) -> None:
        label = self.time_marker_info_label
        if label is None:
            return
        marker_a, marker_b = self._current_time_markers()
        if marker_a is None and marker_b is None:
            label.setText("A/B 未启用。Marker 会吸附到当前波形最近的真实采样点。")
            return

        parts: list[str] = []
        if marker_a is not None:
            parts.append(f"A: {marker_a.time_s*1e6:.9g} µs / {marker_a.voltage_v:.6g} V")
        if marker_b is not None:
            parts.append(f"B: {marker_b.time_s*1e6:.9g} µs / {marker_b.voltage_v:.6g} V")
        if marker_a is not None and marker_b is not None:
            delta = time_marker_delta(marker_a, marker_b)
            parts.append(
                f"ΔT={delta.delta_time_s*1e6:+.9g} µs | "
                f"ΔV={delta.delta_voltage_v:+.6g} V"
            )
        label.setText(" | ".join(parts))

    def _on_time_marker_changed(self, *_args) -> None:
        self._update_time_marker_info()
        self._redraw(zero_span_error=self.current_zero_span_error)

    def _clear_time_markers(self) -> None:
        controls = (self.time_marker_a_enable, self.time_marker_b_enable)
        for control in controls:
            if control is None:
                continue
            control.blockSignals(True)
            try:
                control.setChecked(False)
            finally:
                control.blockSignals(False)
        self._update_time_marker_info()
        self._redraw(zero_span_error=self.current_zero_span_error)

    @staticmethod
    def _draw_one_time_marker(ax_time, ax_zero, marker: TimeMarker | None, name: str) -> None:
        if marker is None:
            return
        time_xlim = ax_time.get_xlim()
        time_ylim = ax_time.get_ylim()
        zero_xlim = ax_zero.get_xlim()
        zero_ylim = ax_zero.get_ylim()

        x_us = marker.time_s * 1e6
        ax_time.axvline(x_us, linestyle=":", linewidth=1.1)
        ax_time.plot([x_us], [marker.voltage_v], marker="o", markersize=4)
        ax_time.annotate(name, (x_us, marker.voltage_v), xytext=(4, 5), textcoords="offset points")
        ax_zero.axvline(x_us, linestyle=":", linewidth=1.1)

        # Marker overlays are display-only and must not alter fixed/manual/zoom ranges.
        ax_time.set_xlim(time_xlim, auto=False)
        ax_time.set_ylim(time_ylim, auto=False)
        ax_zero.set_xlim(zero_xlim, auto=False)
        ax_zero.set_ylim(zero_ylim, auto=False)

    def _draw_time_marker_overlays(self) -> None:
        if self.current_waveform is None or len(self.figure.axes) < 3:
            return
        marker_a, marker_b = self._current_time_markers()
        ax_time = self.figure.axes[0]
        ax_zero = self.figure.axes[2]
        self._draw_one_time_marker(ax_time, ax_zero, marker_a, "A")
        self._draw_one_time_marker(ax_time, ax_zero, marker_b, "B")

    # ------------------------------------------------------------------
    # One-click analysis export
    # ------------------------------------------------------------------
    def _build_analysis_export_group(self) -> None:
        group = QGroupBox("综合分析导出")
        layout = QVBoxLayout(group)
        note = QLabel(
            "一次导出当前四图 PNG、DCM 时域 CSV、Zero Span CSV、"
            "幅度/相位频谱 CSV 和 analysis_metadata.json。"
        )
        note.setWordWrap(True)
        button = QPushButton("一键导出当前分析")
        button.clicked.connect(self.export_analysis_bundle_dialog)
        layout.addWidget(note)
        layout.addWidget(button)

        insert_index = max(0, self.left_layout.count() - 1)
        self.left_layout.insertWidget(insert_index, group)

    def export_analysis_bundle_dialog(self) -> None:
        if self.current_waveform is None:
            QMessageBox.information(self, "没有分析结果", "当前还没有有效 DCM 波形可导出。")
            return

        directory = QFileDialog.getExistingDirectory(self, "选择综合分析导出目录")
        if not directory:
            return

        try:
            workspace = collect_dcm_analysis_workspace(self)
            workspace["zero_span_valid"] = self.current_zero_span is not None
            workspace["zero_span_error"] = self.current_zero_span_error
            outputs = export_dcm_analysis_bundle(
                directory,
                parameters=self.parameters,
                profile=self.profile,
                waveform=self.current_waveform,
                zero_span=self.current_zero_span,
                spectrum=self._spectrum_from_current_cache(),
                figure=self.figure,
                metadata=workspace,
            )
            self.status_label.setText(
                f"已导出综合分析：{directory} | 共 {len(outputs)} 个文件"
            )
        except Exception as exc:
            QMessageBox.critical(self, "导出综合分析失败", str(exc))

    # ------------------------------------------------------------------
    # Drawing hooks
    # ------------------------------------------------------------------
    def _compute_current_spectrum(self, waveform: DcmSwWaveform) -> DcmSpectrum:
        spectrum = compute_dcm_spectrum(
            waveform.time_s,
            waveform.voltage_v,
            amplitude_floor_dbv=self.SPECTRUM_FLOOR_DBV,
            phase_visible_floor_dbv=self.PHASE_VISIBLE_FLOOR_DBV,
            phase_dynamic_range_db=self.PHASE_DYNAMIC_RANGE_DB,
        )
        self.current_spectrum_frequency_hz = spectrum.frequency_hz
        self.current_spectrum_amplitude_dbv = spectrum.amplitude_dbv
        self.current_spectrum_phase_deg = spectrum.phase_deg
        self.current_phase_visibility_threshold_dbv = spectrum.phase_visibility_threshold_dbv
        return spectrum

    def _draw_frequency_panel(self, ax, waveform: DcmSwWaveform) -> None:
        # Stable entry now owns the production magnitude drawing. Legacy v10 is
        # retained only as a compatibility base for the remaining layout/axis/
        # zoom behavior while those layers are migrated separately.
        spectrum = self._compute_current_spectrum(waveform)
        draw_magnitude_spectrum_panel(
            ax,
            spectrum,
            center_frequency_hz=self.profile.center_frequency_hz,
            rbw_hz=self.profile.rbw_hz,
        )

        # Preserve the established v5/v8/v9 behavior: manual coordinate input
        # affects the current frame only; a normal FFT/data refresh returns to
        # automatic bounds and writes the resulting values back to the controls.
        if hasattr(self, "freq_x_min"):
            self._apply_fixed_axis(
                ax,
                x_min=self.freq_x_min.value(),
                x_max=self.freq_x_max.value(),
                x_step=self.freq_x_step.value(),
                y_min=self.freq_y_min.value(),
                y_max=self.freq_y_max.value(),
                y_step=self.freq_y_step.value(),
            )
        if not getattr(self, "_frequency_manual_redraw_once", False):
            self._apply_frequency_auto_axis(ax)

        self._refresh_peak_table()
        self._update_marker_info()
        self._draw_frequency_marker_line(
            ax,
            self._current_frequency_marker(),
            phase=False,
        )

    def _draw_reserved_panel(self, ax) -> None:
        # Stable entry also owns phase rendering from the exact cached bins
        # produced above. This avoids a second FFT and removes v10's drawing
        # implementation from the production path.
        draw_phase_spectrum_panel(
            ax,
            self._spectrum_from_current_cache(),
            center_frequency_hz=self.profile.center_frequency_hz,
            rbw_hz=self.profile.rbw_hz,
        )
        self._draw_frequency_marker_line(
            ax,
            self._current_frequency_marker(),
            phase=True,
        )

    def _redraw(
        self,
        *,
        zero_span_error: str | None = None,
        dcm_error: str | None = None,
    ) -> None:
        super()._redraw(
            zero_span_error=zero_span_error,
            dcm_error=dcm_error,
        )
        self._update_zero_span_info_card()
        self._sync_time_marker_controls_to_waveform()
        self._update_time_marker_info()
        self._draw_time_marker_overlays()
        self.canvas.draw_idle()


__all__ = ["DcmAnalysisWidget"]
