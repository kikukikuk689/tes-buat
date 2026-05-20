"""A frosted-glass styled container."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QVBoxLayout, QWidget


class GlassFrame(QFrame):
    def __init__(self, parent: QWidget | None = None, *, radius: int = 18) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QFrame {{ background: rgba(20, 16, 36, 0.74); "
            f"border: 1px solid rgba(255,255,255,0.08); border-radius: {radius}px; }}"
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 6)
        self.setGraphicsEffect(shadow)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(18, 16, 18, 16)

    def add(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def layout_(self) -> QVBoxLayout:
        return self._layout
