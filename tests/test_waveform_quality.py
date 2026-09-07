from __future__ import annotations

import numpy as np
import pytest

from scope_zero_span_converter.waveform_quality import analyze_time_axis, require_fft_safe


def test_uniform_scope_time_axis_is_fft_safe():
    t = np.arange(10_000, dtype=float) / 1e9
    report = analyze_time_axis(t)

    assert report.fft_safe is True
    assert report.status == "pass"
    assert report.sample_rate_hz == pytest.approx(1e9, rel=1e-9)
    assert report.duplicate_timestamps == 0
    assert report.max_dt_deviation_fraction < 1e-9


def test_duplicate_timestamp_fails_fft_quality_gate():
    t = np.asarray([0.0, 1e-9, 2e-9, 2e-9, 3e-9])
    report = analyze_time_axis(t)

    assert report.fft_safe is False
    assert report.duplicate_timestamps == 1
    with pytest.raises(ValueError, match="重复时间"):
        require_fft_safe(report)


def test_missing_sample_like_gap_fails_uniformity_gate():
    t = np.asarray([0.0, 1e-9, 2e-9, 4e-9, 5e-9])
    report = analyze_time_axis(t)

    assert report.fft_safe is False
    assert report.max_gap_ratio == pytest.approx(2.0)
    assert "采样间隔最大偏差" in report.message


def test_reversed_input_order_warns_but_sorted_axis_remains_fft_safe():
    t = np.asarray([0.0, 2e-9, 1e-9, 3e-9, 4e-9])
    report = analyze_time_axis(t)

    assert report.fft_safe is True
    assert report.status == "warn"
    assert report.nonmonotonic_steps == 1
    assert "时间倒序" in report.message
