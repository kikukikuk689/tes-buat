"""Vertical navigation sidebar."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class NavItem:
    key: str
    title: str
    icon: str  # plain unicode glyph (no font files required)


class Sidebar(QFrame):
    pageChanged = Signal(str)

    def __init__(self, items: list[NavItem], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(232)
        wrap = QVBoxLayout(self)
        wrap.setContentsMargins(16, 20, 16, 18)
        wrap.setSpacing(6)

        brand = QLabel("ASMR\nBROADCAST STUDIO")
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignLeft)
        brand.setFont(QFont("Inter", 11, QFont.Black))
        brand.setStyleSheet("color: #FFFFFF; line-height: 1.0; letter-spacing: 1.6px;")
        wrap.addWidget(brand)
        wrap.addSpacing(18)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        nav_host = QWidget()
        nav_layout = QVBoxLayout(nav_host)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(4)
        for item in items:
            btn = QPushButton(f"  {item.icon}     {item.title}")
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.setIconSize(QSize(20, 20))
            btn.setMinimumHeight(40)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, k=item.key: self._on_clicked(k))
            self._group.addButton(btn)
            self._buttons[item.key] = btn
            nav_layout.addWidget(btn)
        nav_layout.addStretch()
        scroll.setWidget(nav_host)
        wrap.addWidget(scroll, 1)

        footer = QLabel("v1.0  •  Premium Build")
        footer.setStyleSheet("color: #6A6A8A; font-size: 11px;")
        footer.setAlignment(Qt.AlignCenter)
        wrap.addWidget(footer)

    def select(self, key: str) -> None:
        btn = self._buttons.get(key)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)

    def add_listener(self, fn: Callable[[str], None]) -> None:
        self.pageChanged.connect(fn)

    def _on_clicked(self, key: str) -> None:
        self.pageChanged.emit(key)
