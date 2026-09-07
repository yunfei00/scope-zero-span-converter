from __future__ import annotations

import re

import scope_zero_span_converter as package
from scope_zero_span_converter import _version


PEP440_SIMPLE = re.compile(r"^\d+\.\d+\.\d+(?:\.dev\d+)?$")


def test_package_version_comes_from_single_version_module():
    assert package.__version__ == _version.__version__
    assert PEP440_SIMPLE.match(package.__version__)


def test_main_branch_is_on_next_commercialization_development_line():
    assert package.__version__ == "0.8.0.dev0"
