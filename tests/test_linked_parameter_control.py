import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.linked_parameter_control import LinkedDoubleControl


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_linked_double_control_syncs_slider_and_spin_both_directions(qapp):
    del qapp
    control = LinkedDoubleControl(
        -100.0,
        100.0,
        3,
        0.1,
        slider_min=-10.0,
        slider_max=10.0,
    )

    # 即使 QDoubleSpinBox 初值本来就是 0，setValue 也应强制同步滑块到中点。
    control.setValue(0.0)
    assert control.value() == pytest.approx(0.0)
    assert control.slider.value() == pytest.approx(5000, abs=1)

    # 滑块 -> 数值框。
    control.slider.setValue(7500)
    assert control.value() == pytest.approx(5.0, abs=0.01)

    # 数值框 -> 滑块。
    control.spin.setValue(-5.0)
    assert control.value() == pytest.approx(-5.0)
    assert control.slider.value() == pytest.approx(2500, abs=2)


def test_linked_double_control_expands_soft_slider_range_for_precise_input(qapp):
    del qapp
    control = LinkedDoubleControl(
        -1000.0,
        1000.0,
        3,
        0.1,
        slider_min=-10.0,
        slider_max=10.0,
    )

    # 输入框的硬范围比滑块常用软范围更大。输入 50 V 时不能被滑块截成 10 V。
    control.setValue(50.0)
    assert control.value() == pytest.approx(50.0)
    assert 0 < control.slider.value() <= 10000

    # 扩展后继续拖动仍应保持双向联动。
    old_value = control.value()
    control.slider.setValue(max(0, control.slider.value() - 500))
    assert control.value() != pytest.approx(old_value)
