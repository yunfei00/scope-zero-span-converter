from __future__ import annotations

import ast
import re
from pathlib import Path

from PySide6.QtWidgets import QMainWindow, QWidget

from scope_zero_span_converter.dcm_analysis.widget import DcmAnalysisWidget
from scope_zero_span_converter.dcm_extractor.widget import DcmParameterExtractorWidget
from scope_zero_span_converter.dcm_generator.widget import DcmSwGeneratorWidget
from scope_zero_span_converter.main_window import MainWindow


PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "scope_zero_span_converter"
FORMAL_GUI_ROOTS = (
    PACKAGE_ROOT / "dcm_analysis",
    PACKAGE_ROOT / "dcm_generator",
    PACKAGE_ROOT / "dcm_extractor",
)
LEGACY_MODULE_STEMS = {
    "gui",
    "gui_v04",
    "gui_v05",
    "dcm_analysis_widget",
    "dcm_zero_span_widget",
    "dcm_parameter_extractor_widget",
    "dcm_sw_generator_widget",
}
VERSIONED_GUI_STEM = re.compile(r"(?:gui|widget)_v\d+$")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _is_legacy_gui_module(module: str) -> bool:
    stem = module.rsplit(".", 1)[-1]
    return stem in LEGACY_MODULE_STEMS or VERSIONED_GUI_STEM.search(stem) is not None


def test_legacy_gui_implementation_files_are_retired() -> None:
    offenders = [
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in PACKAGE_ROOT.rglob("*.py")
        if _is_legacy_gui_module(path.stem)
    ]
    assert offenders == []


def test_production_source_does_not_import_legacy_gui_modules() -> None:
    offenders: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        for module in _imported_modules(path):
            if _is_legacy_gui_module(module):
                offenders.append(f"{path.relative_to(PACKAGE_ROOT)}: {module}")
    assert offenders == []


def test_formal_gui_packages_use_only_versionless_module_names() -> None:
    offenders = [
        path.relative_to(PACKAGE_ROOT).as_posix()
        for root in FORMAL_GUI_ROOTS
        for path in root.rglob("*.py")
        if VERSIONED_GUI_STEM.search(path.stem)
        or any(_is_legacy_gui_module(module) for module in _imported_modules(path))
    ]
    assert offenders == []


def test_formal_gui_runtime_mros_are_versionless() -> None:
    expected_base = {
        MainWindow: QMainWindow,
        DcmAnalysisWidget: QWidget,
        DcmSwGeneratorWidget: QWidget,
        DcmParameterExtractorWidget: QWidget,
    }
    for widget_type, qt_base in expected_base.items():
        assert qt_base in widget_type.mro()
        assert not any(
            _is_legacy_gui_module(base.__module__)
            for base in widget_type.mro()
        )
