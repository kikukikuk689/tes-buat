"""Entry point: ``python -m verticlip``."""
from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from verticlip import APP_NAME
    from verticlip.ui.main_window import MainWindow
    from verticlip.ui.styles import apply_dark_theme

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("VertiClip")
    apply_dark_theme(app)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
