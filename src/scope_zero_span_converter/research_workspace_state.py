from __future__ import annotations

from types import MethodType
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
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


def _hide_fixed_zero_span_row(window: Any) -> None:
    """Hide the read-only Span=0 row while keeping the internal value intact."""

    span_widget = getattr(window, "span_mhz", None)
    if span_widget is None:
        return

    span_widget.hide()
    parent = span_widget.parentWidget()
    layout = parent.layout() if parent is not None else None
    if isinstance(layout, QFormLayout):
        label = layout.labelForField(span_widget)
        if label is not None:
            label.hide()


def _install_gui_parameter_policy(window: Any) -> None:
    """Expose every runtime FSW parameter and make GUI/AppConfig authoritative."""

    metadata_toggle = getattr(window, "use_metadata_check", None)
    if metadata_toggle is not None:
        metadata_toggle.setChecked(False)
        metadata_toggle.hide()

    signal_group = None
    for group in window.findChildren(QGroupBox):
        if group.title().startswith("Zero Span 转换参数"):
            signal_group = group
            break
    if signal_group is None or not isinstance(signal_group.layout(), QFormLayout):
        return

    layout = signal_group.layout()

    window.fsw_sweep_time_ms = QDoubleSpinBox(signal_group)
    window.fsw_sweep_time_ms.setRange(0.0, 1_000_000.0)
    window.fsw_sweep_time_ms.setDecimals(9)
    window.fsw_sweep_time_ms.setKeyboardTracking(False)
    window.fsw_sweep_time_ms.setSpecialValueText("未设置")
    window.fsw_sweep_time_ms.setToolTip(
        "完整转换重采样使用的 Sweep Time。0 表示未设置。"
    )

    window.fsw_trace_points = QSpinBox(signal_group)
    window.fsw_trace_points.setRange(0, 10_000_000)
    window.fsw_trace_points.setSpecialValueText("未设置")
    window.fsw_trace_points.setToolTip(
        "完整转换重采样使用的 Trace Points。0 表示未设置。"
    )

    layout.addRow("Sweep Time (ms)", window.fsw_sweep_time_ms)
    layout.addRow("Trace Points", window.fsw_trace_points)

    note = QLabel(
        "所有转换与联动均以当前界面参数为准；Metadata 仅作为原始采集记录，不覆盖转换参数。",
        signal_group,
    )
    note.setWordWrap(True)
    layout.addRow(note)

    original_collect_config = window.collect_config
    original_apply_config = window.apply_config

    def collect_config_from_gui(self):
        cfg = original_collect_config()
        cfg.conversion.use_metadata_parameters = False
        sweep_ms = float(self.fsw_sweep_time_ms.value())
        trace_points = int(self.fsw_trace_points.value())
        cfg.conversion.fsw_sweep_time_s = sweep_ms / 1000.0 if sweep_ms > 0 else None
        cfg.conversion.fsw_trace_points = trace_points if trace_points >= 2 else None
        cfg.validate()
        return cfg

    def apply_config_to_gui(self, cfg):
        cfg.conversion.use_metadata_parameters = False
        original_apply_config(cfg)
        if metadata_toggle is not None:
            metadata_toggle.setChecked(False)
        sweep_time_s = cfg.conversion.fsw_sweep_time_s
        trace_points = cfg.conversion.fsw_trace_points
        self.fsw_sweep_time_ms.setValue(
            0.0 if sweep_time_s is None else float(sweep_time_s) * 1000.0
        )
        self.fsw_trace_points.setValue(
            0 if trace_points is None else int(trace_points)
        )

    window.collect_config = MethodType(collect_config_from_gui, window)
    window.apply_config = MethodType(apply_config_to_gui, window)


def install_research_workspace_state(window: Any) -> None:
    """Install compact research UI state and GUI-authoritative parameters."""

    if getattr(window, "_research_sections", None):
        return

    _hide_fixed_zero_span_row(window)
    _install_gui_parameter_policy(window)

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
