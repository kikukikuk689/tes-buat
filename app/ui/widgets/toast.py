"""Floating toast notifications stacked at the bottom-right of the window."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class Toast(QFrame):
    def __init__(
        self,
        title: str,
        message: str,
        severity: str = "info",
        duration_ms: int = 4500,
        parent=None,
    ) -> None:
        super().__init__(parent)
        obj_map = {
            "info": "toastInfo",
            "success": "toastSuccess",
            "warning": "toastWarning",
            "error": "toastError",
            "critical": "toastError",
        }
        self.setObjectName(obj_map.get(severity, "toast"))
        self.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 18, 12)
        layout.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet("font-weight: 700; color: #FFFFFF;")
        m = QLabel(message)
        m.setWordWrap(True)
        m.setStyleSheet("color: #C5C5DC;")
        layout.addWidget(t)
        layout.addWidget(m)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 200))
        shadow.setOffset(0, 6)
        self.setGraphicsEffect(shadow)
        self._opacity_effect: QGraphicsOpacityEffect | None = None
        self.duration_ms = duration_ms

    def fade_out(self) -> None:
        if self._opacity_effect is None:
            self._opacity_effect = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(self._opacity_effect)
        anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        anim.setDuration(280)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self.deleteLater)
        anim.start()


class ToastStack(QWidget):
    """Container that manages a column of toasts in the bottom-right."""

    margin = 18
    spacing = 10

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._toasts: list[Toast] = []
        self._host = parent
        self._host.installEventFilter(self)
        self.setGeometry(0, 0, parent.width(), parent.height())

    def eventFilter(self, watched, event):  # type: ignore[override]
        if watched is self._host and event.type().name == "Resize":
            self.setGeometry(0, 0, self._host.width(), self._host.height())
            self._relayout()
        return super().eventFilter(watched, event)

    def show_toast(self, title: str, message: str, severity: str = "info", duration_ms: int = 4500) -> None:
        toast = Toast(title, message, severity, duration_ms, parent=self)
        toast.setFixedWidth(360)
        toast.adjustSize()
        self._toasts.append(toast)
        toast.destroyed.connect(lambda *_: self._on_toast_destroyed(toast))
        self._relayout(new=toast)
        QTimer.singleShot(duration_ms, toast.fade_out)

    def _on_toast_destroyed(self, toast: Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        self._relayout()

    def _relayout(self, new: Toast | None = None) -> None:
        y = self.height() - self.margin
        for t in reversed(self._toasts):
            t.adjustSize()
            y -= t.height()
            x = self.width() - t.width() - self.margin
            if t is new:
                t.move(x + 240, y)
                t.show()
                anim = QPropertyAnimation(t, b"pos", t)
                anim.setDuration(240)
                anim.setEasingCurve(QEasingCurve.OutCubic)
                anim.setEndValue(QPoint(x, y))
                anim.start()
            else:
                t.move(x, y)
            y -= self.spacing
