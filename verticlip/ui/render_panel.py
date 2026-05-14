"""Bottom render-settings panel + render button."""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from verticlip.core.project import Project
from verticlip.core.render import render_project


# (label, height) - height drives 9:16; width auto-computed.
RESOLUTION_PRESETS = [
    ("HD  720x1280", 1280),
    ("Full HD  1080x1920", 1920),
    ("QHD/2K  1440x2560", 2560),
]


class _RenderWorker(QObject):
    progress = Signal(float, str)
    finished = Signal(bool, str, list)

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project

    def run(self) -> None:
        try:
            outputs = render_project(
                self.project,
                progress=lambda p, m: self.progress.emit(p, m),
            )
            self.finished.emit(True, f"Selesai. {len(outputs)} file dirender.", outputs)
        except Exception as exc:
            self.finished.emit(False, str(exc), [])


class RenderPanel(QWidget):
    statusMessage = Signal(str)

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self._thread: Optional[QThread] = None
        self._worker: Optional[_RenderWorker] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)

        settings = QGroupBox("Render Settings")
        form = QFormLayout(settings)

        self.res_combo = QComboBox()
        for label, h in RESOLUTION_PRESETS:
            self.res_combo.addItem(label, h)
        self.res_combo.setCurrentIndex(1)  # Default 1080x1920
        self.res_combo.currentIndexChanged.connect(self._res_changed)
        form.addRow("Resolusi:", self.res_combo)

        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(15, 60)
        self.fps_spin.setValue(project.render.fps)
        self.fps_spin.valueChanged.connect(self._fps_changed)
        form.addRow("FPS:", self.fps_spin)

        self.crf_spin = QSpinBox()
        self.crf_spin.setRange(10, 35)
        self.crf_spin.setValue(project.render.crf)
        self.crf_spin.valueChanged.connect(self._crf_changed)
        form.addRow("Quality (CRF):", self.crf_spin)

        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "ultrafast", "superfast", "veryfast", "faster", "fast",
            "medium", "slow", "slower", "veryslow",
        ])
        self.preset_combo.setCurrentText(project.render.preset)
        self.preset_combo.currentTextChanged.connect(self._preset_changed)
        form.addRow("Encoder preset:", self.preset_combo)

        out_row = QWidget()
        orl = QHBoxLayout(out_row)
        orl.setContentsMargins(0, 0, 0, 0)
        self.out_dir_edit = QLineEdit(project.render.output_dir)
        self.out_dir_edit.setReadOnly(True)
        out_btn = QPushButton("Pilih folder ...")
        out_btn.clicked.connect(self._pick_out_dir)
        orl.addWidget(self.out_dir_edit, 1)
        orl.addWidget(out_btn)
        form.addRow("Folder output:", out_row)

        self.prefix_edit = QLineEdit(project.render.file_prefix)
        self.prefix_edit.textChanged.connect(self._prefix_changed)
        form.addRow("Nama file (prefix):", self.prefix_edit)

        layout.addWidget(settings, 2)

        # Right side: status + render button
        action_panel = QGroupBox("Render")
        action_layout = QVBoxLayout(action_panel)
        self.bar = QProgressBar()
        self.bar.setValue(0)
        self.status_label = QLabel("Siap render.")
        self.render_btn = QPushButton("RENDER VIDEO")
        self.render_btn.setObjectName("primary")
        self.render_btn.setMinimumHeight(46)
        self.render_btn.clicked.connect(self._start_render)
        self.open_btn = QPushButton("Buka folder output")
        self.open_btn.clicked.connect(self._open_output)
        action_layout.addWidget(self.bar)
        action_layout.addWidget(self.status_label)
        action_layout.addWidget(self.render_btn)
        action_layout.addWidget(self.open_btn)
        action_layout.addStretch(1)
        layout.addWidget(action_panel, 1)

    # ---- field callbacks ----
    def _res_changed(self) -> None:
        self.project.render.output_height = int(self.res_combo.currentData())

    def _fps_changed(self, v: int) -> None:
        self.project.render.fps = v

    def _crf_changed(self, v: int) -> None:
        self.project.render.crf = v

    def _preset_changed(self, s: str) -> None:
        self.project.render.preset = s

    def _pick_out_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Pilih folder output")
        if path:
            self.project.render.output_dir = path
            self.out_dir_edit.setText(path)

    def _prefix_changed(self, s: str) -> None:
        self.project.render.file_prefix = s

    def _open_output(self) -> None:
        path = self.project.render.output_dir
        if not path or not os.path.isdir(path):
            QMessageBox.information(self, "Folder output", "Folder output belum dipilih atau tidak ada.")
            return
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif os.uname().sysname == "Darwin":  # pragma: no cover
                import subprocess
                subprocess.Popen(["open", path])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:
            QMessageBox.warning(self, "Folder output", f"Tidak bisa membuka folder:\n{exc}")

    # ---- render flow ----
    def _start_render(self) -> None:
        if not self.project.source_video:
            QMessageBox.warning(self, "Render", "Pilih video sumber dulu di tab Background.")
            return
        if not self.project.render.output_dir:
            QMessageBox.warning(self, "Render", "Pilih folder output dulu.")
            return

        self.render_btn.setEnabled(False)
        self.bar.setValue(0)
        self.status_label.setText("Memulai render ...")
        self.statusMessage.emit("Render dimulai ...")

        self._thread = QThread(self)
        self._worker = _RenderWorker(self.project)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

    def _on_progress(self, p: float, msg: str) -> None:
        self.bar.setValue(int(p * 100))
        self.status_label.setText(msg)
        self.statusMessage.emit(msg)

    def _on_finished(self, ok: bool, msg: str, outputs: list) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        self.render_btn.setEnabled(True)
        self.status_label.setText(msg)
        if ok:
            self.bar.setValue(100)
            if outputs:
                files = "\n".join(outputs)
                QMessageBox.information(self, "Render selesai", f"{msg}\n\n{files}")
            else:
                QMessageBox.information(self, "Render selesai", msg)
        else:
            QMessageBox.critical(self, "Render gagal", msg)
            self.statusMessage.emit(f"Render gagal: {msg}")
