from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


_SECTION_DEFAULTS: dict[str, bool] = {
    "input": True,
    "roi": True,
    "zero_span": True,
    "conversion": False,
    "output": False,
    "templates": False,
}

_TITLE_TO_SECTION_ID = {
    "输入文件": "input",
    "波形研究区域（ROI）": "roi",
    "Zero Span 转换参数（当前算法保持不变）": "zero_span",
    "转换设置": "conversion",
    "完整转换输出": "output",
    "配置模板": "templates",
}


class CollapsibleSection(QWidget):
    """Compact reusable section with a clickable title and hideable content."""

    def __init__(
        self,
        title: str,
        content: QWidget,
        *,
        expanded: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._content = content

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.header = QToolButton(self)
        self.header.setText(title)
        self.header.setCheckable(True)
        self.header.setChecked(expanded)
        self.header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.header.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.header.setAutoRaise(False)
        self.header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.header.setStyleSheet(
            "QToolButton { text-align: left; font-weight: 600; padding: 6px 8px; }"
        )
        self.header.toggled.connect(self._set_expanded)
        layout.addWidget(self.header)

        # Keep the existing widgets/layout untouched.  Removing the group title
        # avoids displaying the same heading twice while preserving all signal
        # connections and references held by ResearchWorkspaceWindow.
        if isinstance(content, QGroupBox):
            content.setTitle("")
            content.setFlat(True)
        layout.addWidget(content)
        self._set_expanded(expanded)

    def _set_expanded(self, expanded: bool) -> None:
        self._content.setVisible(expanded)
        self.header.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)

    def is_expanded(self) -> bool:
        return self.header.isChecked()

    def set_expanded(self, expanded: bool) -> None:
        self.header.setChecked(bool(expanded))
        self._set_expanded(bool(expanded))


def install_research_workspace_state(window: Any) -> None:
    """Make waveform-research groups collapsible without changing core logic."""

    if getattr(window, "_research_sections", None):
        return

    splitter = window.research_tab.findChild(QSplitter)
    if splitter is None or splitter.count() < 2:
        return

    left_scroll = splitter.widget(0)
    if not isinstance(left_scroll, QScrollArea):
        return
    left_container = left_scroll.widget()
    if left_container is None or left_container.layout() is None:
        return

    left_layout = left_container.layout()
    candidates: list[tuple[int, QGroupBox, str, str]] = []
    for index in range(left_layout.count()):
        item = left_layout.itemAt(index)
        widget = item.widget() if item is not None else None
        if not isinstance(widget, QGroupBox):
            continue
        title = widget.title()
        section_id = _TITLE_TO_SECTION_ID.get(title)
        if section_id is None:
            continue
        candidates.append((index, widget, title, section_id))

    sections: dict[str, CollapsibleSection] = {}
    # Replace from bottom to top so layout indexes remain stable.
    for index, group, title, section_id in reversed(candidates):
        item = left_layout.takeAt(index)
        if item is None:
            continue
        section = CollapsibleSection(
            title,
            group,
            expanded=_SECTION_DEFAULTS[section_id],
            parent=left_container,
        )
        left_layout.insertWidget(index, section)
        sections[section_id] = section

    window._research_sections = sections
    window._research_splitter = splitter


def collect_research_workspace(window: Any) -> dict[str, Any]:
    """Serialize UI-only waveform research layout preferences."""

    sections = getattr(window, "_research_sections", {})
    splitter = getattr(window, "_research_splitter", None)
    state: dict[str, Any] = {
        "sections": {
            section_id: section.is_expanded()
            for section_id, section in sections.items()
        }
    }
    if isinstance(splitter, QSplitter):
        state["splitter_sizes"] = [int(value) for value in splitter.sizes()]
    return state


def apply_research_workspace(window: Any, state: dict[str, Any]) -> None:
    """Restore saved waveform research layout, tolerating older state files."""

    sections = getattr(window, "_research_sections", {})
    section_state = state.get("sections", {})
    if isinstance(section_state, dict):
        for section_id, section in sections.items():
            saved = section_state.get(section_id)
            if isinstance(saved, bool):
                section.set_expanded(saved)

    splitter = getattr(window, "_research_splitter", None)
    sizes = state.get("splitter_sizes")
    if isinstance(splitter, QSplitter) and isinstance(sizes, list) and len(sizes) == splitter.count():
        parsed: list[int] = []
        for value in sizes:
            try:
                parsed.append(max(0, int(value)))
            except (TypeError, ValueError):
                parsed = []
                break
        if parsed and any(parsed):
            splitter.setSizes(parsed)
