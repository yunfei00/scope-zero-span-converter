from __future__ import annotations

from dataclasses import asdict, fields
from typing import Any

from PySide6.QtWidgets import QSplitter

from .dcm_sw_generator import DcmSwParameters
from .dcm_zero_span_link import ZeroSpanProfile


_WORKSPACE_SCHEMA_VERSION = 2

_AXIS_FIELDS = (
    "dcm_y_min",
    "dcm_y_max",
    "dcm_y_step",
    "zero_y_min",
    "zero_y_max",
    "zero_y_step",
    "freq_x_min",
    "freq_x_max",
    "freq_x_step",
    "freq_y_min",
    "freq_y_max",
    "freq_y_step",
)


def _filtered_dataclass_kwargs(cls, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    allowed = {field.name for field in fields(cls)}
    return {key: value for key, value in raw.items() if key in allowed}


def _read_spin(widget, name: str) -> float | None:
    control = getattr(widget, name, None)
    if control is None or not hasattr(control, "value"):
        return None
    try:
        return float(control.value())
    except (TypeError, ValueError):
        return None


def _set_spin(control, value: Any) -> None:
    if control is None or value is None or not hasattr(control, "setValue"):
        return
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return
    previous = control.blockSignals(True)
    try:
        control.setValue(numeric)
    finally:
        control.blockSignals(previous)


def _clean_path(value: Any) -> str | None:
    """Return a persisted recent-file path without touching the filesystem.

    Workspace restoration must not depend on a removable drive/network share
    still being available. The stored path is only used as the next file-dialog
    starting location; physical parameters are restored from the workspace
    snapshot itself.
    """

    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _main_splitter(widget) -> QSplitter | None:
    splitters = widget.findChildren(QSplitter)
    if not splitters:
        return None
    # DCM analysis currently owns one main horizontal splitter. Keeping this
    # lookup here avoids modifying the legacy base widget solely for persistence.
    return splitters[0]


def collect_dcm_analysis_workspace(widget) -> dict[str, Any]:
    """Serialize stable DCM-analysis working state without waveform/zoom data."""

    axis: dict[str, float] = {}
    for name in _AXIS_FIELDS:
        value = _read_spin(widget, name)
        if value is not None:
            axis[name] = value

    marker_a_enable = getattr(widget, "time_marker_a_enable", None)
    marker_b_enable = getattr(widget, "time_marker_b_enable", None)
    marker_a_time = getattr(widget, "time_marker_a_time_us", None)
    marker_b_time = getattr(widget, "time_marker_b_time_us", None)
    splitter = _main_splitter(widget)

    return {
        "schema_version": _WORKSPACE_SCHEMA_VERSION,
        "dcm_parameters": asdict(widget.parameters),
        "zero_span_profile": asdict(widget.profile),
        "axis": axis,
        "panels": {
            "zero_span_expanded": bool(
                getattr(getattr(widget, "zero_span_toggle", None), "isChecked", lambda: False)()
            ),
            "axis_settings_expanded": bool(
                getattr(getattr(widget, "axis_display_toggle", None), "isChecked", lambda: False)()
            ),
        },
        "layout": {
            "main_splitter_sizes": splitter.sizes() if splitter is not None else [],
        },
        "markers": {
            "frequency_hz": getattr(widget, "selected_marker_frequency_hz", None),
            "time_a_enabled": bool(marker_a_enable.isChecked()) if marker_a_enable is not None else False,
            "time_a_us": float(marker_a_time.value()) if marker_a_time is not None else None,
            "time_b_enabled": bool(marker_b_enable.isChecked()) if marker_b_enable is not None else False,
            "time_b_us": float(marker_b_time.value()) if marker_b_time is not None else None,
        },
        "recent_files": {
            "dcm_parameters_path": _clean_path(
                getattr(widget, "current_dcm_parameters_path", None)
            ),
            "zero_span_profile_path": _clean_path(
                getattr(widget, "current_zero_span_profile_path", None)
            ),
        },
        # Rectangle Zoom / Space history is intentionally omitted. It is a
        # temporary navigation state, not a customer workspace setting.
    }


def apply_dcm_analysis_workspace(widget, raw: Any) -> bool:
    """Restore DCM-analysis workspace defensively; unknown future keys are ignored."""

    if not isinstance(raw, dict):
        return False
    try:
        schema_version = int(raw.get("schema_version", 1))
    except (TypeError, ValueError):
        return False
    if schema_version < 1:
        return False

    params_raw = raw.get("dcm_parameters")
    if isinstance(params_raw, dict):
        defaults = asdict(DcmSwParameters())
        defaults.update(_filtered_dataclass_kwargs(DcmSwParameters, params_raw))
        widget.parameters = DcmSwParameters(**defaults)
        widget._apply_parameters_to_controls(widget.parameters)

    profile_raw = raw.get("zero_span_profile")
    if isinstance(profile_raw, dict):
        defaults = asdict(ZeroSpanProfile())
        defaults.update(_filtered_dataclass_kwargs(ZeroSpanProfile, profile_raw))
        widget.profile = ZeroSpanProfile(**defaults)
        widget._apply_profile_to_controls(widget.profile)

    # Generate/cache data once with the restored physical parameters before
    # restoring display-only controls and markers.
    widget._recompute()

    axis_raw = raw.get("axis")
    if isinstance(axis_raw, dict):
        for name in _AXIS_FIELDS:
            if name in axis_raw:
                _set_spin(getattr(widget, name, None), axis_raw[name])

    panels = raw.get("panels")
    if isinstance(panels, dict):
        zero_toggle = getattr(widget, "zero_span_toggle", None)
        if zero_toggle is not None and "zero_span_expanded" in panels:
            zero_toggle.setChecked(bool(panels["zero_span_expanded"]))
        axis_toggle = getattr(widget, "axis_display_toggle", None)
        if axis_toggle is not None and "axis_settings_expanded" in panels:
            axis_toggle.setChecked(bool(panels["axis_settings_expanded"]))

    layout = raw.get("layout")
    if isinstance(layout, dict):
        sizes = layout.get("main_splitter_sizes")
        splitter = _main_splitter(widget)
        if splitter is not None and isinstance(sizes, list) and len(sizes) >= 2:
            try:
                clean_sizes = [max(0, int(value)) for value in sizes]
                if any(clean_sizes):
                    splitter.setSizes(clean_sizes)
            except (TypeError, ValueError):
                pass

    markers = raw.get("markers")
    if isinstance(markers, dict):
        frequency_hz = markers.get("frequency_hz")
        try:
            widget.selected_marker_frequency_hz = (
                None if frequency_hz is None else float(frequency_hz)
            )
        except (TypeError, ValueError):
            widget.selected_marker_frequency_hz = None

        # The current waveform already exists, so the marker controls now have
        # their correct absolute time limits. Restored values are clamped by Qt
        # to the active waveform range if an old state no longer fits.
        for name, key in (
            ("time_marker_a_time_us", "time_a_us"),
            ("time_marker_b_time_us", "time_b_us"),
        ):
            if key in markers:
                _set_spin(getattr(widget, name, None), markers[key])

        for name, key in (
            ("time_marker_a_enable", "time_a_enabled"),
            ("time_marker_b_enable", "time_b_enabled"),
        ):
            control = getattr(widget, name, None)
            if control is not None and key in markers:
                previous = control.blockSignals(True)
                try:
                    control.setChecked(bool(markers[key]))
                finally:
                    control.blockSignals(previous)

    # Schema v2 introduced explicit recent-file state. Keep schema v1 fully
    # compatible: no section simply means no remembered dialog location.
    recent_files = raw.get("recent_files")
    if isinstance(recent_files, dict):
        if hasattr(widget, "current_dcm_parameters_path"):
            widget.current_dcm_parameters_path = _clean_path(
                recent_files.get("dcm_parameters_path")
            )
        if hasattr(widget, "current_zero_span_profile_path"):
            widget.current_zero_span_profile_path = _clean_path(
                recent_files.get("zero_span_profile_path")
            )

    # Frequency inputs normally represent an automatically refreshed view. A
    # restored workspace should show the saved input values for this first frame;
    # the next real DCM/FFT update resumes the existing automatic-axis behavior.
    has_manual_frequency_axis = isinstance(axis_raw, dict) and any(
        name in axis_raw for name in ("freq_x_min", "freq_x_max", "freq_y_min", "freq_y_max")
    )
    if has_manual_frequency_axis and hasattr(widget, "_frequency_manual_redraw_once"):
        widget._frequency_manual_redraw_once = True
        try:
            widget._redraw(zero_span_error=widget.current_zero_span_error)
        finally:
            widget._frequency_manual_redraw_once = False
    else:
        widget._redraw(zero_span_error=widget.current_zero_span_error)

    if hasattr(widget, "_update_marker_info"):
        widget._update_marker_info()
    if hasattr(widget, "_update_time_marker_info"):
        widget._update_time_marker_info()
    return True
