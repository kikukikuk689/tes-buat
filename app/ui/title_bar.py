"""Custom title bar for the frameless main window."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QWidget,
)


class TitleBar(QFrame):
    minimizeClicked = Signal()
    maximizeClicked = Signal()
    closeClicked = Signal()

    def __init__(self, host: QWidget, title: str, subtitle: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("titleBar")
        self.setFixedHeight(48)
        self._host = host
        self._drag_pos: QPoint | None = None

        title_label = QLabel(title)
        title_label.setObjectName("appTitle")
        sub_label = QLabel(subtitle)
        sub_label.setObjectName("appSubtitle")
        text_box = QFrame()
        tb_layout = QHBoxLayout(text_box)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        tb_layout.setSpacing(8)
        tb_layout.addWidget(title_label)
        tb_layout.addWidget(sub_label)

        self.live_indicator = QLabel("●  System idle")
        self.live_indicator.setObjectName("statusIdle")

        self.min_btn = self._mk_btn("—")
        self.max_btn = self._mk_btn("▢")
        self.close_btn = self._mk_btn("✕", role="closeButton")

        self.min_btn.clicked.connect(self.minimizeClicked.emit)
        self.max_btn.clicked.connect(self.maximizeClicked.emit)
        self.close_btn.clicked.connect(self.closeClicked.emit)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 4, 8, 4)
        layout.setSpacing(12)
        layout.addWidget(text_box)
        layout.addItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))
        layout.addWidget(self.live_indicator)
        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.close_btn)

    def set_status(self, text: str, severity: str = "idle") -> None:
        obj_map = {
            "live": "statusLive",
            "idle": "statusIdle",
            "error": "statusError",
            "reconnecting": "statusReconn",
        }
        self.live_indicator.setObjectName(obj_map.get(severity, "statusIdle"))
        self.live_indicator.setText(f"●  {text}")
        self.live_indicator.style().unpolish(self.live_indicator)
        self.live_indicator.style().polish(self.live_indicator)

    def _mk_btn(self, label: str, role: str = "titleAction") -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName(role)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(36, 30)
        return btn

    # Drag-to-move the frameless window ---------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._host.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            self._host.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        self.maximizeClicked.emit()
