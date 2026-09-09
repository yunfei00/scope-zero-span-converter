from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QGroupBox, QLabel, QToolButton

from .axis import apply_fixed_y_axis, nice_step
from .controls import DcmAnalysisControls
from .zoom import ZoomState, ZoomTarget


class DcmAnalysisView(DcmAnalysisControls):
    """Versionless construction for the production four-panel analysis view."""

    SPECTRUM_FLOOR_DBV = -300.0
    PHASE_VISIBLE_FLOOR_DBV = -120.0
    PHASE_DYNAMIC_RANGE_DB = 60.0

    def __init__(self, parent=None) -> None:
        # Dynamic redraw/recompute occurs during the common control constructor,
        # so spectrum and zoom state must exist before QWidget construction.
        self.current_spectrum_frequency_hz = np.asarray([], dtype=float)
        self.current_spectrum_amplitude_dbv = np.asarray([], dtype=float)
        self.current_spectrum_phase_deg = np.asarray([], dtype=float)
        self.current_phase_visibility_threshold_dbv = self.PHASE_VISIBLE_FLOOR_DBV

        self._zoom_state = ZoomState()
        # Compatibility attributes used by workspace/tests; ZoomState is the
        # single source of truth.
        self._zoom_ranges = self._zoom_state.ranges
        self._zoom_history = self._zoom_state.history
        self._zoom_selectors: dict[ZoomTarget, object] = {}
        self._zoom_axes: dict[ZoomTarget, object] = {}
        self._zoom_key_cid: int | None = None
        self._zoom_focus_cid: int | None = None

        super().__init__(parent)

        self._build_axis_display_fold()
        self._initialize_axis_values_from_current_data()
        self._build_frequency_axis_controls()
        self._initialize_frequency_axis_values()

        self.canvas.setFocusPolicy(Qt.StrongFocus)
        self.canvas.setToolTip(
            "左上 DCM 时域 / 右上 DCM 完整频域：按住鼠标左键拖框放大；"
            "按空格逐级返回上一次范围。"
        )
        self._zoom_key_cid = self.canvas.mpl_connect(
            "key_press_event", self._on_zoom_key_press
        )
        self._zoom_focus_cid = self.canvas.mpl_connect(
            "button_press_event", self._on_zoom_canvas_press
        )
        self._add_zoom_help_text()

        # Repaint once after all axis controls exist, then attach selectors to
        # the final axes created by that redraw.
        self._redraw(zero_span_error=self.current_zero_span_error)
        self._rebind_zoom_selectors()

    # ------------------------------------------------------------------
    # DCM / Zero Span Y-axis controls (legacy v2/v3 responsibility)
    # ------------------------------------------------------------------
    def _build_axis_display_fold(self) -> None:
        self.axis_display_toggle = QToolButton()
        self.axis_display_toggle.setText("图表坐标轴显示设置（范围 / 方格步进）")
        self.axis_display_toggle.setCheckable(True)
        self.axis_display_toggle.setChecked(False)
        self.axis_display_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.axis_display_toggle.setArrowType(Qt.RightArrow)
        self.axis_display_toggle.toggled.connect(self._toggle_axis_display_panel)

        self.axis_display_panel = QGroupBox()
        self.axis_display_panel.setVisible(False)
        form = QFormLayout(self.axis_display_panel)

        self.dcm_y_min = self._axis_spin(-1e9, 1e9, 6, 1.0)
        self.dcm_y_max = self._axis_spin(-1e9, 1e9, 6, 1.0)
        self.dcm_y_step = self._axis_spin(1e-9, 1e9, 6, 1.0)
        self.zero_y_min = self._axis_spin(-1e9, 1e9, 6, 10.0)
        self.zero_y_max = self._axis_spin(-1e9, 1e9, 6, 10.0)
        self.zero_y_step = self._axis_spin(1e-9, 1e9, 6, 10.0)

        form.addRow("DCM 纵轴最小值 (V)", self.dcm_y_min)
        form.addRow("DCM 纵轴最大值 (V)", self.dcm_y_max)
        form.addRow("DCM 每格步进 (V)", self.dcm_y_step)
        form.addRow("Zero Span 纵轴最小值 (dBm)", self.zero_y_min)
        form.addRow("Zero Span 纵轴最大值 (dBm)", self.zero_y_max)
        form.addRow("Zero Span 每格步进 (dB)", self.zero_y_step)

        for spin in (
            self.dcm_y_min,
            self.dcm_y_max,
            self.dcm_y_step,
            self.zero_y_min,
            self.zero_y_max,
            self.zero_y_step,
        ):
            spin.valueChanged.connect(self._on_axis_display_changed)

        insert_at = max(0, self.left_layout.count() - 1)
        self.left_layout.insertWidget(insert_at, self.axis_display_toggle)
        self.left_layout.insertWidget(insert_at + 1, self.axis_display_panel)

    @staticmethod
    def _axis_spin(
        minimum: float,
        maximum: float,
        decimals: int,
        step: float,
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setKeyboardTracking(True)
        spin.setMinimumWidth(150)
        return spin

    def _toggle_axis_display_panel(self, checked: bool) -> None:
        self.axis_display_panel.setVisible(checked)
        self.axis_display_toggle.setArrowType(
            Qt.DownArrow if checked else Qt.RightArrow
        )

    @staticmethod
    def _nice_bounds(values: np.ndarray, step: float) -> tuple[float, float]:
        finite = np.asarray(values, dtype=float)
        finite = finite[np.isfinite(finite)]
        if len(finite) == 0:
            return -step, step
        low = float(np.min(finite))
        high = float(np.max(finite))
        if math.isclose(low, high):
            low -= step
            high += step
        margin = max((high - low) * 0.08, step * 0.5)
        low = math.floor((low - margin) / step) * step
        high = math.ceil((high + margin) / step) * step
        if high <= low:
            high = low + step
        return low, high

    def _initialize_axis_values_from_current_data(self) -> None:
        dcm_step = 2.0
        zero_step = 10.0
        if self.current_waveform is not None:
            dcm_min, dcm_max = self._nice_bounds(
                self.current_waveform.voltage_v, dcm_step
            )
        else:
            dcm_min, dcm_max = -10.0, 20.0
        if self.current_zero_span is not None:
            zero_min, zero_max = self._nice_bounds(
                self.current_zero_span.amplitude_dbm, zero_step
            )
        else:
            zero_min, zero_max = -120.0, 20.0

        controls_and_values = (
            (self.dcm_y_min, dcm_min),
            (self.dcm_y_max, dcm_max),
            (self.dcm_y_step, dcm_step),
            (self.zero_y_min, zero_min),
            (self.zero_y_max, zero_max),
            (self.zero_y_step, zero_step),
        )
        for control, _value in controls_and_values:
            control.blockSignals(True)
        try:
            for control, value in controls_and_values:
                control.setValue(value)
        finally:
            for control, _value in controls_and_values:
                control.blockSignals(False)

    def _apply_y_axis_settings(
        self,
        ax,
        minimum: float,
        maximum: float,
        step: float,
    ) -> None:
        apply_fixed_y_axis(ax, minimum, maximum, step)

    def _apply_axis_controls_if_ready(self, ax_time, ax_zero) -> None:
        if not hasattr(self, "dcm_y_min"):
            ax_time.grid(True, alpha=0.25)
            ax_zero.grid(True, alpha=0.25)
            return
        self._apply_y_axis_settings(
            ax_time,
            self.dcm_y_min.value(),
            self.dcm_y_max.value(),
            self.dcm_y_step.value(),
        )
        self._apply_y_axis_settings(
            ax_zero,
            self.zero_y_min.value(),
            self.zero_y_max.value(),
            self.zero_y_step.value(),
        )

    # ------------------------------------------------------------------
    # Frequency X/Y controls (legacy v5 construction responsibility)
    # ------------------------------------------------------------------
    def _build_frequency_axis_controls(self) -> None:
        form = self.axis_display_panel.layout()
        if not isinstance(form, QFormLayout):
            raise RuntimeError("图表显示设置面板布局不是 QFormLayout")

        self.freq_x_min = self._axis_spin(-1e9, 1e9, 6, 10.0)
        self.freq_x_max = self._axis_spin(-1e9, 1e9, 6, 10.0)
        self.freq_x_step = self._axis_spin(1e-9, 1e9, 6, 10.0)
        self.freq_y_min = self._axis_spin(-1e9, 1e9, 6, 10.0)
        self.freq_y_max = self._axis_spin(-1e9, 1e9, 6, 10.0)
        self.freq_y_step = self._axis_spin(1e-9, 1e9, 6, 10.0)

        form.addRow("频域 X 最小值 (MHz)", self.freq_x_min)
        form.addRow("频域 X 最大值 (MHz)", self.freq_x_max)
        form.addRow("频域 X 每格步进 (MHz)", self.freq_x_step)
        form.addRow("频域 Y 最小值 (dBV)", self.freq_y_min)
        form.addRow("频域 Y 最大值 (dBV)", self.freq_y_max)
        form.addRow("频域 Y 每格步进 (dB)", self.freq_y_step)

        for spin in (
            self.freq_x_min,
            self.freq_x_max,
            self.freq_x_step,
            self.freq_y_min,
            self.freq_y_max,
            self.freq_y_step,
        ):
            spin.valueChanged.connect(self._on_frequency_axis_changed)

    def _initialize_frequency_axis_values(self) -> None:
        frequency_mhz = np.asarray(self.current_spectrum_frequency_hz, dtype=float) / 1e6
        amplitude_dbv = np.asarray(self.current_spectrum_amplitude_dbv, dtype=float)

        if len(frequency_mhz):
            x_min = float(frequency_mhz[0])
            x_max = float(frequency_mhz[-1])
        else:
            x_min, x_max = 0.0, 1000.0
        x_step = nice_step(max(x_max - x_min, 1.0) / 10.0)

        finite_y = amplitude_dbv[np.isfinite(amplitude_dbv)]
        if len(finite_y):
            raw_min = float(np.min(finite_y))
            raw_max = float(np.max(finite_y))
            y_step = 20.0
            y_min = math.floor(raw_min / y_step) * y_step
            y_max = math.ceil(raw_max / y_step) * y_step
            if y_max <= y_min:
                y_max = y_min + y_step
        else:
            y_min, y_max, y_step = -200.0, 20.0, 20.0

        controls_and_values = (
            (self.freq_x_min, x_min),
            (self.freq_x_max, x_max),
            (self.freq_x_step, x_step),
            (self.freq_y_min, y_min),
            (self.freq_y_max, y_max),
            (self.freq_y_step, y_step),
        )
        for control, _value in controls_and_values:
            control.blockSignals(True)
        try:
            for control, value in controls_and_values:
                control.setValue(value)
        finally:
            for control, _value in controls_and_values:
                control.blockSignals(False)

    # ------------------------------------------------------------------
    # Rectangle-selector construction (legacy v6 responsibility)
    # ------------------------------------------------------------------
    def _add_zoom_help_text(self) -> None:
        form = self.axis_display_panel.layout()
        if not isinstance(form, QFormLayout):
            return
        self.zoom_help_label = QLabel(
            "放大查看：左上 DCM 时域或右上完整频域按住鼠标左键拖出矩形；"
            "可连续多级放大，按空格逐级返回。放大不会修改这里保存的基础坐标参数。"
        )
        self.zoom_help_label.setWordWrap(True)
        form.addRow(self.zoom_help_label)


__all__ = ["DcmAnalysisView"]
