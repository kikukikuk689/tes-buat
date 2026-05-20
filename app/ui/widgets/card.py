"""Card / MetricCard widgets."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


def _drop_shadow(widget: QWidget, blur: int = 24, color: str = "#9D4DFF", offset: int = 0) -> None:
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    c = QColor(color)
    c.setAlpha(110)
    eff.setColor(c)
    eff.setOffset(0, offset)
    widget.setGraphicsEffect(eff)


class Card(QFrame):
    """A rounded panel with title + content."""

    def __init__(self, title: str = "", subtitle: str = "", *, glow: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("cardGlow" if glow else "card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumHeight(110)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 18)
        layout.setSpacing(8)
        if title:
            self.title_label = QLabel(title)
            self.title_label.setProperty("class", "cardTitle")
            self.title_label.setObjectName("cardTitle")
            layout.addWidget(self.title_label)
        if subtitle:
            self.subtitle_label = QLabel(subtitle)
            self.subtitle_label.setProperty("class", "cardCaption")
            self.subtitle_label.setObjectName("cardCaption")
            layout.addWidget(self.subtitle_label)
        self.content_layout = layout
        if glow:
            _drop_shadow(self, blur=28, color="#9D4DFF", offset=0)


class MetricCard(Card):
    """A card that prominently displays a single metric value."""

    def __init__(
        self,
        title: str,
        value: str = "0",
        caption: str = "",
        *,
        glow: bool = False,
        parent=None,
    ) -> None:
        super().__init__(title=title, glow=glow, parent=parent)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("cardValue")
        self.value_label.setProperty("class", "cardValue")
        self.value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.caption_label = QLabel(caption)
        self.caption_label.setObjectName("cardCaption")
        self.caption_label.setProperty("class", "cardCaption")
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.value_label)
        self.content_layout.addLayout(row)
        self.content_layout.addWidget(self.caption_label)
        self.content_layout.addStretch()

    def set_value(self, value: str, caption: str | None = None) -> None:
        self.value_label.setText(value)
        if caption is not None:
            self.caption_label.setText(caption)
