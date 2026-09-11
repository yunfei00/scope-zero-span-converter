from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path


def _is_wsl() -> bool:
    """Return True when running inside Windows Subsystem for Linux."""

    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True

    try:
        with open("/proc/sys/kernel/osrelease", "r", encoding="utf-8") as handle:
            return "microsoft" in handle.read().lower()
    except OSError:
        return False


from PySide6.QtWidgets import QApplication

from .app_state import AppState, load_state, save_state
from .logging_utils import get_logger
from .main_window import MainWindow
from .research_workspace_state import (
    apply_research_workspace,
    collect_research_workspace,
    install_research_workspace_state,
)
from .workspace import apply_dcm_analysis_workspace, collect_dcm_analysis_workspace


LOGGER = get_logger()


def collect_app_state(window: MainWindow) -> AppState:
    """Collect state while the accepted main window is still alive."""

    config = window.collect_config()
    current_index = window.tabs.currentIndex()
    return AppState(
        config=config,
        selected_tab=current_index,
        selected_tab_id=window.tab_id_for_index(current_index),
        selected_template=window.template_combo.currentText(),
        workspace={
            "waveform_research": collect_research_workspace(window),
            "dcm_analysis": collect_dcm_analysis_workspace(
                window.dcm_analysis_tab
            ),
        },
    )


def _show_main_window(app: QApplication, window: MainWindow) -> None:
    """Show the main window using the platform's native maximize state."""

    screen = app.primaryScreen()
    if screen is not None:
        geometry = screen.geometry()
        available = screen.availableGeometry()
        LOGGER.info(
            "显示环境: WSL=%s, QtPlatform=%s, screen=%dx%d, available=%dx%d, DPR=%.2f",
            _is_wsl(),
            app.platformName(),
            geometry.width(),
            geometry.height(),
            available.width(),
            available.height(),
            screen.devicePixelRatio(),
        )
    else:
        LOGGER.info(
            "显示环境: WSL=%s, QtPlatform=%s, screen=unknown",
            _is_wsl(),
            app.platformName(),
        )

    # Do not force xcb or emulate maximization with setGeometry() under WSLg.
    # Let Qt/WSLg choose the native platform backend so multi-monitor geometry
    # and per-monitor scaling remain under the compositor's control.
    window.showMaximized()
    LOGGER.info("主窗口使用平台原生 showMaximized() 启动")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scope Zero Span Converter")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--smoke-report", type=Path)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.smoke_test:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from .runtime_paths import user_data_directory
        from .smoke import run_smoke_test
        return run_smoke_test(args.smoke_report or user_data_directory() / "smoke-report.json")
    app = QApplication(sys.argv)
    window = MainWindow()
    install_research_workspace_state(window)

    state = load_state()
    if state is not None:
        try:
            window.apply_config(state.config)

            research_workspace = state.workspace.get("waveform_research")
            if isinstance(research_workspace, dict):
                apply_research_workspace(window, research_workspace)

            dcm_workspace = state.workspace.get("dcm_analysis")
            if isinstance(dcm_workspace, dict):
                apply_dcm_analysis_workspace(window.dcm_analysis_tab, dcm_workspace)

            restored = False
            if state.selected_tab_id:
                index = window.index_for_tab_id(state.selected_tab_id)
                if index >= 0:
                    window.tabs.setCurrentIndex(index)
                    restored = True

            # 兼容 schema v1：旧状态只保存数字页签索引。
            if not restored and 0 <= state.selected_tab < window.tabs.count():
                window.tabs.setCurrentIndex(state.selected_tab)

            if state.selected_template:
                index = window.template_combo.findText(state.selected_template)
                if index >= 0:
                    window.template_combo.setCurrentIndex(index)
            LOGGER.info("已恢复最近使用状态")
        except Exception:
            LOGGER.exception("恢复最近使用状态失败")

    def persist_state() -> None:
        try:
            save_state(collect_app_state(window))
            LOGGER.info("已保存最近使用状态")
        except Exception:
            LOGGER.exception("保存最近使用状态失败")

    app.aboutToQuit.connect(persist_state)
    _show_main_window(app, window)
    return app.exec()
