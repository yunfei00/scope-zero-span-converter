from __future__ import annotations

import ast
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from scope_zero_span_converter.dcm_extractor.widget import DcmParameterExtractorWidget
from scope_zero_span_converter.dcm_sw_generator import (
    DcmSwParameters,
    generate_dcm_sw_waveform,
)
import scope_zero_span_converter.dcm_extractor.widget as widget_module
import scope_zero_span_converter.dcm_extractor.worker as worker_module


LEGACY_MODULES = {
    "scope_zero_span_converter.dcm_parameter_extractor_widget",
    "scope_zero_span_converter.dcm_parameter_extractor_widget_v2",
    "scope_zero_span_converter.dcm_parameter_extractor_widget_v3",
    "scope_zero_span_converter.dcm_parameter_extractor_widget_v5",
    "scope_zero_span_converter.dcm_parameter_extractor_widget_v6",
    "scope_zero_span_converter.dcm_parameter_extractor_widget_v7",
}


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _waveform():
    return generate_dcm_sw_waveform(
        DcmSwParameters(
            time_origin_s=5e-6,
            total_duration_s=8e-6,
            switching_start_s=5.8e-6,
            rise_time_s=50e-9,
            on_time_s=1.2e-6,
            fall_time_s=60e-9,
            freewheel_time_s=1.0e-6,
            spike_ringing_frequency_hz=25e6,
            discontinuous_resonance_frequency_hz=4e6,
            sample_rate_hz=250e6,
            noise_rms_v=0.01,
            random_seed=77,
        )
    )


def _formal_widget(qapp) -> DcmParameterExtractorWidget:
    del qapp
    waveform = _waveform()
    widget = DcmParameterExtractorWidget()
    widget.set_waveform(waveform.time_s, waveform.voltage_v, source_name="formal-test")
    return widget


class _CapturingPool:
    def __init__(self) -> None:
        self.tasks = []

    def start(self, task) -> None:
        self.tasks.append(task)


def test_formal_extractor_has_version_free_mro_and_import_graph(qapp):
    del qapp
    modules = {base.__module__ for base in DcmParameterExtractorWidget.mro()}
    assert QWidget in DcmParameterExtractorWidget.mro()
    assert not modules & LEGACY_MODULES

    path = Path(widget_module.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any("dcm_parameter_extractor_widget" in name for name in imports)


def test_formal_extractor_owns_explicit_controls_and_state(qapp):
    del qapp
    widget = DcmParameterExtractorWidget()
    for name in (
        "input_group",
        "input_layout",
        "load_button",
        "rerun_button",
        "global_refine_btn",
        "restore_all_btn",
        "use_global_all_btn",
        "save_reconstruction_csv_btn",
    ):
        assert getattr(widget, name) is not None
    assert widget.waveform_path is None
    assert widget.result is None
    assert widget.ringing_result is None
    assert widget.dcm_result is None
    assert widget.global_result is None
    assert widget.current_parameters is None
    assert widget.parameter_controls == {}


def test_formal_staged_extraction_builds_unified_parameters_and_absolute_origin(qapp):
    widget = _formal_widget(qapp)
    assert widget.result is not None
    assert widget.ringing_result is not None
    assert widget.dcm_result is not None
    assert widget.current_parameters is not None
    assert widget.current_fit_result is not None
    assert widget.current_parameters.time_origin_s == pytest.approx(5e-6, abs=1e-18)
    assert widget.global_refine_btn.isEnabled()
    assert set(widget.parameter_controls) == {
        "baseline_voltage_v",
        "on_high_voltage_v",
        "freewheel_low_voltage_v",
        "switching_start_s",
        "rise_time_s",
        "on_time_s",
        "fall_time_s",
        "freewheel_time_s",
        "rise_spike_amplitude_v",
        "fall_spike_amplitude_v",
        "spike_ringing_frequency_hz",
        "spike_decay_rate_per_s",
        "discontinuous_initial_amplitude_v",
        "discontinuous_resonance_frequency_hz",
        "discontinuous_decay_rate_per_s",
    }

    labels = [line.get_label() for line in widget.figure.axes[0].lines]
    assert "基础 + 尖峰/寄生振铃拟合" in labels
    assert "基础 + 尖峰/振铃 + DCM 完整拟合" in labels
    assert "生成器同源当前重建波形" in labels


def test_formal_manual_edit_debounce_and_restore_are_generator_unified(qapp):
    widget = _formal_widget(qapp)
    assert widget.current_parameters is not None
    assert widget.current_fit_result is not None
    automatic_on_time_s = widget.result.on_time_s
    previous_fit = widget.current_fit_result

    control = widget.parameter_controls["on_time_s"]
    changed_us = control.value() + 0.2
    control.setValue(changed_us)
    widget._on_parameter_changed("on_time_s", changed_us)
    assert widget._parameter_timer.isActive()
    assert widget.current_parameters.on_time_s == pytest.approx(changed_us * 1e-6)

    widget._parameter_timer.stop()
    widget._parameter_timer.timeout.emit()
    assert widget.current_fit_result is not None
    assert widget.current_fit_result is not previous_fit

    widget._restore_all_auto_values()
    assert widget.current_parameters is not None
    assert widget.current_parameters.on_time_s == pytest.approx(automatic_on_time_s)
    assert widget.current_parameters.time_origin_s == pytest.approx(5e-6, abs=1e-18)


def test_formal_later_stage_failure_preserves_valid_earlier_results(
    qapp, monkeypatch
):
    del qapp
    waveform = _waveform()
    widget = DcmParameterExtractorWidget()

    def fail_ringing(*args, **kwargs):
        del args, kwargs
        raise ValueError("synthetic ringing failure")

    monkeypatch.setattr(widget_module, "extract_dcm_edge_ringing", fail_ringing)
    widget.set_waveform(waveform.time_s, waveform.voltage_v, source_name="partial")

    assert widget.result is not None
    assert widget.ringing_result is None
    assert widget.ringing_error == "synthetic ringing failure"
    assert widget.current_parameters is not None
    assert widget.current_fit_result is not None


def test_formal_stale_global_refinement_result_is_rejected(qapp):
    widget = _formal_widget(qapp)
    pool = _CapturingPool()
    widget._global_refinement_pool = pool
    widget.run_global_refinement()
    assert len(pool.tasks) == 1
    request_id = widget._global_refinement_active_request_id
    assert request_id is not None

    widget.result = object()
    widget._on_global_refinement_finished(request_id, object())

    assert widget.global_result is None
    assert widget._global_refinement_active_request_id is None
    assert "已丢弃" in widget.status_label.text()


def test_current_global_refinement_result_maps_back_to_generator_parameters(qapp):
    widget = _formal_widget(qapp)
    pool = _CapturingPool()
    widget._global_refinement_pool = pool
    widget.run_global_refinement()
    task = pool.tasks[0]
    task.max_iterations = 1
    task.max_optimization_points = 1_500
    task.run()

    assert widget.global_result is not None
    assert widget.current_parameters is not None
    assert widget.current_fit_result is not None
    assert widget.current_parameters.time_origin_s == pytest.approx(5e-6, abs=1e-18)
    assert widget.current_parameters.baseline_voltage_v == pytest.approx(
        widget.global_result.baseline_voltage_v
    )
    assert widget._global_refinement_active_request_id is None
    assert widget.use_global_all_btn.isEnabled()


def test_formal_json_export_keeps_stable_semantics(qapp, tmp_path):
    widget = _formal_widget(qapp)
    output = widget.save_result(tmp_path / "formal-result")
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert output.suffix == ".json"
    assert payload["basic"] is not None
    assert payload["edge_ringing"] is not None
    assert payload["discontinuous_resonance"] is not None
    assert payload["global_refinement"] is None
    assert payload["current_generator_parameters"]["time_origin_s"] == pytest.approx(5e-6)
    assert payload["current_generator_fit"]["parameters"]["time_origin_s"] == pytest.approx(
        5e-6
    )


def test_global_worker_module_has_no_qwidget_or_gui_event_pump():
    path = Path(worker_module.__file__)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "PySide6.QtWidgets" not in imported_modules
    assert "QWidget" not in source
    assert "QApplication.processEvents" not in source
    assert "refine_dcm_parameters_globally" in source
