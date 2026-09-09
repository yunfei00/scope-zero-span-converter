from __future__ import annotations

import json

from matplotlib.figure import Figure

from scope_zero_span_converter.dcm_analysis.exporter import export_dcm_analysis_bundle
from scope_zero_span_converter.dcm_analysis.spectrum import compute_dcm_spectrum
from scope_zero_span_converter.dcm_sw_generator import DcmSwParameters, generate_dcm_sw_waveform
from scope_zero_span_converter.dcm_zero_span_link import (
    ZeroSpanProfile,
    convert_dcm_waveform_to_zero_span,
)


def test_export_bundle_writes_png_csv_and_metadata(tmp_path):
    waveform = generate_dcm_sw_waveform(DcmSwParameters(noise_rms_v=0.0))
    zero_span = convert_dcm_waveform_to_zero_span(waveform, ZeroSpanProfile())
    spectrum = compute_dcm_spectrum(waveform.time_s, waveform.voltage_v)

    figure = Figure(figsize=(4, 3))
    axis = figure.add_subplot(111)
    axis.plot(waveform.time_s[:100] * 1e6, waveform.voltage_v[:100])

    outputs = export_dcm_analysis_bundle(
        tmp_path,
        parameters=waveform.parameters,
        profile=ZeroSpanProfile(),
        waveform=waveform,
        zero_span=zero_span,
        spectrum=spectrum,
        figure=figure,
        metadata={
            "markers": {"time_a_enabled": False},
            "zoom_history": "must-not-be-generated-by-exporter",
        },
    )

    assert outputs["time_domain_csv"].exists()
    assert outputs["zero_span_csv"].exists()
    assert outputs["spectrum_csv"].exists()
    assert outputs["four_panel_png"].exists()
    assert outputs["metadata_json"].exists()

    payload = json.loads(outputs["metadata_json"].read_text(encoding="utf-8"))
    assert payload["export_type"] == "dcm_analysis_bundle"
    assert payload["semantics"]["zoom_history_exported"] is False
    assert payload["semantics"]["zero_span"].startswith("fixed RF center")
    assert payload["zero_span_result"]["center_frequency_hz"] == 200e6
    assert payload["fft"]["window"] == "hann"
    assert payload["analysis_snapshot"]["waveform_signature"] == (
        spectrum.source_waveform_signature
    )
    assert "zoom_history" not in payload["workspace"]
    assert set(payload["data_files"]) >= {
        "time_domain_csv",
        "zero_span_csv",
        "spectrum_csv",
        "four_panel_png",
    }
