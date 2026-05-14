"""Main application window for VertiClip Studio."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from verticlip import APP_NAME, __version__
from verticlip.core.project import Project
from verticlip.ui.controls_panel import ControlsPanel
from verticlip.ui.ffmpeg_status import FFmpegStatusWidget
from verticlip.ui.preview_canvas import PreviewCanvas
from verticlip.ui.render_panel import RenderPanel


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{__version__}")
        self.resize(1380, 880)
        self.project = Project()

        # Add one sample text to make the canvas useful out of the box
        self.project.texts.clear()

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QWidget()
        header.setStyleSheet("background-color: #181A1D; border-bottom: 1px solid #2A2D33;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 10, 16, 10)
        title = QLabel(APP_NAME)
        title.setObjectName("headerTitle")
        subtitle = QLabel("9:16 Vertical Clip Composer")
        subtitle.setStyleSheet("color: #777; padding-left: 12px;")
        h_layout.addWidget(title)
        h_layout.addWidget(subtitle)
        h_layout.addStretch(1)
        self.ffmpeg_status = FFmpegStatusWidget()
        self.ffmpeg_status.statusChanged.connect(self._on_ffmpeg_status)
        h_layout.addWidget(self.ffmpeg_status)
        root.addWidget(header)

        # Top split: controls | preview
        splitter = QSplitter(Qt.Horizontal)
        self.controls = ControlsPanel(self.project)
        self.preview = PreviewCanvas()
        self.preview.set_project(self.project)
        preview_wrap = QWidget()
        pw_layout = QVBoxLayout(preview_wrap)
        pw_layout.setContentsMargins(8, 8, 8, 8)
        preview_title = QLabel("Preview (9:16) - klik dan drag elemen, posisi tepat sesuai render")
        preview_title.setObjectName("sectionTitle")
        pw_layout.addWidget(preview_title)
        pw_layout.addWidget(self.preview, 1)
        splitter.addWidget(self.controls)
        splitter.addWidget(preview_wrap)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([620, 760])
        root.addWidget(splitter, 1)

        # Bottom render panel
        self.render_panel = RenderPanel(self.project)
        self.render_panel.statusMessage.connect(self.statusBar().showMessage)
        root.addWidget(self.render_panel)

        self.setCentralWidget(central)
        self.statusBar().showMessage("Siap.")

        # Wire up signals
        self.controls.refreshRequested.connect(self._refresh_preview)
        self.controls.selectionChanged.connect(self._on_controls_selection)
        self.preview.selectionChanged.connect(self._on_preview_selection)
        self.preview.positionChanged.connect(self._on_preview_position_changed)

        # Keyboard shortcut: Esc to deselect
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=lambda: self.preview.select("", -1))

    def _refresh_preview(self) -> None:
        # apply previewed part index from controls panel
        if self.project.part_text.enabled:
            self.preview.set_part_preview(self.controls.preview_part_index)
        else:
            self.preview.set_part_preview(None)
        self.preview.refresh()

    def _on_controls_selection(self, kind: str, index: int) -> None:
        self.preview.select(kind, index)

    def _on_preview_selection(self, kind: str, index: int) -> None:
        if not kind:
            return
        self.controls.show_for_selection(kind, index)

    def _on_preview_position_changed(self) -> None:
        sel = self.preview.selected()
        if sel is None:
            return
        kind, idx = sel
        self.controls.sync_after_drag(kind, idx)
        self.statusBar().showMessage(self._format_position_status(kind, idx))

    def _format_position_status(self, kind: str, idx: int) -> str:
        if kind == "text" and 0 <= idx < len(self.project.texts):
            t = self.project.texts[idx]
            return f"Teks {idx + 1}: x={t.x:.4f}, y={t.y:.4f} (norm)"
        if kind == "part":
            p = self.project.part_text
            return f"Part text: x={p.x:.4f}, y={p.y:.4f} (norm)"
        if kind == "logo":
            l = self.project.logo
            return f"Logo: x={l.x:.4f}, y={l.y:.4f} (norm)"
        return ""

    def _on_ffmpeg_status(self, st) -> None:
        # Disable render button when ffmpeg missing
        self.render_panel.render_btn.setEnabled(bool(st.available))
        if not st.available:
            self.statusBar().showMessage("FFmpeg belum terinstall - klik 'Install FFmpeg'.")

    def resizeEvent(self, event) -> None:  # pragma: no cover - GUI behaviour
        super().resizeEvent(event)
        self.preview.refresh()
