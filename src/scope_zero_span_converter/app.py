from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication

from .app_state import AppState, load_state, save_state
from .logging_utils import get_logger
from .main_window import MainWindow
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
            "dcm_analysis": collect_dcm_analysis_workspace(
                window.dcm_analysis_tab
            )
        },
    )


def _is_wsl() -> bool:
    """Return True when running inside Windows Subsystem for Linux."""

    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True

    try:
        with open("/proc/sys/kernel/osrelease", "r", encoding="utf-8") as handle:
            return "microsoft" in handle.read().lower()
    except OSError:
        return False


def _show_main_window(app: QApplication, window: MainWindow) -> None:
    """Show the main window with a WSLg-compatible maximize fallback."""

    screen = app.primaryScreen()
    if screen is not None:
        geometry = screen.geometry()
        available = screen.availableGeometry()
        LOGGER.info(
            "显示环境: WSL=%s, screen=%dx%d, available=%dx%d, DPR=%.2f",
            _is_wsl(),
            geometry.width(),
            geometry.height(),
            available.width(),
            available.height(),
            screen.devicePixelRatio(),
        )

    if _is_wsl() and screen is not None:
        # WSLg can ignore showMaximized() depending on the host/Wayland window
        # manager.  Explicitly fill Qt's usable desktop area instead.
        window.setGeometry(screen.availableGeometry())
        window.show()
        LOGGER.info("WSLg 环境：已按 availableGeometry 铺满可用桌面区域")
        return

    window.showMaximized()
    LOGGER.info("非 WSL 环境：使用 showMaximized() 启动")


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()

    state = load_state()
    if state is not None:
        try:
            window.apply_config(state.config)

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
