"""Backup Manager — create / restore / export configuration."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from ...core.paths import paths
from ...services import get_backup, get_notifier
from ...utils.time_utils import fmt_bytes
from ..widgets import Card
from .base_page import BasePage


class BackupPage(BasePage):
    title = "Backup Manager"
    subtitle = "Auto + manual backups; import / export config"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.service = get_backup()

        toolbar = QHBoxLayout()
        self.create_btn = QPushButton("＋ Create backup")
        self.create_btn.setObjectName("primary")
        self.restore_btn = QPushButton("⤺ Restore selected")
        self.export_btn = QPushButton("📤 Export config…")
        self.import_btn = QPushButton("📥 Import config…")
        self.delete_btn = QPushButton("🗑 Delete selected")
        self.delete_btn.setObjectName("danger")
        for b in (self.create_btn, self.restore_btn, self.export_btn, self.import_btn, self.delete_btn):
            toolbar.addWidget(b)
        toolbar.addStretch()
        self.content_layout.addLayout(toolbar)

        card = Card("Backups")
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "Size", "Created"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        card.content_layout.addWidget(self.table)
        self.content_layout.addWidget(card)

        self.create_btn.clicked.connect(self._create)
        self.restore_btn.clicked.connect(self._restore)
        self.export_btn.clicked.connect(self._export)
        self.import_btn.clicked.connect(self._import)
        self.delete_btn.clicked.connect(self._delete)
        self._reload()

    def on_show(self) -> None:
        super().on_show()
        self._reload()

    def _reload(self) -> None:
        records = self.service.list_backups()
        self.table.setRowCount(len(records))
        for row, rec in enumerate(records):
            self.table.setItem(row, 0, QTableWidgetItem(rec.name))
            self.table.setItem(row, 1, QTableWidgetItem(fmt_bytes(rec.size_bytes)))
            self.table.setItem(row, 2, QTableWidgetItem(rec.created_at.isoformat(sep=" ", timespec="seconds")))

    def _selected_name(self) -> str | None:
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return None
        return self.table.item(sel[0].row(), 0).text()

    def _create(self) -> None:
        rec = self.service.create()
        get_notifier().notify("Backup", f"Created {rec.name}", "success")
        self._reload()

    def _restore(self) -> None:
        name = self._selected_name()
        if not name:
            return
        if QMessageBox.question(self, "Restore backup", f"Restore {name}? This overwrites current data.") != QMessageBox.Yes:
            return
        try:
            self.service.restore(paths.backups_dir / name)
            QMessageBox.information(self, "Restore", "Restore complete. Please restart the app.")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Restore failed", str(exc))

    def _delete(self) -> None:
        name = self._selected_name()
        if not name:
            return
        if QMessageBox.question(self, "Delete backup", f"Delete {name}?") != QMessageBox.Yes:
            return
        try:
            (paths.backups_dir / name).unlink()
        except OSError as exc:
            QMessageBox.critical(self, "Delete failed", str(exc))
            return
        self._reload()

    def _export(self) -> None:
        target, _ = QFileDialog.getSaveFileName(self, "Export config", "studio-config.yaml", "YAML (*.yaml *.yml)")
        if not target:
            return
        try:
            self.service.export_config(Path(target))
            get_notifier().notify("Backup", f"Config exported to {target}", "success")
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _import(self) -> None:
        source, _ = QFileDialog.getOpenFileName(self, "Import config", "", "YAML (*.yaml *.yml)")
        if not source:
            return
        try:
            self.service.import_config(Path(source))
            QMessageBox.information(self, "Import", "Config imported. Restart the app to load it.")
        except OSError as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
