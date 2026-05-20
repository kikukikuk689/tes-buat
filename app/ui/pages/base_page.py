"""Common base class for every navigation page."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class BasePage(QWidget):
    """Provides a styled header strip and a content area."""

    title: str = "Page"
    subtitle: str = ""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(18)

        header = QFrame()
        header.setObjectName("pageHeader")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)
        title_box = QVBoxLayout()
        self.title_label = QLabel(self.title)
        self.title_label.setStyleSheet("color: #FFFFFF; font-size: 22px; font-weight: 800;")
        self.subtitle_label = QLabel(self.subtitle)
        self.subtitle_label.setStyleSheet("color: #8A8AAE; font-size: 12px;")
        self.subtitle_label.setVisible(bool(self.subtitle))
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        h_layout.addLayout(title_box, 1)
        self._header_extra = QHBoxLayout()
        self._header_extra.setSpacing(8)
        h_layout.addLayout(self._header_extra)
        outer.addWidget(header)

        self.content_layout = QVBoxLayout()
        self.content_layout.setSpacing(16)
        outer.addLayout(self.content_layout, 1)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.on_refresh_tick)
        self._refresh_timer.setInterval(1500)

    # ------------------------------------------------------------------
    # Hooks for subclasses
    # ------------------------------------------------------------------
    def add_header_widget(self, widget: QWidget) -> None:
        self._header_extra.addWidget(widget)

    def add_header_label(self, text: str, *, role: str = "") -> QLabel:
        label = QLabel(text)
        if role:
            label.setObjectName(role)
        label.setAlignment(Qt.AlignVCenter)
        label.setFont(QFont("Inter", 11, QFont.Medium))
        self._header_extra.addWidget(label)
        return label

    def set_title(self, title: str, subtitle: str = "") -> None:
        self.title_label.setText(title)
        if subtitle:
            self.subtitle_label.setText(subtitle)
            self.subtitle_label.setVisible(True)

    def on_show(self) -> None:
        self._refresh_timer.start()

    def on_hide(self) -> None:
        self._refresh_timer.stop()

    def on_refresh_tick(self) -> None:
        """Override to update UI periodically."""
