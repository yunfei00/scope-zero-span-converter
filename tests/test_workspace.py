from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_analysis.widget import DcmAnalysisWidget
from scope_zero_span_converter.workspace import (
    apply_dcm_analysis_workspace,
    collect_dcm_analysis_workspace,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_dcm_analysis_workspace_roundtrip_without_zoom_history(qapp, tmp_path):
    del qapp
    source = DcmAnalysisWidget()

    source.parameters.on_high_voltage_v = 15.25
    source._apply_parameters_to_controls(source.parameters)
    source.profile.center_frequency_hz = 180e6
    source.profile.rbw_hz = 8e6
    source._apply_profile_to_controls(source.profile)
    source._recompute()

    source.dcm_y_min.setValue(-8.0)
    source.dcm_y_max.setValue(22.0)
    source.dcm_y_step.setValue(2.0)
    source.zero_y_min.setValue(-90.0)
    source.zero_y_max.setValue(5.0)
    source.zero_y_step.setValue(5.0)

    source.freq_x_min.setValue(20.0)
    source.freq_x_max.setValue(300.0)
    source.freq_x_step.setValue(20.0)
    source.freq_y_min.setValue(-100.0)
    source.freq_y_max.setValue(10.0)
    source.freq_y_step.setValue(10.0)

    source.zero_span_toggle.setChecked(True)
    source.axis_display_toggle.setChecked(True)
    source.selected_marker_frequency_hz = 60e6
    source.time_marker_a_time_us.setValue(4.0)
    source.time_marker_b_time_us.setValue(8.0)
    source.time_marker_a_enable.setChecked(True)
    source.time_marker_b_enable.setChecked(True)

    source.current_dcm_parameters_path = str(tmp_path / "customer_dcm.json")
    source.current_zero_span_profile_path = str(tmp_path / "customer_zero_span.json")

    state = collect_dcm_analysis_workspace(source)

    assert state["schema_version"] == 2
    assert "zoom" not in state
    assert "waveform" not in state
    assert state["dcm_parameters"]["on_high_voltage_v"] == pytest.approx(15.25)
    assert state["zero_span_profile"]["center_frequency_hz"] == pytest.approx(180e6)
    assert state["axis"]["freq_x_min"] == pytest.approx(20.0)
    assert state["markers"]["time_a_enabled"] is True
    assert state["recent_files"]["dcm_parameters_path"].endswith("customer_dcm.json")
    assert state["recent_files"]["zero_span_profile_path"].endswith(
        "customer_zero_span.json"
    )

    restored = DcmAnalysisWidget()
    assert apply_dcm_analysis_workspace(restored, state) is True

    assert restored.parameters.on_high_voltage_v == pytest.approx(15.25)
    assert restored.profile.center_frequency_hz == pytest.approx(180e6)
    assert restored.profile.rbw_hz == pytest.approx(8e6)
    assert restored.dcm_y_min.value() == pytest.approx(-8.0)
    assert restored.dcm_y_max.value() == pytest.approx(22.0)
    assert restored.freq_x_min.value() == pytest.approx(20.0)
    assert restored.freq_x_max.value() == pytest.approx(300.0)
    assert restored.zero_span_toggle.isChecked() is True
    assert restored.axis_display_toggle.isChecked() is True
    assert restored.selected_marker_frequency_hz == pytest.approx(60e6)
    assert restored.time_marker_a_enable.isChecked() is True
    assert restored.time_marker_b_enable.isChecked() is True
    assert restored.time_marker_a_time_us.value() == pytest.approx(4.0)
    assert restored.time_marker_b_time_us.value() == pytest.approx(8.0)
    assert restored.current_dcm_parameters_path == source.current_dcm_parameters_path
    assert restored.current_zero_span_profile_path == source.current_zero_span_profile_path


def test_workspace_restore_keeps_schema_v1_compatible(qapp):
    del qapp
    source = DcmAnalysisWidget()
    state = collect_dcm_analysis_workspace(source)
    state["schema_version"] = 1
    state.pop("recent_files", None)

    restored = DcmAnalysisWidget()
    restored.current_dcm_parameters_path = "previous.json"
    restored.current_zero_span_profile_path = "previous_zero.json"

    assert apply_dcm_analysis_workspace(restored, state) is True
    # Schema v1 had no recent-file section; restoring it must not invent or
    # overwrite paths and must still restore the physical workspace normally.
    assert restored.current_dcm_parameters_path == "previous.json"
    assert restored.current_zero_span_profile_path == "previous_zero.json"
    assert restored.parameters.on_high_voltage_v == pytest.approx(
        source.parameters.on_high_voltage_v
    )


def test_workspace_restore_ignores_unknown_future_fields(qapp):
    del qapp
    widget = DcmAnalysisWidget()
    state = collect_dcm_analysis_workspace(widget)
    state["future_section"] = {"anything": 1}
    state["dcm_parameters"]["future_parameter"] = 123
    state["zero_span_profile"]["future_profile_parameter"] = 456
    state["recent_files"]["future_file"] = "future.dat"

    assert apply_dcm_analysis_workspace(widget, state) is True
