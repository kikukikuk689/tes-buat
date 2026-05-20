"""Scheduler page — define start/stop times for channels."""
from __future__ import annotations

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from ...db.base import get_db
from ...db.repository import ChannelRepository, ScheduleRepository
from ...services import get_scheduler
from .base_page import BasePage


class _ScheduleDialog(QDialog):
    def __init__(self, channels: list, schedule=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Schedule slot")
        self.resize(440, 320)
        form = QFormLayout(self)

        self.channel = QComboBox()
        for c in channels:
            self.channel.addItem(c.name, c.id)
        if schedule:
            idx = self.channel.findData(schedule.channel_id)
            if idx >= 0:
                self.channel.setCurrentIndex(idx)
        self.label = QLineEdit(schedule.label if schedule else "")
        self.start_at = QDateTimeEdit(QDateTime.fromString(schedule.start_at.isoformat(), Qt.ISODate)
                                       if schedule and schedule.start_at else QDateTime.currentDateTime())
        self.start_at.setCalendarPopup(True)
        self.stop_at = QDateTimeEdit(QDateTime.fromString(schedule.stop_at.isoformat(), Qt.ISODate)
                                      if schedule and schedule.stop_at else QDateTime.currentDateTime().addSecs(3600))
        self.stop_at.setCalendarPopup(True)
        self.cron_start = QLineEdit(schedule.cron_start if schedule else "")
        self.cron_start.setPlaceholderText("optional crontab e.g.  0 8 * * *")
        self.cron_stop = QLineEdit(schedule.cron_stop if schedule else "")
        self.cron_stop.setPlaceholderText("optional crontab e.g.  0 23 * * *")

        form.addRow("Channel", self.channel)
        form.addRow("Label", self.label)
        form.addRow("Start", self.start_at)
        form.addRow("Stop", self.stop_at)
        form.addRow("Cron start", self.cron_start)
        form.addRow("Cron stop", self.cron_stop)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def values(self) -> dict:
        cron_s = self.cron_start.text().strip()
        cron_e = self.cron_stop.text().strip()
        return {
            "channel_id": int(self.channel.currentData()),
            "label": self.label.text().strip(),
            "start_at": self.start_at.dateTime().toPython() if not cron_s else None,
            "stop_at": self.stop_at.dateTime().toPython() if not cron_e else None,
            "cron_start": cron_s or None,
            "cron_stop": cron_e or None,
            "enabled": True,
        }


class SchedulerPage(BasePage):
    title = "Scheduler"
    subtitle = "Automated start / stop schedules per channel"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        toolbar = QHBoxLayout()
        self.add_btn = QPushButton("＋  New schedule")
        self.add_btn.setObjectName("primary")
        self.edit_btn = QPushButton("✎  Edit")
        self.del_btn = QPushButton("🗑  Delete")
        self.del_btn.setObjectName("danger")
        self.reload_btn = QPushButton("↻ Reload")
        toolbar.addWidget(self.add_btn)
        toolbar.addWidget(self.edit_btn)
        toolbar.addWidget(self.del_btn)
        toolbar.addWidget(self.reload_btn)
        toolbar.addStretch()
        self.content_layout.addLayout(toolbar)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["#", "Channel", "Label", "Start", "Stop", "Cron", "Enabled"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.content_layout.addWidget(self.table)

        self.add_btn.clicked.connect(self._add)
        self.edit_btn.clicked.connect(self._edit)
        self.del_btn.clicked.connect(self._delete)
        self.reload_btn.clicked.connect(self._reload)
        self._reload()

    def on_show(self) -> None:
        super().on_show()
        self._reload()

    def _selected_id(self) -> int | None:
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return None
        return int(self.table.item(sel[0].row(), 0).text())

    def _reload(self) -> None:
        schedules = ScheduleRepository(get_db()).list()
        channels = {c.id: c.name for c in ChannelRepository(get_db()).list()}
        self.table.setRowCount(len(schedules))
        for row, s in enumerate(schedules):
            self.table.setItem(row, 0, QTableWidgetItem(str(s.id)))
            self.table.setItem(row, 1, QTableWidgetItem(channels.get(s.channel_id, f"#{s.channel_id}")))
            self.table.setItem(row, 2, QTableWidgetItem(s.label))
            self.table.setItem(row, 3, QTableWidgetItem(s.start_at.isoformat() if s.start_at else ""))
            self.table.setItem(row, 4, QTableWidgetItem(s.stop_at.isoformat() if s.stop_at else ""))
            cron = " | ".join(filter(None, [s.cron_start, s.cron_stop]))
            self.table.setItem(row, 5, QTableWidgetItem(cron))
            self.table.setItem(row, 6, QTableWidgetItem("Yes" if s.enabled else "No"))

    def _add(self) -> None:
        channels = ChannelRepository(get_db()).list()
        if not channels:
            QMessageBox.warning(self, "No channels", "Create a channel first.")
            return
        dlg = _ScheduleDialog(channels, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            ScheduleRepository(get_db()).add(**dlg.values())
            get_scheduler().reload()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Failed", str(exc))
            return
        self._reload()

    def _edit(self) -> None:
        sid = self._selected_id()
        if sid is None:
            return
        repo = ScheduleRepository(get_db())
        sched = next((s for s in repo.list() if s.id == sid), None)
        if sched is None:
            return
        channels = ChannelRepository(get_db()).list()
        dlg = _ScheduleDialog(channels, schedule=sched, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            repo.update(sid, **dlg.values())
            get_scheduler().reload()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Failed", str(exc))
            return
        self._reload()

    def _delete(self) -> None:
        sid = self._selected_id()
        if sid is None:
            return
        if QMessageBox.question(self, "Delete", "Delete this schedule?") != QMessageBox.Yes:
            return
        ScheduleRepository(get_db()).delete(sid)
        get_scheduler().reload()
        self._reload()
