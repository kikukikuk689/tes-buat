"""Theme manager page."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QHBoxLayout,
    QPushButton,
    QWidget,
)

from ...core.config import get_config
from ...services import get_notifier
from ..widgets import Card
from .base_page import BasePage


class ThemePage(BasePage):
    title = "Theme Manager"
    subtitle = "Switch theme; tweak accent and animations"

    def __init__(self, theme_manager, parent=None) -> None:
        super().__init__(parent)
        self.theme_manager = theme_manager

        card = Card("Available themes", glow=True)
        host = QWidget()
        h = QHBoxLayout(host)
        h.setSpacing(12)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for theme in theme_manager.available():
            btn = QPushButton(theme.name)
            btn.setCheckable(True)
            btn.setMinimumHeight(56)
            btn.setStyleSheet(
                "QPushButton { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.10); "
                "border-radius: 12px; font-weight: 700; padding: 12px 18px; }"
                f"QPushButton:checked {{ border: 2px solid {theme.accent}; color: {theme.accent}; }}"
            )
            if theme.key == theme_manager.current.key:
                btn.setChecked(True)
            btn.clicked.connect(lambda _, k=theme.key: self._apply(k))
            self.group.addButton(btn)
            h.addWidget(btn)
        card.content_layout.addWidget(host)
        self.content_layout.addWidget(card)

        toggles = Card("Visual options")
        cfg = get_config().config.theme
        self.anim = QCheckBox("Smooth animations")
        self.anim.setChecked(cfg.enable_animations)
        self.blur = QCheckBox("Glassmorphism / blur")
        self.blur.setChecked(cfg.enable_blur)
        toggles.content_layout.addWidget(self.anim)
        toggles.content_layout.addWidget(self.blur)
        save_row = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(self._save)
        save_row.addWidget(self.save_btn)
        save_row.addStretch()
        toggles.content_layout.addLayout(save_row)
        self.content_layout.addWidget(toggles)

    def _apply(self, key: str) -> None:
        from PySide6.QtWidgets import QApplication

        self.theme_manager.apply(QApplication.instance(), key)
        get_notifier().notify("Theme", f"Switched to {key}", "success")

    def _save(self) -> None:
        get_config().update(
            theme={
                "enable_animations": self.anim.isChecked(),
                "enable_blur": self.blur.isChecked(),
            }
        )
        get_notifier().notify("Theme", "Visual options saved", "success")
