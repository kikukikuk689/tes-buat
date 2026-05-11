"""Entry point for Music Spectrum Studio."""
from __future__ import annotations

import os
import sys

# Make sure relative imports resolve when running this file directly.
if __package__ is None or __package__ == "":
    HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, HERE)

from PySide6.QtWidgets import QApplication

from app.gui.main_window import MainWindow
from app.gui.styles import apply_system_theme
from app.utils.logger import AppLogger


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Music Spectrum Studio")
    apply_system_theme(app)
    AppLogger.get().info("Aplikasi dimulai")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
