from __future__ import annotations

import json
import os
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
import pytest
from matplotlib.figure import Figure
from PySide6.QtWidgets import QApplication

from scope_zero_span_converter.dcm_analysis.exporter import export_dcm_analysis_bundle
from scope_zero_span_converter.dcm_analysis.snapshot import (
    ANALYSIS_UPDATING_MESSAGE,
    AnalysisSnapshotConsistencyError,
    validate_analysis_snapshot,
)
from scope_zero_span_converter.dcm_analysis.spectrum import compute_dcm_spectrum
from scope_zero_span_converter.dcm_analysis.widget import DcmAnalysisWidget
from scope_zero_span_converter.dcm_sw_generator import (
    DcmSwParameters,
    generate_dcm_sw_waveform,
)
from scope_zero_span_converter.dcm_zero_span_link import (
    ZeroSpanProfile,
    convert_dcm_waveform_to_zero_span,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _analysis(parameters: DcmSwParameters | None = None, profile=None):
    parameters = parameters or DcmSwParameters(noise_rms_v=0.0)
    profile = profile or ZeroSpanProfile()
    waveform = generate_dcm_sw_waveform(parameters)
    zero_span = convert_dcm_waveform_to_zero_span(waveform, profile)
    spectrum = compute_dcm_spectrum(waveform.time_s, waveform.voltage_v)
    return parameters, profile, waveform, zero_span, spectrum


def test_export_rejects_fft_from_old_same_shape_waveform(tmp_path):
    old = _analysis(DcmSwParameters(on_high_voltage_v=10.0, noise_rms_v=0.0))
    current = _analysis(DcmSwParameters(on_high_voltage_v=14.0, noise_rms_v=0.0))
    parameters, profile, waveform, zero_span, _spectrum = current

    with pytest.raises(AnalysisSnapshotConsistencyError, match="FFT.*旧 DCM 波形"):
        export_dcm_analysis_bundle(
            tmp_path / "old-fft",
            parameters=parameters,
            profile=profile,
            waveform=waveform,
            zero_span=zero_span,
            spectrum=old[4],
        )
    assert not (tmp_path / "old-fft").exists()


def test_export_rejects_zero_span_from_old_same_shape_waveform(tmp_path):
    old = _analysis(DcmSwParameters(on_high_voltage_v=10.0, noise_rms_v=0.0))
    current = _analysis(DcmSwParameters(on_high_voltage_v=14.0, noise_rms_v=0.0))
    parameters, profile, waveform, _zero_span, spectrum = current

    with pytest.raises(AnalysisSnapshotConsistencyError, match="Zero Span.*旧 DCM 波形"):
        export_dcm_analysis_bundle(
            tmp_path / "old-zero-span",
            parameters=parameters,
            profile=profile,
            waveform=waveform,
            zero_span=old[3],
            spectrum=spectrum,
        )
    assert not (tmp_path / "old-zero-span").exists()


def test_export_rejects_zero_span_after_profile_change(tmp_path):
    parameters, profile, waveform, zero_span, spectrum = _analysis()
    changed_profile = replace(profile, calibration_db=profile.calibration_db + 1.0)

    with pytest.raises(AnalysisSnapshotConsistencyError, match="不对应当前转换参数"):
        export_dcm_analysis_bundle(
            tmp_path / "old-profile",
            parameters=parameters,
            profile=changed_profile,
            waveform=waveform,
            zero_span=zero_span,
            spectrum=spectrum,
        )
    assert not (tmp_path / "old-profile").exists()


def test_export_rejects_dcm_parameters_without_matching_waveform():
    parameters, profile, waveform, zero_span, spectrum = _analysis()
    changed_parameters = replace(parameters, on_high_voltage_v=15.0)

    with pytest.raises(AnalysisSnapshotConsistencyError, match="DCM 参数"):
        validate_analysis_snapshot(
            parameters=changed_parameters,
            profile=profile,
            waveform=waveform,
            zero_span=zero_span,
            spectrum=spectrum,
        )


@pytest.mark.parametrize(
    "state_field",
    ["_spectrum_worker_running", "_recompute_worker_running"],
)
def test_widget_export_rejects_running_analysis_worker(qapp, state_field):
    del qapp
    widget = DcmAnalysisWidget()
    setattr(widget, state_field, True)

    with pytest.raises(
        AnalysisSnapshotConsistencyError,
        match=ANALYSIS_UPDATING_MESSAGE,
    ):
        widget.validate_current_analysis_snapshot()

    setattr(widget, state_field, False)


def test_widget_export_rejects_pending_latest_request(qapp):
    del qapp
    widget = DcmAnalysisWidget()
    widget._spectrum_pending_waveform = widget.current_waveform

    with pytest.raises(
        AnalysisSnapshotConsistencyError,
        match=ANALYSIS_UPDATING_MESSAGE,
    ):
        widget.validate_current_analysis_snapshot()


def test_core_input_changes_advance_generation_and_gate_until_complete(qapp):
    del qapp
    widget = DcmAnalysisWidget()
    initial_generation = widget.analysis_generation
    assert widget._completed_analysis_generation == initial_generation

    voltage_control = widget._parameter_controls["on_high_voltage_v"]
    voltage_control.spin.setValue(voltage_control.value() + 1.0)

    parameter_generation = widget.analysis_generation
    assert parameter_generation == initial_generation + 1
    assert widget._completed_analysis_generation is None
    with pytest.raises(
        AnalysisSnapshotConsistencyError,
        match=ANALYSIS_UPDATING_MESSAGE,
    ):
        widget.validate_current_analysis_snapshot()

    widget._recompute()
    parameter_snapshot = widget.validate_current_analysis_snapshot()
    assert parameter_snapshot.generation == parameter_generation
    assert parameter_snapshot.completed is True

    widget.calibration_db.setValue(widget.calibration_db.value() + 1.0)
    profile_generation = widget.analysis_generation
    assert profile_generation == parameter_generation + 1
    assert widget.current_zero_span is not None
    assert widget.current_zero_span.analysis_generation == parameter_generation
    with pytest.raises(
        AnalysisSnapshotConsistencyError,
        match=ANALYSIS_UPDATING_MESSAGE,
    ):
        widget.validate_current_analysis_snapshot()

    widget._recompute()
    profile_snapshot = widget.validate_current_analysis_snapshot()
    assert profile_snapshot.generation == profile_generation
    assert profile_snapshot.zero_span.analysis_generation == profile_generation
    assert profile_snapshot.spectrum.analysis_generation == profile_generation


def test_waveform_replacement_invalidates_completed_generation(qapp):
    del qapp
    widget = DcmAnalysisWidget()
    original = widget.current_waveform
    assert original is not None
    completed_generation = widget.analysis_generation

    changed_voltage = original.voltage_v.copy()
    changed_voltage[0] += 0.25
    widget.current_waveform = replace(original, voltage_v=changed_voltage)

    with pytest.raises(
        AnalysisSnapshotConsistencyError,
        match=ANALYSIS_UPDATING_MESSAGE,
    ):
        widget.validate_current_analysis_snapshot()
    assert widget.analysis_generation == completed_generation + 1
    assert widget._completed_analysis_generation is None


def test_snapshot_and_export_reject_mixed_result_generations(tmp_path):
    parameters, profile, waveform, zero_span, spectrum = _analysis()
    zero_span = replace(zero_span, analysis_generation=4)
    spectrum = replace(spectrum, analysis_generation=5)

    with pytest.raises(
        AnalysisSnapshotConsistencyError,
        match="旧 generation.*Zero Span",
    ):
        validate_analysis_snapshot(
            parameters=parameters,
            profile=profile,
            waveform=waveform,
            zero_span=zero_span,
            spectrum=spectrum,
            analysis_generation=5,
            completed_generation=5,
            waveform_generation=5,
            zero_span_generation=4,
            spectrum_generation=5,
        )

    with pytest.raises(
        AnalysisSnapshotConsistencyError,
        match="旧 generation.*Zero Span",
    ):
        export_dcm_analysis_bundle(
            tmp_path / "stale-generation",
            parameters=parameters,
            profile=profile,
            waveform=waveform,
            zero_span=zero_span,
            spectrum=spectrum,
            analysis_generation=5,
        )
    assert not (tmp_path / "stale-generation").exists()


def test_latest_completed_generation_exports_current_inputs_and_results(tmp_path, qapp):
    del qapp
    widget = DcmAnalysisWidget()

    voltage_control = widget._parameter_controls["on_high_voltage_v"]
    voltage_control.spin.setValue(voltage_control.value() + 2.0)
    widget.calibration_db.setValue(widget.calibration_db.value() + 1.5)
    latest_generation = widget.analysis_generation
    widget._recompute()

    snapshot = widget.validate_current_analysis_snapshot()
    outputs = export_dcm_analysis_bundle(
        tmp_path,
        parameters=snapshot.parameters,
        profile=snapshot.profile,
        waveform=snapshot.waveform,
        zero_span=snapshot.zero_span,
        spectrum=snapshot.spectrum,
        analysis_generation=snapshot.generation,
    )
    metadata = json.loads(outputs["metadata_json"].read_text(encoding="utf-8"))

    assert snapshot.generation == latest_generation
    assert metadata["analysis_snapshot"] == {
        "generation": latest_generation,
        "completed": True,
        "waveform_signature": snapshot.waveform_signature,
        "zero_span_source_waveform_signature": snapshot.waveform_signature,
        "zero_span_profile_signature": snapshot.profile_signature,
        "fft_source_waveform_signature": snapshot.waveform_signature,
    }
    assert metadata["dcm_parameters"]["on_high_voltage_v"] == pytest.approx(
        widget.parameters.on_high_voltage_v
    )
    assert metadata["zero_span_profile"]["calibration_db"] == pytest.approx(
        widget.profile.calibration_db
    )
    assert metadata["zero_span_result"]["analysis_generation"] == latest_generation
    assert metadata["fft"]["analysis_generation"] == latest_generation


def test_consistent_snapshot_exports_one_coherent_bundle(tmp_path):
    parameters, profile, waveform, zero_span, spectrum = _analysis()
    figure = Figure(figsize=(5, 3))
    axis = figure.add_subplot(111)
    axis.plot(waveform.time_s, waveform.voltage_v)

    outputs = export_dcm_analysis_bundle(
        tmp_path,
        parameters=parameters,
        profile=profile,
        waveform=waveform,
        zero_span=zero_span,
        spectrum=spectrum,
        figure=figure,
    )

    assert set(outputs) == {
        "time_domain_csv",
        "zero_span_csv",
        "spectrum_csv",
        "four_panel_png",
        "metadata_json",
    }
    assert outputs["four_panel_png"].stat().st_size > 0

    dcm_csv = pd.read_csv(outputs["time_domain_csv"])
    zero_csv = pd.read_csv(outputs["zero_span_csv"])
    fft_csv = pd.read_csv(outputs["spectrum_csv"])
    metadata = json.loads(outputs["metadata_json"].read_text(encoding="utf-8"))

    np.testing.assert_allclose(
        dcm_csv["time_s"].to_numpy(), waveform.time_s, rtol=1e-14, atol=1e-18
    )
    np.testing.assert_allclose(
        dcm_csv["voltage_v"].to_numpy(),
        waveform.voltage_v,
        rtol=1e-14,
        atol=5e-16,
    )
    np.testing.assert_allclose(
        zero_csv["time_s"].to_numpy(), zero_span.time_s, rtol=1e-14, atol=1e-18
    )
    assert np.allclose(
        zero_csv["amplitude_dbm"].to_numpy(),
        zero_span.amplitude_dbm,
        rtol=1e-12,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        fft_csv["frequency_hz"].to_numpy(),
        spectrum.frequency_hz,
        rtol=1e-14,
        atol=1e-18,
    )

    snapshot = metadata["analysis_snapshot"]
    assert snapshot["waveform_signature"] == zero_span.source_waveform_signature
    assert snapshot["waveform_signature"] == spectrum.source_waveform_signature
    assert snapshot["zero_span_profile_signature"] == zero_span.source_profile_signature
    assert metadata["dcm_parameters"]["on_high_voltage_v"] == parameters.on_high_voltage_v
    assert metadata["zero_span_profile"]["impedance_ohm"] == profile.impedance_ohm
    assert metadata["zero_span_result"]["source_waveform_signature"] == snapshot[
        "waveform_signature"
    ]
    assert metadata["fft"]["source_waveform_signature"] == snapshot[
        "waveform_signature"
    ]
    assert metadata["data_files"]["metadata_json"] == "analysis_metadata.json"
