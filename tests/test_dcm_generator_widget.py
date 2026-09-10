from __future__ import annotations

import ast
from dataclasses import asdict
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QWidget

from scope_zero_span_converter.dcm_generator.widget import DcmSwGeneratorWidget
import scope_zero_span_converter.dcm_generator.widget as generator_widget_module
from scope_zero_span_converter.dcm_sw_generator import DcmSwParameters
from scope_zero_span_converter.dcm_sw_waveform_io import parameter_sidecar_for


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _compact_parameters(**changes) -> DcmSwParameters:
    values = {
        "time_origin_s": 5e-6,
        "total_duration_s": 12e-6,
        "switching_start_s": 6.5e-6,
        "sample_rate_hz": 200e6,
        "noise_rms_v": 0.0,
    }
    values.update(changes)
    return DcmSwParameters(**values)


def _fire_debounced_generation(widget: DcmSwGeneratorWidget) -> None:
    assert widget._auto_timer.isActive()
    widget._auto_timer.stop()
    widget._auto_timer.timeout.emit()


def test_formal_generator_is_direct_qwidget_without_versioned_imports(qapp):
    del qapp
    assert QWidget in DcmSwGeneratorWidget.mro()
    modules = {base.__module__ for base in DcmSwGeneratorWidget.mro()}
    assert "scope_zero_span_converter.dcm_sw_generator_widget_v2" not in modules
    assert "scope_zero_span_converter.dcm_sw_generator_widget_v3" not in modules

    path = Path(generator_widget_module.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(
        name.endswith(("dcm_sw_generator_widget_v2", "dcm_sw_generator_widget_v3"))
        for name in imports
    )

    widget = DcmSwGeneratorWidget()
    assert widget.current_waveform is not None
    assert widget.current_waveform.parameters == widget.collect_parameters()


def test_auto_and_manual_generation_use_current_controls(qapp):
    del qapp
    widget = DcmSwGeneratorWidget()
    original = widget.current_waveform
    assert original is not None

    widget.high_v.spin.setValue(original.parameters.on_high_voltage_v + 2.0)
    _fire_debounced_generation(widget)
    automatic = widget.current_waveform
    assert automatic is not None and automatic is not original
    assert automatic.parameters.on_high_voltage_v == pytest.approx(14.0)
    assert not np.array_equal(automatic.voltage_v, original.voltage_v)

    widget.auto_generate_check.setChecked(False)
    widget.high_v.spin.setValue(16.0)
    assert widget._auto_timer.isActive() is False
    assert widget.current_waveform is automatic

    widget.generate_waveform()
    manual = widget.current_waveform
    assert manual is not None and manual is not automatic
    assert manual.parameters.on_high_voltage_v == pytest.approx(16.0)


def test_parameter_roundtrip_preserves_absolute_time_axis(qapp):
    del qapp
    widget = DcmSwGeneratorWidget()
    parameters = _compact_parameters(
        on_high_voltage_v=17.25,
        fall_spike_amplitude_v=-6.5,
        random_seed=2468,
    )

    widget.apply_parameters(parameters, schedule_generate=False)
    assert asdict(widget.collect_parameters()) == pytest.approx(asdict(parameters))

    widget.generate_waveform()
    waveform = widget.current_waveform
    assert waveform is not None
    assert waveform.time_s[0] == pytest.approx(5e-6, abs=1e-18)
    assert waveform.time_s[-1] == pytest.approx(17e-6, abs=1e-12)
    assert waveform.events.rise_start_s == pytest.approx(6.5e-6, abs=1e-18)


def test_formal_widget_saves_and_loads_parameter_json(qapp, tmp_path, monkeypatch):
    del qapp
    widget = DcmSwGeneratorWidget()
    expected = _compact_parameters(on_high_voltage_v=18.5, random_seed=77)
    widget.apply_parameters(expected, schedule_generate=False)

    path = tmp_path / "customer-generator.json"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(path), "JSON (*.json)"),
    )
    widget.save_parameters_dialog()
    assert path.exists()

    widget.apply_parameters(DcmSwParameters(), schedule_generate=False)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(path), "JSON (*.json)"),
    )
    widget.load_parameters_dialog()

    assert asdict(widget.collect_parameters()) == pytest.approx(asdict(expected))
    assert widget.current_waveform is not None
    assert widget.current_waveform.time_s[0] == pytest.approx(5e-6, abs=1e-18)


def test_saved_historical_waveform_survives_until_next_parameter_change(
    qapp,
    tmp_path,
    monkeypatch,
):
    widget = DcmSwGeneratorWidget()
    parameters = _compact_parameters(on_high_voltage_v=15.0, random_seed=99)
    widget.apply_parameters(parameters, schedule_generate=False)
    widget.generate_waveform()

    csv_path = tmp_path / "saved-history.csv"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(csv_path), "CSV (*.csv)"),
    )
    widget.save_waveform_dialog()
    sidecar = parameter_sidecar_for(csv_path)
    assert csv_path.exists() and sidecar.exists()

    frame = pd.read_csv(csv_path)
    changed_index = len(frame) // 2
    frame.loc[changed_index, "voltage_v"] += 7.0
    frame.to_csv(csv_path, index=False)
    saved_voltage = frame["voltage_v"].to_numpy(dtype=float)

    loaded = widget.load_saved_waveform(csv_path)
    np.testing.assert_allclose(loaded.voltage_v, saved_voltage, rtol=0, atol=1e-12)
    assert widget._auto_timer.isActive() is False
    qapp.processEvents()
    assert widget.current_waveform is loaded
    np.testing.assert_allclose(
        widget.current_waveform.voltage_v,
        saved_voltage,
        rtol=0,
        atol=1e-12,
    )

    widget.high_v.spin.setValue(16.0)
    _fire_debounced_generation(widget)
    regenerated = widget.current_waveform
    assert regenerated is not None and regenerated is not loaded
    assert regenerated.parameters.on_high_voltage_v == pytest.approx(16.0)
    assert regenerated.voltage_v[changed_index] != pytest.approx(
        saved_voltage[changed_index]
    )


def test_manual_sidecar_selection_and_research_signal_remain_available(
    qapp,
    tmp_path,
    monkeypatch,
):
    del qapp
    widget = DcmSwGeneratorWidget()
    csv_path = tmp_path / "without-sidecar.csv"
    selected = tmp_path / "manually-selected.json"

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.Yes,
    )
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(selected), "JSON (*.json)"),
    )
    assert widget._choose_parameters_path(csv_path) == selected

    received = []
    widget.waveform_ready_for_research.connect(received.append)
    widget.send_to_research()
    assert received == [widget.current_waveform]
