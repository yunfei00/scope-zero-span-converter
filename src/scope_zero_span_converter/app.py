from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .app_state import AppState, load_state, save_state
from .gui_v04 import MainWindow
from .logging_utils import get_logger


LOGGER = get_logger()


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()

    state = load_state()
    if state is not None:
        try:
            window.apply_config(state.config)
            if 0 <= state.selected_tab < window.tabs.count():
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
            config = window.collect_config()
            save_state(
                AppState(
                    config=config,
                    selected_tab=window.tabs.currentIndex(),
                    selected_template=window.template_combo.currentText(),
                )
            )
            LOGGER.info("已保存最近使用状态")
        except Exception:
            LOGGER.exception("保存最近使用状态失败")

    app.aboutToQuit.connect(persist_state)
    window.show()
    return app.exec()
