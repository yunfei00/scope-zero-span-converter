from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QSlider,
    QSpinBox,
    QWidget,
)


_SLIDER_STEPS = 10_000


class LinkedDoubleControl(QWidget):
    """水平滑块 + 双精度输入框。

    - 滑块用于快速连续调参；
    - 输入框用于精确输入；
    - 两者双向实时同步；
    - slider_min/slider_max 是交互“软范围”，不是参数硬限制；
    - 输入框输入超出软范围的合法值时，软范围自动扩展以容纳该值。
    """

    valueChanged = Signal(float)

    def __init__(
        self,
        minimum: float,
        maximum: float,
        decimals: int,
        step: float,
        *,
        slider_min: float | None = None,
        slider_max: float | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        if maximum <= minimum:
            raise ValueError("maximum 必须大于 minimum")

        self._hard_min = float(minimum)
        self._hard_max = float(maximum)
        self._soft_min = float(slider_min if slider_min is not None else minimum)
        self._soft_max = float(slider_max if slider_max is not None else maximum)
        self._soft_min = max(self._hard_min, self._soft_min)
        self._soft_max = min(self._hard_max, self._soft_max)
        if self._soft_max <= self._soft_min:
            self._soft_min = self._hard_min
            self._soft_max = self._hard_max

        self._syncing = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, _SLIDER_STEPS)
        self.slider.setTracking(True)
        self.slider.setMinimumWidth(150)

        self.spin = QDoubleSpinBox()
        self.spin.setRange(self._hard_min, self._hard_max)
        self.spin.setDecimals(decimals)
        self.spin.setSingleStep(step)
        self.spin.setKeyboardTracking(True)
        self.spin.setMinimumWidth(125)

        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spin, 0)

        self.slider.valueChanged.connect(self._on_slider_changed)
        self.spin.valueChanged.connect(self._on_spin_changed)

    def value(self) -> float:
        return float(self.spin.value())

    def setValue(self, value: float) -> None:  # noqa: N802 - Qt API compatibility
        self.spin.setValue(float(value))

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        super().setEnabled(enabled)
        self.slider.setEnabled(enabled)
        self.spin.setEnabled(enabled)

    def _expand_soft_range_for(self, value: float) -> None:
        if self._soft_min <= value <= self._soft_max:
            return

        width = max(self._soft_max - self._soft_min, abs(value) * 0.1, 1e-12)
        if value < self._soft_min:
            new_min = value - width * 0.15
            self._soft_min = max(self._hard_min, new_min)
        else:
            new_max = value + width * 0.15
            self._soft_max = min(self._hard_max, new_max)

        if self._soft_max <= self._soft_min:
            self._soft_min = self._hard_min
            self._soft_max = self._hard_max

    def _slider_to_value(self, slider_value: int) -> float:
        ratio = slider_value / _SLIDER_STEPS
        return self._soft_min + ratio * (self._soft_max - self._soft_min)

    def _value_to_slider(self, value: float) -> int:
        self._expand_soft_range_for(value)
        width = self._soft_max - self._soft_min
        if width <= 0:
            return 0
        ratio = (value - self._soft_min) / width
        ratio = max(0.0, min(1.0, ratio))
        return int(round(ratio * _SLIDER_STEPS))

    def _on_slider_changed(self, slider_value: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            value = self._slider_to_value(slider_value)
            self.spin.setValue(value)
        finally:
            self._syncing = False
        self.valueChanged.emit(self.value())

    def _on_spin_changed(self, value: float) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self.slider.setValue(self._value_to_slider(float(value)))
        finally:
            self._syncing = False
        self.valueChanged.emit(float(value))


class LinkedIntControl(QWidget):
    """整数版水平滑块 + 输入框双向联动控件。"""

    valueChanged = Signal(int)

    def __init__(
        self,
        minimum: int,
        maximum: int,
        *,
        slider_min: int | None = None,
        slider_max: int | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        if maximum <= minimum:
            raise ValueError("maximum 必须大于 minimum")

        self._hard_min = int(minimum)
        self._hard_max = int(maximum)
        self._soft_min = max(self._hard_min, int(slider_min if slider_min is not None else minimum))
        self._soft_max = min(self._hard_max, int(slider_max if slider_max is not None else maximum))
        if self._soft_max <= self._soft_min:
            self._soft_min = self._hard_min
            self._soft_max = self._hard_max
        self._syncing = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, _SLIDER_STEPS)
        self.slider.setTracking(True)
        self.slider.setMinimumWidth(150)

        self.spin = QSpinBox()
        self.spin.setRange(self._hard_min, self._hard_max)
        self.spin.setKeyboardTracking(True)
        self.spin.setMinimumWidth(125)

        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spin, 0)

        self.slider.valueChanged.connect(self._on_slider_changed)
        self.spin.valueChanged.connect(self._on_spin_changed)

    def value(self) -> int:
        return int(self.spin.value())

    def setValue(self, value: int) -> None:  # noqa: N802
        self.spin.setValue(int(value))

    def _expand_soft_range_for(self, value: int) -> None:
        if self._soft_min <= value <= self._soft_max:
            return
        width = max(self._soft_max - self._soft_min, abs(value) // 10, 1)
        if value < self._soft_min:
            self._soft_min = max(self._hard_min, value - max(1, width // 6))
        else:
            self._soft_max = min(self._hard_max, value + max(1, width // 6))

    def _slider_to_value(self, slider_value: int) -> int:
        ratio = slider_value / _SLIDER_STEPS
        return int(round(self._soft_min + ratio * (self._soft_max - self._soft_min)))

    def _value_to_slider(self, value: int) -> int:
        self._expand_soft_range_for(value)
        width = self._soft_max - self._soft_min
        if width <= 0:
            return 0
        ratio = (value - self._soft_min) / width
        ratio = max(0.0, min(1.0, ratio))
        return int(round(ratio * _SLIDER_STEPS))

    def _on_slider_changed(self, slider_value: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self.spin.setValue(self._slider_to_value(slider_value))
        finally:
            self._syncing = False
        self.valueChanged.emit(self.value())

    def _on_spin_changed(self, value: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self.slider.setValue(self._value_to_slider(int(value)))
        finally:
            self._syncing = False
        self.valueChanged.emit(int(value))
