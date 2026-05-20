"""Logs Viewer page — searchable, tabbed log inspector."""
from __future__ import annotations

from collections import deque
from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...core.events import Topics, event_bus
from ...db.base import get_db
from ...db.repository import LogRepository
from .base_page import BasePage


class LogsPage(BasePage):
    title = "Logs Viewer"
    subtitle = "Realtime FFmpeg + application logs"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.content_layout.addWidget(self.tabs)

        # Realtime FFmpeg tab
        self.realtime = QTextEdit()
        self.realtime.setReadOnly(True)
        self.realtime.setStyleSheet(
            "background: #0A0815; color: #D4FFE0; font-family: 'JetBrains Mono', 'Cascadia Mono', monospace;"
        )
        self.realtime_buffer: deque[str] = deque(maxlen=5000)
        self.tabs.addTab(self.realtime, "Realtime FFmpeg")

        # Persisted log query tab
        query_widget = QWidget()
        qv = QVBoxLayout(query_widget)
        toolbar = QHBoxLayout()
        self.level = QComboBox()
        self.level.addItems(["", "DEBUG", "INFO", "WARN", "ERROR"])
        self.source = QComboBox()
        self.source.addItems(["", "app", "ffmpeg", "youtube", "stream", "scheduler"])
        self.search = QLineEdit()
        self.search.setPlaceholderText("search…")
        self.refresh_btn = QPushButton("Search")
        self.refresh_btn.setObjectName("primary")
        self.export_btn = QPushButton("Export…")
        self.refresh_btn.clicked.connect(self._reload_table)
        self.export_btn.clicked.connect(self._export_logs)
        for w in (
            QLabel("Level"),
            self.level,
            QLabel("Source"),
            self.source,
            QLabel("Search"),
            self.search,
            self.refresh_btn,
            self.export_btn,
        ):
            toolbar.addWidget(w)
        toolbar.addStretch()
        qv.addLayout(toolbar)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Time", "Level", "Source", "Channel", "Message"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        qv.addWidget(self.table)
        self.tabs.addTab(query_widget, "Persisted logs")

        # Live event log
        self.events = QTextEdit()
        self.events.setReadOnly(True)
        self.events.setStyleSheet(
            "background: #0A0815; color: #CDB6FF; font-family: 'JetBrains Mono', monospace;"
        )
        self.events_buffer: deque[str] = deque(maxlen=2000)
        self.tabs.addTab(self.events, "App events")

        event_bus.subscribe(Topics.STREAM_LOG, lambda p: QTimer.singleShot(0, lambda: self._append_realtime(p)))
        event_bus.subscribe(
            Topics.STREAM_STATE, lambda p: QTimer.singleShot(0, lambda: self._append_event("STATE", p))
        )
        event_bus.subscribe(
            Topics.WATCHDOG_EVENT, lambda p: QTimer.singleShot(0, lambda: self._append_event("WATCH", p))
        )
        event_bus.subscribe(
            Topics.NETWORK_STATE,
            lambda p: QTimer.singleShot(0, lambda: self._append_event("NET", p) if not p.get("silent") else None),
        )
        event_bus.subscribe(
            Topics.SCHEDULER_TICK, lambda p: QTimer.singleShot(0, lambda: self._append_event("SCHED", p))
        )

        self._reload_table()

    def on_show(self) -> None:
        super().on_show()
        self._reload_table()

    # ------------------------------------------------------------------
    def _reload_table(self) -> None:
        rows = LogRepository(get_db()).query(
            level=self.level.currentText() or None,
            source=self.source.currentText() or None,
            search=self.search.text().strip() or None,
            limit=400,
        )
        self.table.setRowCount(len(rows))
        for row, r in enumerate(rows):
            self.table.setItem(row, 0, QTableWidgetItem(r.ts.isoformat()))
            self.table.setItem(row, 1, QTableWidgetItem(r.level))
            self.table.setItem(row, 2, QTableWidgetItem(r.source))
            self.table.setItem(row, 3, QTableWidgetItem(str(r.channel_id or "")))
            self.table.setItem(row, 4, QTableWidgetItem(r.message))

    def _append_realtime(self, payload: dict) -> None:
        ts = datetime.utcnow().strftime("%H:%M:%S")
        cid = payload.get("channel_id")
        line = f"[{ts}] ch={cid}  {payload.get('line','')}"
        self.realtime_buffer.append(line)
        self.realtime.setPlainText("\n".join(list(self.realtime_buffer)[-1000:]))
        self.realtime.moveCursor(self.realtime.textCursor().End)

    def _append_event(self, kind: str, payload: dict) -> None:
        ts = datetime.utcnow().strftime("%H:%M:%S")
        line = f"[{ts}] [{kind}] {payload}"
        self.events_buffer.append(line)
        self.events.setPlainText("\n".join(list(self.events_buffer)[-1000:]))

    def _export_logs(self) -> None:
        rows = LogRepository(get_db()).query(limit=10000)
        target, _ = QFileDialog.getSaveFileName(self, "Export logs", "studio-logs.txt", "Text (*.txt)")
        if not target:
            return
        try:
            with open(target, "w", encoding="utf-8") as fh:
                for r in rows:
                    fh.write(f"{r.ts.isoformat()}  {r.level:<5}  {r.source:<10}  ch={r.channel_id}  {r.message}\n")
            QMessageBox.information(self, "Exported", f"Wrote {len(rows)} log lines to {target}")
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
