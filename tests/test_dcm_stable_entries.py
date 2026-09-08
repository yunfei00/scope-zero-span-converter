from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from scope_zero_span_converter.dcm_extractor import DcmParameterExtractorWidget
from scope_zero_span_converter.dcm_generator import DcmSwGeneratorWidget


def test_generator_and_extractor_use_stable_package_entries():
    assert DcmSwGeneratorWidget.__module__ == "scope_zero_span_converter.dcm_generator.widget"
    assert DcmParameterExtractorWidget.__module__ == "scope_zero_span_converter.dcm_extractor.widget"
