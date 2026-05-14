"""
Preview canvas widget.

The canvas keeps a strict 9:16 aspect ratio and converts mouse events to
**normalized output coordinates** in [0, 1]. The same normalized
coordinates are persisted to the project model and used by both:
  - the preview compositor (this file's parent module)
  - the final FFmpeg render (verticlip.core.render)

So whatever the user sees in the preview is what gets rendered, with no
drift between preview and output regardless of zoom or resolution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from verticlip.core.preview_render import (
    PREVIEW_H,
    PREVIEW_W,
    render_preview_frame,
)
from verticlip.core.project import Project


@dataclass
class DraggableHandle:
    """A reference to something positionable on the canvas."""
    kind: str          # "text" / "part" / "logo"
    index: int         # index in project.texts if kind == "text"; else -1
    # Bounding box in canvas pixels (used to detect hits and draw selection)
    rect: QRect

    def normalized_center(self, w: int, h: int) -> tuple[float, float]:
        cx = (self.rect.x() + self.rect.width() / 2) / max(1, w)
        cy = (self.rect.y() + self.rect.height() / 2) / max(1, h)
        return cx, cy


class PreviewCanvas(QWidget):
    """9:16 video preview that supports precise drag-positioning."""

    selectionChanged = Signal(str, int)   # kind, index
    positionChanged = Signal()            # emitted whenever a drag updates state

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(QSize(PREVIEW_W, PREVIEW_H))
        self.setMouseTracking(True)
        self._project: Optional[Project] = None
        self._frame: Optional[QPixmap] = None
        self._handles: list[DraggableHandle] = []
        self._selected: Optional[tuple[str, int]] = None
        self._drag_offset_norm: Optional[tuple[float, float]] = None
        self._render_size: QSize = QSize(PREVIEW_W, PREVIEW_H)
        self._render_time_s: float = 1.0
        self._show_part: bool = True
        self._part_index_override: Optional[int] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_project(self, project: Project) -> None:
        self._project = project
        self.refresh()

    def set_preview_time(self, t_seconds: float) -> None:
        self._render_time_s = t_seconds
        self.refresh()

    def set_part_preview(self, index: Optional[int]) -> None:
        self._part_index_override = index
        self.refresh()

    def selected(self) -> Optional[tuple[str, int]]:
        return self._selected

    def select(self, kind: str, index: int = -1) -> None:
        self._selected = (kind, index)
        self.selectionChanged.emit(kind, index)
        self.update()

    def refresh(self) -> None:
        if self._project is None:
            self._frame = None
            self.update()
            return
        size = self._compute_render_size()
        self._render_size = size
        frame = render_preview_frame(
            self._project,
            t_seconds=self._render_time_s,
            target_size=(size.width(), size.height()),
            part_index=self._part_index_override,
            show_part_text=self._show_part,
        )
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, _ = rgb.shape
        img = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888).copy()
        self._frame = QPixmap.fromImage(img)
        self._handles = self._compute_handles(size)
        self.update()

    # ------------------------------------------------------------------
    # Layout / sizing
    # ------------------------------------------------------------------
    def heightForWidth(self, w: int) -> int:  # pragma: no cover - widget hint
        return int(w * 16 / 9)

    def hasHeightForWidth(self) -> bool:  # pragma: no cover - widget hint
        return True

    def _compute_render_size(self) -> QSize:
        w_avail = max(120, self.width())
        h_avail = max(120, self.height())
        # Fit a 9:16 box inside the widget while preserving aspect.
        if w_avail * 16 <= h_avail * 9:
            w = w_avail
            h = int(round(w * 16 / 9))
        else:
            h = h_avail
            w = int(round(h * 9 / 16))
        return QSize(max(90, w), max(160, h))

    def _frame_top_left(self) -> QPoint:
        x = (self.width() - self._render_size.width()) // 2
        y = (self.height() - self._render_size.height()) // 2
        return QPoint(max(0, x), max(0, y))

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0F1013"))
        tl = self._frame_top_left()
        if self._frame is None:
            painter.setPen(QColor("#888"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Pilih video sumber\nuntuk memulai")
            painter.end()
            return
        painter.drawPixmap(tl, self._frame)

        # Selection outline
        if self._selected is not None:
            kind, idx = self._selected
            for h in self._handles:
                if h.kind == kind and h.index == idx:
                    pen = QPen(QColor("#4F7CFF"))
                    pen.setWidth(2)
                    painter.setPen(pen)
                    rect = QRect(
                        h.rect.x() + tl.x() - 4,
                        h.rect.y() + tl.y() - 4,
                        h.rect.width() + 8,
                        h.rect.height() + 8,
                    )
                    painter.drawRect(rect)
                    break

        # Indicator: 9:16 hint
        painter.setPen(QColor("#555"))
        painter.drawRect(tl.x(), tl.y(), self._render_size.width() - 1, self._render_size.height() - 1)
        painter.end()

    # ------------------------------------------------------------------
    # Handles
    # ------------------------------------------------------------------
    def _compute_handles(self, size: QSize) -> list[DraggableHandle]:
        handles: list[DraggableHandle] = []
        if self._project is None:
            return handles
        w, h = size.width(), size.height()

        # Texts: approximate bbox by font size
        for i, t in enumerate(self._project.texts):
            box_w, box_h = self._approx_text_size(t.text, t.font_size, h)
            cx = int(round(t.x * w))
            cy = int(round(t.y * h))
            r = QRect(cx - box_w // 2, cy - box_h // 2, box_w, box_h)
            handles.append(DraggableHandle("text", i, r))

        # Part text
        if self._project.part_text.enabled:
            p = self._project.part_text
            idx = self._part_index_override if self._part_index_override is not None else p.start_index
            label = f"{p.label} {idx}"
            box_w, box_h = self._approx_text_size(label, p.font_size, h)
            cx = int(round(p.x * w))
            cy = int(round(p.y * h))
            r = QRect(cx - box_w // 2, cy - box_h // 2, box_w, box_h)
            handles.append(DraggableHandle("part", -1, r))

        # Logo
        if self._project.logo.path:
            logo_w = max(10, int(round(self._project.logo.size * w)))
            # Without loading we estimate aspect 1:1; close enough for selection box.
            logo_h = logo_w
            cx = int(round(self._project.logo.x * w))
            cy = int(round(self._project.logo.y * h))
            r = QRect(cx - logo_w // 2, cy - logo_h // 2, logo_w, logo_h)
            handles.append(DraggableHandle("logo", -1, r))

        return handles

    @staticmethod
    def _approx_text_size(text: str, font_size_pt: int, canvas_h: int) -> tuple[int, int]:
        from verticlip.core.project import REFERENCE_HEIGHT
        scale = canvas_h / REFERENCE_HEIGHT
        px = max(8, int(font_size_pt * scale))
        # Approx character width 0.6 of size
        w = int(max(20, len(text) * px * 0.6))
        h = int(max(px + 8, px * 1.4))
        return w, h

    # ------------------------------------------------------------------
    # Mouse handling -> updates project state with normalized coords
    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if self._project is None:
            return
        pos = event.position().toPoint()
        tl = self._frame_top_left()
        # Topmost-first
        for h in reversed(self._handles):
            local = QRect(
                h.rect.x() + tl.x(), h.rect.y() + tl.y(),
                h.rect.width(), h.rect.height(),
            )
            if local.contains(pos):
                self.select(h.kind, h.index)
                cx_norm, cy_norm = self._handle_center_normalized(h)
                pos_norm = self._point_to_norm(pos)
                self._drag_offset_norm = (cx_norm - pos_norm[0], cy_norm - pos_norm[1])
                return
        # Click on background -> deselect
        self._drag_offset_norm = None
        self.select("", -1)

    def mouseMoveEvent(self, event) -> None:
        if self._project is None or self._selected is None:
            return
        kind, idx = self._selected
        if not kind or self._drag_offset_norm is None:
            return
        pos = event.position().toPoint()
        nx, ny = self._point_to_norm(pos)
        ox, oy = self._drag_offset_norm
        nx = min(1.0, max(0.0, nx + ox))
        ny = min(1.0, max(0.0, ny + oy))
        self._apply_position(kind, idx, nx, ny)
        self.positionChanged.emit()
        self.refresh()

    def mouseReleaseEvent(self, _event) -> None:
        self._drag_offset_norm = None

    # ------------------------------------------------------------------
    def _handle_center_normalized(self, h: DraggableHandle) -> tuple[float, float]:
        return h.normalized_center(self._render_size.width(), self._render_size.height())

    def _point_to_norm(self, pos: QPoint) -> tuple[float, float]:
        tl = self._frame_top_left()
        w = max(1, self._render_size.width())
        h = max(1, self._render_size.height())
        x = (pos.x() - tl.x()) / w
        y = (pos.y() - tl.y()) / h
        return (x, y)

    def _apply_position(self, kind: str, idx: int, nx: float, ny: float) -> None:
        if self._project is None:
            return
        if kind == "text" and 0 <= idx < len(self._project.texts):
            self._project.texts[idx].x = nx
            self._project.texts[idx].y = ny
        elif kind == "part":
            self._project.part_text.x = nx
            self._project.part_text.y = ny
        elif kind == "logo":
            self._project.logo.x = nx
            self._project.logo.y = ny

    # Allow external code to ask for refresh after non-drag mutations
    def schedule_refresh(self) -> None:
        self.refresh()
