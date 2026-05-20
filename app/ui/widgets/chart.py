"""Lightweight sparkline / line chart widget.

Pure QPainter implementation — no dependency on QtCharts.  Suitable for
the dashboard's realtime CPU / network / bitrate strips.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class SparklineChart(QWidget):
    def __init__(
        self,
        capacity: int = 60,
        color: str = "#9D4DFF",
        fill: bool = True,
        min_y: float | None = 0.0,
        max_y: float | None = None,
        title: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._values: deque[float] = deque(maxlen=capacity)
        self._color = QColor(color)
        self._fill = fill
        self._min_y = min_y
        self._max_y = max_y
        self._title = title
        self.setMinimumHeight(80)

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def push(self, value: float) -> None:
        self._values.append(float(value))
        self.update()

    def set_values(self, values: Iterable[float]) -> None:
        self._values.clear()
        for v in values:
            self._values.append(float(v))
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(8, 8, -8, -8)

        # Title
        if self._title:
            painter.setPen(QColor("#8A8AAE"))
            font = painter.font()
            font.setPointSizeF(8.5)
            painter.setFont(font)
            painter.drawText(rect.adjusted(0, 0, 0, -rect.height() + 14), Qt.AlignLeft, self._title.upper())

        if len(self._values) < 2:
            painter.setPen(QColor("#3D3D62"))
            painter.drawText(rect, Qt.AlignCenter, "waiting for data…")
            return

        values = list(self._values)
        min_y = self._min_y if self._min_y is not None else min(values)
        max_y = self._max_y if self._max_y is not None else max(values)
        if max_y <= min_y:
            max_y = min_y + 1.0
        chart_rect = rect.adjusted(0, 18, 0, 0)

        # Grid
        grid_pen = QPen(QColor(255, 255, 255, 18))
        grid_pen.setStyle(Qt.DashLine)
        painter.setPen(grid_pen)
        for i in range(1, 4):
            y = chart_rect.top() + chart_rect.height() * i / 4
            painter.drawLine(chart_rect.left(), int(y), chart_rect.right(), int(y))

        # Path
        path = QPainterPath()
        n = len(values)
        for i, v in enumerate(values):
            x = chart_rect.left() + (chart_rect.width() * i / (n - 1))
            y = chart_rect.bottom() - ((v - min_y) / (max_y - min_y)) * chart_rect.height()
            if i == 0:
                path.moveTo(QPointF(x, y))
            else:
                path.lineTo(QPointF(x, y))

        if self._fill:
            fill = QPainterPath(path)
            fill.lineTo(chart_rect.right(), chart_rect.bottom())
            fill.lineTo(chart_rect.left(), chart_rect.bottom())
            fill.closeSubpath()
            grad = QLinearGradient(0, chart_rect.top(), 0, chart_rect.bottom())
            top = QColor(self._color)
            top.setAlpha(120)
            bottom = QColor(self._color)
            bottom.setAlpha(0)
            grad.setColorAt(0.0, top)
            grad.setColorAt(1.0, bottom)
            painter.fillPath(fill, grad)

        pen = QPen(self._color)
        pen.setWidthF(2.0)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)

        # Latest dot
        last_x = chart_rect.right()
        last_y = chart_rect.bottom() - ((values[-1] - min_y) / (max_y - min_y)) * chart_rect.height()
        painter.setBrush(self._color)
        painter.drawEllipse(QPointF(last_x, last_y), 3.4, 3.4)
