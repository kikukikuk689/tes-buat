"""FFmpeg Manager page — detect, install, repair FFmpeg."""
from __future__ import annotations

import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
)

from ...services import get_ffmpeg_manager, get_notifier
from ..widgets import Card, MetricCard
from .base_page import BasePage


class FFmpegPage(BasePage):
    title = "FFmpeg Manager"
    subtitle = "Detect, install, update and verify FFmpeg"

    progressUpdate = Signal(float, str)
    installFinished = Signal(bool, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # status row of metric cards
        status_row = QHBoxLayout()
        self.status_card = MetricCard("Status", "Unknown", "FFmpeg detection", glow=True)
        self.version_card = MetricCard("Version", "—", "ffmpeg -version line")
        self.binary_card = MetricCard("Binary path", "—", "")
        for card in (self.status_card, self.version_card, self.binary_card):
            status_row.addWidget(card)
        self.content_layout.addLayout(status_row)

        # actions
        action_row = QHBoxLayout()
        self.refresh_btn = QPushButton("↻ Refresh")
        self.install_btn = QPushButton("⬇ Install FFmpeg")
        self.install_btn.setObjectName("primary")
        self.repair_btn = QPushButton("🔧 Repair / Update")
        self.repair_btn.setObjectName("ghost")
        for b in (self.refresh_btn, self.install_btn, self.repair_btn):
            action_row.addWidget(b)
        action_row.addStretch()
        self.content_layout.addLayout(action_row)

        # progress
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("color: #8A8AAE;")
        self.content_layout.addWidget(self.progress)
        self.content_layout.addWidget(self.progress_label)

        # encoders list
        body = QHBoxLayout()
        enc_card = Card("Available encoders", subtitle="hardware + software")
        self.encoder_list = QListWidget()
        enc_card.content_layout.addWidget(self.encoder_list)
        body.addWidget(enc_card, 2)

        fmt_card = Card("Supported formats")
        self.format_view = QTextEdit()
        self.format_view.setReadOnly(True)
        self.format_view.setStyleSheet("background: rgba(8,8,20,0.55);")
        fmt_card.content_layout.addWidget(self.format_view)
        body.addWidget(fmt_card, 1)
        self.content_layout.addLayout(body)

        self.refresh_btn.clicked.connect(self._refresh)
        self.install_btn.clicked.connect(self._install)
        self.repair_btn.clicked.connect(self._repair)
        self.progressUpdate.connect(self._on_progress, Qt.QueuedConnection)
        self.installFinished.connect(self._on_install_finished, Qt.QueuedConnection)

        self._refresh()

    def _refresh(self) -> None:
        info = get_ffmpeg_manager().refresh()
        self.status_card.set_value(info.state.value.upper(), "")
        self.version_card.set_value(info.version or "—", "")
        self.binary_card.set_value(info.binary or "—", "")
        self.encoder_list.clear()
        for enc in info.encoders:
            item = QListWidgetItem(enc)
            if any(k in enc for k in ("nvenc", "qsv", "amf", "videotoolbox", "vaapi")):
                item.setForeground(Qt.GlobalColor.green)
            self.encoder_list.addItem(item)
        self.format_view.setPlainText("\n".join(info.formats))

    def _install(self) -> None:
        self.progress.setVisible(True)
        self.progress_label.setText("Starting FFmpeg download…")
        self.install_btn.setEnabled(False)
        self.repair_btn.setEnabled(False)

        def worker():
            try:
                get_ffmpeg_manager().install(
                    progress=lambda pct, msg: self.progressUpdate.emit(pct, msg)
                )
                self.installFinished.emit(True, "FFmpeg installed successfully.")
            except Exception as exc:  # noqa: BLE001
                self.installFinished.emit(False, str(exc))

        threading.Thread(target=worker, name="ffmpeg-install", daemon=True).start()

    def _repair(self) -> None:
        if (
            QMessageBox.question(
                self,
                "Repair FFmpeg",
                "Delete the currently bundled FFmpeg and download a fresh copy?",
            )
            != QMessageBox.Yes
        ):
            return
        self._install_via_repair()

    def _install_via_repair(self) -> None:
        self.progress.setVisible(True)
        self.progress_label.setText("Repairing FFmpeg…")
        self.install_btn.setEnabled(False)
        self.repair_btn.setEnabled(False)

        def worker():
            try:
                get_ffmpeg_manager().repair(
                    progress=lambda pct, msg: self.progressUpdate.emit(pct, msg)
                )
                self.installFinished.emit(True, "FFmpeg repaired successfully.")
            except Exception as exc:  # noqa: BLE001
                self.installFinished.emit(False, str(exc))

        threading.Thread(target=worker, name="ffmpeg-repair", daemon=True).start()

    def _on_progress(self, pct: float, msg: str) -> None:
        self.progress.setValue(int(pct))
        self.progress_label.setText(msg)

    def _on_install_finished(self, ok: bool, message: str) -> None:
        self.install_btn.setEnabled(True)
        self.repair_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.progress_label.setText(message)
        notifier = get_notifier()
        if ok:
            notifier.notify("FFmpeg", message, "success")
        else:
            notifier.notify("FFmpeg", message, "error")
        self._refresh()
