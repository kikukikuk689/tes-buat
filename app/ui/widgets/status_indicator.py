"""Live-status pill widget."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QLabel

_STATE_COLORS = {
    "live": "#2AD27D",
    "starting": "#FFC857",
    "reconnecting": "#FFC857",
    "paused": "#6BBCFF",
    "stopping": "#9D4DFF",
    "idle": "#7A7AA0",
    "error": "#FF4D6D",
    "unknown": "#7A7AA0",
}


class StatusBadge(QLabel):
    """A circular dot + label.  Use :py:meth:`set_state` to update."""

    def __init__(self, state: str = "idle", parent=None) -> None:
        super().__init__(parent)
        self._state = state.lower()
        self.setMinimumHeight(22)
        self.setFont(QFont("Inter", 9, QFont.DemiBold))
        self.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self._refresh_text()

    def state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
        self._state = state.lower() if state else "idle"
        self._refresh_text()
        self.update()

    def _refresh_text(self) -> None:
        self.setText(f"   {self._state.upper()}")
        color = _STATE_COLORS.get(self._state, "#7A7AA0")
        self.setStyleSheet(f"color: {color};")

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(_STATE_COLORS.get(self._state, "#7A7AA0"))
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        cy = self.height() // 2
        p.drawEllipse(2, cy - 5, 10, 10)
        if self._state in {"live", "reconnecting", "starting"}:
            ring = QColor(color)
            ring.setAlpha(80)
            p.setBrush(Qt.NoBrush)
            p.setPen(ring)
            p.drawEllipse(0, cy - 7, 14, 14)
