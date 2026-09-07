from __future__ import annotations

import os
import re

import scope_zero_span_converter as package
from scope_zero_span_converter import _version


PEP440_SIMPLE = re.compile(r"^\d+\.\d+\.\d+(?:\.dev\d+)?$")


def test_package_version_comes_from_single_version_module():
    assert package.__version__ == _version.__version__
    assert PEP440_SIMPLE.match(package.__version__)


def test_version_matches_current_build_context():
    ref_name = os.environ.get("GITHUB_REF_NAME", "")
    if ref_name.startswith("v"):
        assert package.__version__ == ref_name[1:]
    else:
        assert package.__version__ == "0.8.0.dev0"
