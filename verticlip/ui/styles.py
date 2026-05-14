"""Dark, professional Qt theme."""
from __future__ import annotations

from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication


STYLE_SHEET = """
* {
    font-family: "Segoe UI", "Inter", "Roboto", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    color: #E6E6E6;
}
QMainWindow, QDialog, QWidget {
    background-color: #1E1F22;
}
QGroupBox {
    border: 1px solid #313338;
    border-radius: 8px;
    margin-top: 14px;
    padding: 10px 8px 8px 8px;
    background-color: #25272B;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #B8C0D0;
    font-weight: 600;
}
QLabel#sectionTitle {
    font-size: 14px;
    font-weight: 600;
    color: #B8C0D0;
}
QLabel#statusOk { color: #5CD18E; }
QLabel#statusBad { color: #F88; }
QLabel#statusWarn { color: #FFC857; }
QLabel#headerTitle {
    font-size: 18px;
    font-weight: 700;
    color: #FFFFFF;
    letter-spacing: 0.5px;
}
QPushButton {
    background-color: #353841;
    border: 1px solid #3F424B;
    border-radius: 6px;
    padding: 6px 12px;
    color: #EDEDED;
}
QPushButton:hover { background-color: #3F424B; }
QPushButton:pressed { background-color: #2C2E36; }
QPushButton:disabled { color: #777; background-color: #2A2C32; }
QPushButton#primary {
    background-color: #4F7CFF;
    border: 1px solid #4F7CFF;
    color: white;
    font-weight: 600;
}
QPushButton#primary:hover { background-color: #6B91FF; }
QPushButton#danger {
    background-color: #E55353;
    border: 1px solid #E55353;
    color: white;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {
    background-color: #2A2C32;
    border: 1px solid #3A3D45;
    border-radius: 6px;
    padding: 4px 6px;
    selection-background-color: #4F7CFF;
}
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: #2A2C32;
    border: 1px solid #3A3D45;
    selection-background-color: #4F7CFF;
}
QSlider::groove:horizontal {
    height: 4px;
    background: #3A3D45;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #4F7CFF;
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 7px;
}
QProgressBar {
    background-color: #2A2C32;
    border: 1px solid #3A3D45;
    border-radius: 6px;
    text-align: center;
    color: #E6E6E6;
}
QProgressBar::chunk {
    background-color: #4F7CFF;
    border-radius: 6px;
}
QTabWidget::pane { border: 1px solid #313338; border-radius: 6px; top: -1px; }
QTabBar::tab {
    background: #25272B;
    color: #B8C0D0;
    padding: 6px 12px;
    border: 1px solid #313338;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #1E1F22;
    color: #FFFFFF;
    border-bottom: 1px solid #1E1F22;
}
QListWidget {
    background-color: #25272B;
    border: 1px solid #313338;
    border-radius: 6px;
}
QListWidget::item:selected {
    background-color: #4F7CFF;
    color: white;
}
QToolTip {
    background-color: #2A2C32;
    border: 1px solid #4F7CFF;
    color: #EDEDED;
    padding: 4px;
}
QStatusBar { background: #181A1D; color: #B8C0D0; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px; height: 16px;
}
QScrollBar:vertical {
    background: #1E1F22;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #3A3D45;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""


def apply_dark_theme(app: QApplication) -> None:
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#1E1F22"))
    palette.setColor(QPalette.WindowText, QColor("#E6E6E6"))
    palette.setColor(QPalette.Base, QColor("#2A2C32"))
    palette.setColor(QPalette.AlternateBase, QColor("#25272B"))
    palette.setColor(QPalette.ToolTipBase, QColor("#2A2C32"))
    palette.setColor(QPalette.ToolTipText, QColor("#E6E6E6"))
    palette.setColor(QPalette.Text, QColor("#E6E6E6"))
    palette.setColor(QPalette.Button, QColor("#353841"))
    palette.setColor(QPalette.ButtonText, QColor("#E6E6E6"))
    palette.setColor(QPalette.Highlight, QColor("#4F7CFF"))
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)
    app.setStyleSheet(STYLE_SHEET)
