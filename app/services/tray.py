"""System tray integration backed by Qt's QSystemTrayIcon.

We deliberately use Qt rather than ``pystray`` because the rest of the
UI is Qt-based: that gives us proper integration with the application
event loop, the same icon assets, and native menu rendering on every
platform.  ``pystray`` is still pulled in as a dependency for users who
want to script tray actions from headless contexts.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon


class SystemTrayService:
    def __init__(
        self,
        icon_path: str,
        *,
        on_show: Callable[[], None],
        on_quit: Callable[[], None],
        on_start_all: Callable[[], None],
        on_stop_all: Callable[[], None],
    ) -> None:
        self._tray = QSystemTrayIcon(QIcon(icon_path))
        self._tray.setToolTip("ASMR Broadcast Studio")
        menu = QMenu()
        show_act = QAction("Open dashboard", menu)
        show_act.triggered.connect(on_show)
        menu.addAction(show_act)
        menu.addSeparator()
        start_act = QAction("Start all enabled channels", menu)
        start_act.triggered.connect(on_start_all)
        menu.addAction(start_act)
        stop_act = QAction("Stop all streams", menu)
        stop_act.triggered.connect(on_stop_all)
        menu.addAction(stop_act)
        menu.addSeparator()
        quit_act = QAction("Quit", menu)
        quit_act.triggered.connect(on_quit)
        menu.addAction(quit_act)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(lambda reason: on_show() if reason == QSystemTrayIcon.Trigger else None)
        self._tray.show()

    def notify(self, title: str, message: str, severity: str = "info") -> None:
        icon_type = {
            "info": QSystemTrayIcon.Information,
            "success": QSystemTrayIcon.Information,
            "warning": QSystemTrayIcon.Warning,
            "error": QSystemTrayIcon.Critical,
            "critical": QSystemTrayIcon.Critical,
        }.get(severity, QSystemTrayIcon.Information)
        self._tray.showMessage(title, message, icon_type, 5000)

    def shutdown(self) -> None:
        try:
            self._tray.hide()
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def is_available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable() and bool(QApplication.instance())
