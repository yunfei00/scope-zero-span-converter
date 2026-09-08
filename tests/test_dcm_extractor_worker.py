from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from scope_zero_span_converter.dcm_discontinuous_extractor import (
    extract_dcm_discontinuous_resonance,
)
from scope_zero_span_converter.dcm_extractor.worker import GlobalRefinementWorkerTask
from scope_zero_span_converter.dcm_parameter_extractor import extract_dcm_basic_parameters
from scope_zero_span_converter.dcm_ringing_extractor import extract_dcm_edge_ringing
from scope_zero_span_converter.dcm_sw_generator import DcmSwParameters, generate_dcm_sw_waveform


def test_global_refinement_worker_runs_without_qwidget_access():
    waveform = generate_dcm_sw_waveform(
        DcmSwParameters(
            total_duration_s=8e-6,
            switching_start_s=0.8e-6,
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
    basic = extract_dcm_basic_parameters(waveform.time_s, waveform.voltage_v)
    ringing = extract_dcm_edge_ringing(waveform.time_s, waveform.voltage_v, basic)
    dcm = extract_dcm_discontinuous_resonance(
        waveform.time_s,
        waveform.voltage_v,
        basic,
        ringing,
    )

    completed = []
    failures = []
    task = GlobalRefinementWorkerTask(
        request_id=11,
        time_s=waveform.time_s,
        voltage_v=waveform.voltage_v,
        basic=basic,
        ringing=ringing,
        dcm=dcm,
        max_iterations=1,
        max_optimization_points=1500,
    )
    task.signals.finished.connect(lambda request_id, result: completed.append((request_id, result)))
    task.signals.failed.connect(lambda request_id, message: failures.append((request_id, message)))

    task.run()

    assert not failures
    assert len(completed) == 1
    request_id, result = completed[0]
    assert request_id == 11
    assert result.optimized_reconstruction_v.shape == waveform.voltage_v.shape
    assert result.final_residual_v.shape == waveform.voltage_v.shape
