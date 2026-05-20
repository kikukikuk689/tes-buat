"""Push button with a subtle hover/scale animation."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QSize, Qt
from PySide6.QtGui import QEnterEvent
from PySide6.QtWidgets import QPushButton


class AnimatedButton(QPushButton):
    """Button that nudges its size on hover for a "premium" feel."""

    def __init__(self, text: str = "", parent=None, role: str = "default") -> None:
        super().__init__(text, parent)
        self.setObjectName(role)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(38)
        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def enterEvent(self, event: QEnterEvent) -> None:  # type: ignore[override]
        super().enterEvent(event)
        self._animate_scale(1.03)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        super().leaveEvent(event)
        self._animate_scale(1.0)

    def _animate_scale(self, factor: float) -> None:
        if not self.parentWidget():
            return
        geo = self.geometry()
        new_size = QSize(int(self.sizeHint().width() * factor), int(self.sizeHint().height() * factor))
        target = QRect(
            geo.center().x() - new_size.width() // 2,
            geo.center().y() - new_size.height() // 2,
            new_size.width(),
            new_size.height(),
        )
        self._anim.stop()
        self._anim.setStartValue(geo)
        self._anim.setEndValue(target)
        self._anim.start()
