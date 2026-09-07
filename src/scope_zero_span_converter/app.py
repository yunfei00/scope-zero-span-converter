from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .app_state import AppState, load_state, save_state
from .gui_v05 import MainWindow
from .logging_utils import get_logger


LOGGER = get_logger()


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()

    state = load_state()
    if state is not None:
        try:
            window.apply_config(state.config)

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
            config = window.collect_config()
            current_index = window.tabs.currentIndex()
            save_state(
                AppState(
                    config=config,
                    selected_tab=current_index,
                    selected_tab_id=window.tab_id_for_index(current_index),
                    selected_template=window.template_combo.currentText(),
                )
            )
            LOGGER.info("已保存最近使用状态")
        except Exception:
            LOGGER.exception("保存最近使用状态失败")

    app.aboutToQuit.connect(persist_state)
    window.show()
    return app.exec()
