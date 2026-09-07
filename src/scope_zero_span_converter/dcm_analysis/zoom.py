from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


ZoomTarget = Literal["time", "frequency"]
AxisBounds = tuple[float, float]
ZoomBounds = tuple[AxisBounds, AxisBounds]


def normalized_bounds(a: float, b: float) -> AxisBounds | None:
    """Normalize a dragged interval and reject effectively zero-size ranges."""
    low = float(min(a, b))
    high = float(max(a, b))
    scale = max(abs(low), abs(high), 1.0)
    if high - low <= scale * 1e-12:
        return None
    return low, high


@dataclass
class ZoomState:
    """Transient multi-level zoom state shared by DCM time/frequency views."""

    ranges: dict[ZoomTarget, ZoomBounds | None] = field(
        default_factory=lambda: {"time": None, "frequency": None}
    )
    history: list[tuple[ZoomTarget, ZoomBounds | None]] = field(default_factory=list)

    def push(self, target: ZoomTarget, bounds: ZoomBounds) -> None:
        self.history.append((target, self.ranges[target]))
        self.ranges[target] = bounds

    def undo(self) -> bool:
        if not self.history:
            return False
        target, previous = self.history.pop()
        self.ranges[target] = previous
        return True

    def clear(self, target: ZoomTarget) -> None:
        self.ranges[target] = None
        self.history[:] = [entry for entry in self.history if entry[0] != target]

    def current(self, target: ZoomTarget) -> ZoomBounds | None:
        return self.ranges[target]
