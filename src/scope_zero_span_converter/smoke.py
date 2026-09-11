"""Noninteractive validation of the actual source or frozen GUI entrypoint."""

from __future__ import annotations

import json
import platform
import sys
import traceback
from pathlib import Path

from . import __version__
from .config import load_config
from .product import PRODUCT_NAME
from .runtime_paths import resource_path, user_data_directory


def run_smoke_test(report_path: Path) -> int:
    from PySide6.QtCore import qVersion
    from PySide6.QtWidgets import QApplication
    from .dcm_analysis.widget import DcmAnalysisWidget
    from .dcm_extractor.widget import DcmParameterExtractorWidget
    from .dcm_generator.widget import DcmSwGeneratorWidget
    from .main_window import MainWindow

    report = {
        "version": __version__, "product": PRODUCT_NAME,
        "python": platform.python_version(), "qt": qVersion(),
        "executable": str(Path(sys.executable).resolve()),
        "frozen": bool(getattr(sys, "frozen", False)),
        "user_data_directory": str(user_data_directory()), "status": "FAIL",
    }
    window = None
    app = QApplication.instance() or QApplication(["ScopeZeroSpanConverter", "--smoke-test"])
    try:
        config_path = resource_path("configs/default.json")
        load_config(config_path).validate()
        if not resource_path("assets/app.ico").is_file():
            raise RuntimeError("Packaged application icon is missing")
        window = MainWindow()
        expected = ["waveform_research", "dcm_generator", "dcm_extractor", "dcm_analysis", "batch_conversion"]
        actual = [window.tab_id_for_index(i) for i in range(window.tabs.count())]
        if actual != expected:
            raise RuntimeError(f"Unexpected tabs: {actual}")
        for child, expected_type in (
            (window.dcm_generator_tab, DcmSwGeneratorWidget),
            (window.dcm_extractor_tab, DcmParameterExtractorWidget),
            (window.dcm_analysis_tab, DcmAnalysisWidget),
        ):
            if type(child) is not expected_type:
                raise RuntimeError(f"Unexpected widget: {type(child)}")
            child.canvas.draw()
        if window.windowIcon().isNull():
            raise RuntimeError("Qt could not decode the application icon")
        if window.dcm_analysis_tab._spectrum_cache is None:
            raise RuntimeError("Initial NumPy FFT did not complete")
        window.collect_config().validate()
        report.update(tabs=actual, config_resource=str(config_path), platform=app.platformName())
        # Exercise timers/Qt delivery and the normal safe close path, without
        # restoring or overwriting a customer's AppState.
        app.processEvents()
        if window.has_active_background_tasks():
            raise RuntimeError("Smoke initialization unexpectedly started background work")
        if not window.close():
            raise RuntimeError("MainWindow did not close cleanly")
        app.processEvents()
        report["status"] = "PASS"
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        if window is not None:
            window.begin_shutdown()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "PASS" else 1
