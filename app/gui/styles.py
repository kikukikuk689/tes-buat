"""Light theme styling tuned for a modern professional look.

The app follows the system theme automatically when ``apply_system_theme``
is used; otherwise the light theme is forced via ``apply_light_theme``.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication


LIGHT_QSS = """
QMainWindow, QDialog, QWidget {
    background: #f6f7fb;
    color: #1d1f2a;
    font-family: 'Segoe UI', 'Inter', 'Roboto', sans-serif;
    font-size: 10pt;
}
QGroupBox {
    border: 1px solid #d3d6e0;
    border-radius: 10px;
    margin-top: 14px;
    background: #ffffff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #43485c;
    font-weight: 600;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #c5c9d6;
    border-radius: 8px;
    padding: 6px 14px;
    color: #1d1f2a;
}
QPushButton:hover { background: #eef0f7; }
QPushButton:pressed { background: #dce0ef; }
QPushButton#primary {
    background: #4f7cff;
    color: #ffffff;
    border: 1px solid #3960e5;
    font-weight: 600;
}
QPushButton#primary:hover { background: #3e6cff; }
QPushButton#primary:pressed { background: #2854db; }
QPushButton#danger {
    background: #ff5b6b;
    color: white;
    border: 1px solid #d94455;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QListWidget {
    background: #ffffff;
    border: 1px solid #c5c9d6;
    border-radius: 6px;
    padding: 4px 6px;
    selection-background-color: #4f7cff;
    selection-color: #ffffff;
}
QPlainTextEdit { font-family: 'Cascadia Mono', 'JetBrains Mono', monospace; font-size: 9pt; }
QSlider::groove:horizontal {
    height: 6px;
    background: #d8dbe6;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #4f7cff;
    border-radius: 8px;
    width: 16px;
    margin: -6px 0;
}
QTabWidget::pane {
    border: 1px solid #d3d6e0;
    border-radius: 10px;
    background: #ffffff;
    top: -1px;
}
QTabBar::tab {
    padding: 7px 16px;
    background: #ebedf3;
    border: 1px solid #d3d6e0;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 2px;
}
QTabBar::tab:selected { background: #ffffff; color: #1d1f2a; font-weight: 600; }
QProgressBar {
    border: 1px solid #c5c9d6;
    border-radius: 6px;
    background: #ffffff;
    text-align: center;
    color: #1d1f2a;
    height: 18px;
}
QProgressBar::chunk {
    background: #4f7cff;
    border-radius: 5px;
}
QLabel[class="muted"] { color: #6a6f80; }
QStatusBar { background: #ebedf3; }
QCheckBox { spacing: 6px; }
"""


def apply_light_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor("#f6f7fb"))
    pal.setColor(QPalette.ColorRole.WindowText, QColor("#1d1f2a"))
    pal.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#eef0f7"))
    pal.setColor(QPalette.ColorRole.Text, QColor("#1d1f2a"))
    pal.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor("#1d1f2a"))
    pal.setColor(QPalette.ColorRole.Highlight, QColor("#4f7cff"))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)
    app.setStyleSheet(LIGHT_QSS)


def apply_system_theme(app: QApplication) -> None:
    """Let Qt follow the OS palette but apply our QSS for consistency."""
    app.setStyle("Fusion")
    app.setStyleSheet(LIGHT_QSS)
