from __future__ import annotations

from typing import Literal

from matplotlib.widgets import RectangleSelector
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QFormLayout

from .dcm_zero_span_widget_v5 import DcmZeroSpanWidget as FrequencyAxisDcmZeroSpanWidget


ZoomTarget = Literal["time", "frequency"]
ZoomBounds = tuple[tuple[float, float], tuple[float, float]]


class DcmZeroSpanWidget(FrequencyAxisDcmZeroSpanWidget):
    """四格联动页：DCM 时域 / 完整频域支持鼠标框选放大。

    交互规则：
    - 左上 DCM SW 时域：鼠标左键拖矩形，同时放大 X/Y；由于和左下 Zero Span
      共享时间 X 轴，Zero Span 会同步跟随相同时间窗口；
    - 右上 DCM 完整频域：鼠标左键拖矩形，同时放大频率 X 与幅度 Y；
    - 可连续多级放大；按 Space 逐级撤销最近一次放大；
    - 放大属于临时查看状态，不写回左侧基础坐标 Min/Max/Step；
    - DCM / Zero Span 重新计算后保持当前放大窗口；手工修改对应基础坐标设置时
      清除该图的临时放大状态，以新的基础范围为准。
    """

    def __init__(self, parent=None) -> None:
        # 父类初始化过程中会动态调用本类 _redraw，因此缩放状态必须提前存在。
        self._zoom_ranges: dict[ZoomTarget, ZoomBounds | None] = {
            "time": None,
            "frequency": None,
        }
        self._zoom_history: list[tuple[ZoomTarget, ZoomBounds | None]] = []
        self._zoom_selectors: dict[ZoomTarget, RectangleSelector] = {}
        self._zoom_axes: dict[ZoomTarget, object] = {}
        self._zoom_key_cid: int | None = None
        self._zoom_focus_cid: int | None = None

        super().__init__(parent)

        self.canvas.setFocusPolicy(Qt.StrongFocus)
        self.canvas.setToolTip(
            "左上 DCM 时域 / 右上 DCM 完整频域：按住鼠标左键拖框放大；"
            "按空格逐级返回上一次范围。"
        )
        self._zoom_key_cid = self.canvas.mpl_connect("key_press_event", self._on_zoom_key_press)
        self._zoom_focus_cid = self.canvas.mpl_connect(
            "button_press_event", self._on_zoom_canvas_press
        )
        self._add_zoom_help_text()
        self._rebind_zoom_selectors()

    # ------------------------------------------------------------------
    # Zoom help / lifecycle
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

    def _disconnect_zoom_selectors(self) -> None:
        for selector in self._zoom_selectors.values():
            try:
                selector.set_active(False)
                selector.disconnect_events()
            except Exception:
                pass
        self._zoom_selectors.clear()
        self._zoom_axes.clear()

    def _rebind_zoom_selectors(self) -> None:
        """Figure 每次 clear/redraw 后 axes 都会重建，因此 selector 也必须重绑。"""
        self._disconnect_zoom_selectors()
        if self.current_waveform is None or len(self.figure.axes) < 2:
            return

        ax_time = self.figure.axes[0]
        ax_frequency = self.figure.axes[1]
        self._zoom_axes = {
            "time": ax_time,
            "frequency": ax_frequency,
        }

        self._zoom_selectors["time"] = RectangleSelector(
            ax_time,
            lambda eclick, erelease: self._on_zoom_rectangle(
                "time", eclick, erelease
            ),
            useblit=False,
            button=[1],
            minspanx=0,
            minspany=0,
            spancoords="data",
            interactive=False,
        )
        self._zoom_selectors["frequency"] = RectangleSelector(
            ax_frequency,
            lambda eclick, erelease: self._on_zoom_rectangle(
                "frequency", eclick, erelease
            ),
            useblit=False,
            button=[1],
            minspanx=0,
            minspany=0,
            spancoords="data",
            interactive=False,
        )

    # ------------------------------------------------------------------
    # Zoom state
    # ------------------------------------------------------------------
    @staticmethod
    def _normalized_bounds(a: float, b: float) -> tuple[float, float] | None:
        low = float(min(a, b))
        high = float(max(a, b))
        scale = max(abs(low), abs(high), 1.0)
        if high - low <= scale * 1e-12:
            return None
        return low, high

    def _on_zoom_rectangle(self, target: ZoomTarget, eclick, erelease) -> None:
        if (
            eclick is None
            or erelease is None
            or eclick.xdata is None
            or eclick.ydata is None
            or erelease.xdata is None
            or erelease.ydata is None
        ):
            return

        x_bounds = self._normalized_bounds(eclick.xdata, erelease.xdata)
        y_bounds = self._normalized_bounds(eclick.ydata, erelease.ydata)
        if x_bounds is None or y_bounds is None:
            return

        previous = self._zoom_ranges[target]
        self._zoom_history.append((target, previous))
        self._zoom_ranges[target] = (x_bounds, y_bounds)
        self.canvas.setFocus()
        self._redraw(zero_span_error=self.current_zero_span_error)

    def _on_zoom_canvas_press(self, event) -> None:
        if event is None:
            return
        if event.inaxes in self._zoom_axes.values():
            self.canvas.setFocus()

    def _on_zoom_key_press(self, event) -> None:
        key = getattr(event, "key", None)
        if key not in {" ", "space"}:
            return
        self._undo_last_zoom()

    def _undo_last_zoom(self) -> None:
        if not self._zoom_history:
            return
        target, previous = self._zoom_history.pop()
        self._zoom_ranges[target] = previous
        self._redraw(zero_span_error=self.current_zero_span_error)

    def _clear_zoom_target(self, target: ZoomTarget) -> None:
        self._zoom_ranges[target] = None
        self._zoom_history = [
            entry for entry in self._zoom_history if entry[0] != target
        ]

    def _apply_zoom_ranges_if_ready(self) -> None:
        if len(self.figure.axes) < 2:
            return

        ax_time = self.figure.axes[0]
        ax_frequency = self.figure.axes[1]

        time_zoom = self._zoom_ranges["time"]
        if time_zoom is not None:
            (x_min, x_max), (y_min, y_max) = time_zoom
            # ax_time 与左下 Zero Span sharex，因此这里设置时左下时间范围同步变化。
            ax_time.set_xlim(x_min, x_max, auto=False)
            ax_time.set_ylim(y_min, y_max, auto=False)
            ax_time.set_autoscalex_on(False)
            ax_time.set_autoscaley_on(False)

        frequency_zoom = self._zoom_ranges["frequency"]
        if frequency_zoom is not None:
            (x_min, x_max), (y_min, y_max) = frequency_zoom
            ax_frequency.set_xlim(x_min, x_max, auto=False)
            ax_frequency.set_ylim(y_min, y_max, auto=False)
            ax_frequency.set_autoscalex_on(False)
            ax_frequency.set_autoscaley_on(False)

    # ------------------------------------------------------------------
    # Base-axis changes cancel only the related temporary zoom
    # ------------------------------------------------------------------
    def _on_axis_display_changed(self, *_args) -> None:
        sender = self.sender()
        dcm_axis_controls = {
            getattr(self, "dcm_y_min", None),
            getattr(self, "dcm_y_max", None),
            getattr(self, "dcm_y_step", None),
        }
        # sender=None covers tests/manual method calls and means treat as explicit base reset.
        if sender is None or sender in dcm_axis_controls:
            self._clear_zoom_target("time")
        super()._on_axis_display_changed(*_args)

    def _on_frequency_axis_changed(self, *_args) -> None:
        self._clear_zoom_target("frequency")
        super()._on_frequency_axis_changed(*_args)

    # ------------------------------------------------------------------
    # Redraw: parent draws full/base views first, then transient zoom overlays
    # ------------------------------------------------------------------
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
        self._apply_zoom_ranges_if_ready()
        self.canvas.draw_idle()
        self._rebind_zoom_selectors()
