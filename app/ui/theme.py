"""Theme manager: loads QSS files + manages active accent colour."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from ..core.config import get_config
from ..core.logger import get_logger
from ..core.paths import paths


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    qss_file: str
    accent: str
    background: str


THEMES: dict[str, Theme] = {
    "cyberpunk": Theme(
        key="cyberpunk",
        name="Cyberpunk Neon",
        qss_file="cyberpunk.qss",
        accent="#9D4DFF",
        background="#0B0B19",
    ),
    "midnight": Theme(
        key="midnight",
        name="Midnight Black",
        qss_file="midnight.qss",
        accent="#5E9DFF",
        background="#0A0F1A",
    ),
    "purple_neon": Theme(
        key="purple_neon",
        name="Purple Neon",
        qss_file="purple_neon.qss",
        accent="#C264FF",
        background="#170A2A",
    ),
}


class ThemeManager(QObject):
    themeChanged = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._log = get_logger("theme")
        self._current = THEMES.get(get_config().config.theme.active, THEMES["cyberpunk"])

    @property
    def current(self) -> Theme:
        return self._current

    def available(self) -> Iterable[Theme]:
        return THEMES.values()

    def apply(self, app: QApplication, theme_key: str | None = None) -> Theme:
        key = theme_key or self._current.key
        theme = THEMES.get(key, THEMES["cyberpunk"])
        path = paths.themes_dir / theme.qss_file
        qss = path.read_text(encoding="utf-8") if path.exists() else _DEFAULT_QSS
        qss = qss.replace("{ACCENT}", theme.accent).replace("{BG}", theme.background)
        app.setStyleSheet(qss)
        if theme.key != self._current.key:
            self._current = theme
            self.themeChanged.emit(theme.key)
        get_config().update(theme={"active": theme.key, "accent": theme.accent})
        return theme


_DEFAULT_QSS = """
* { color: #E8E8F2; font-family: 'Segoe UI', 'Inter', sans-serif; }
QMainWindow, QDialog { background: {BG}; }
QLabel#accent { color: {ACCENT}; }
QPushButton { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
    border-radius: 10px; padding: 8px 14px; }
QPushButton:hover { background: rgba(157, 77, 255, 0.18); border-color: {ACCENT}; }
"""
