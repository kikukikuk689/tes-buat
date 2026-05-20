"""Settings page — general behaviour, performance, notifications, language."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
)

from ...core.config import get_config
from ...services import get_notifier
from ..widgets import Card
from .base_page import BasePage


class SettingsPage(BasePage):
    title = "Settings"
    subtitle = "App-wide configuration"

    LANGUAGES = ["en", "id", "ja", "ko", "es", "fr", "de", "pt"]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        cfg = get_config().config
        general_card = Card("General", glow=True)
        general_form = QFormLayout()

        self.auto_launch = QCheckBox("Launch with OS")
        self.auto_launch.setChecked(cfg.general.auto_launch)
        self.min_tray = QCheckBox("Minimize to tray")
        self.min_tray.setChecked(cfg.general.minimize_to_tray)
        self.close_tray = QCheckBox("Close to tray (keeps streams alive)")
        self.close_tray.setChecked(cfg.general.close_to_tray)
        self.notifications = QCheckBox("Enable desktop notifications")
        self.notifications.setChecked(cfg.general.enable_notifications)
        self.sound = QCheckBox("Sound alerts")
        self.sound.setChecked(cfg.general.sound_alerts)
        self.updates = QCheckBox("Check for updates")
        self.updates.setChecked(cfg.general.check_updates)
        self.language = QComboBox()
        self.language.addItems(self.LANGUAGES)
        self.language.setCurrentText(cfg.general.language)
        general_form.addRow(self.auto_launch)
        general_form.addRow(self.min_tray)
        general_form.addRow(self.close_tray)
        general_form.addRow(self.notifications)
        general_form.addRow(self.sound)
        general_form.addRow(self.updates)
        general_form.addRow("Language", self.language)
        general_card.content_layout.addLayout(general_form)
        self.content_layout.addWidget(general_card)

        perf_card = Card("Performance")
        perf_form = QFormLayout()
        self.max_streams = QSpinBox()
        self.max_streams.setRange(1, 64)
        self.max_streams.setValue(cfg.performance.max_parallel_streams)
        self.monitor_interval = QSpinBox()
        self.monitor_interval.setRange(250, 10_000)
        self.monitor_interval.setValue(cfg.performance.monitor_interval_ms)
        self.monitor_interval.setSuffix(" ms")
        self.watchdog_interval = QSpinBox()
        self.watchdog_interval.setRange(500, 60_000)
        self.watchdog_interval.setValue(cfg.performance.watchdog_interval_ms)
        self.watchdog_interval.setSuffix(" ms")
        self.network_url = QLineEdit(cfg.performance.network_check_url)
        self.smart_cache = QCheckBox("Smart caching")
        self.smart_cache.setChecked(cfg.performance.enable_smart_cache)
        perf_form.addRow("Max parallel streams", self.max_streams)
        perf_form.addRow("Monitor interval", self.monitor_interval)
        perf_form.addRow("Watchdog interval", self.watchdog_interval)
        perf_form.addRow("Network probe URL", self.network_url)
        perf_form.addRow(self.smart_cache)
        perf_card.content_layout.addLayout(perf_form)
        self.content_layout.addWidget(perf_card)

        backup_card = Card("Backup")
        backup_form = QFormLayout()
        self.auto_backup = QCheckBox("Auto backup")
        self.auto_backup.setChecked(cfg.backup.auto_backup)
        self.backup_interval = QSpinBox()
        self.backup_interval.setRange(1, 168)
        self.backup_interval.setValue(cfg.backup.interval_hours)
        self.backup_interval.setSuffix(" h")
        self.backup_keep = QSpinBox()
        self.backup_keep.setRange(1, 365)
        self.backup_keep.setValue(cfg.backup.keep_last)
        backup_form.addRow(self.auto_backup)
        backup_form.addRow("Interval", self.backup_interval)
        backup_form.addRow("Keep last", self.backup_keep)
        backup_card.content_layout.addLayout(backup_form)
        self.content_layout.addWidget(backup_card)

        save_row = QHBoxLayout()
        self.save_btn = QPushButton("Save settings")
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(self._save)
        save_row.addWidget(self.save_btn)
        save_row.addStretch()
        self.content_layout.addLayout(save_row)

    def _save(self) -> None:
        get_config().update(
            general={
                "auto_launch": self.auto_launch.isChecked(),
                "minimize_to_tray": self.min_tray.isChecked(),
                "close_to_tray": self.close_tray.isChecked(),
                "enable_notifications": self.notifications.isChecked(),
                "sound_alerts": self.sound.isChecked(),
                "check_updates": self.updates.isChecked(),
                "language": self.language.currentText(),
            },
            performance={
                "max_parallel_streams": int(self.max_streams.value()),
                "monitor_interval_ms": int(self.monitor_interval.value()),
                "watchdog_interval_ms": int(self.watchdog_interval.value()),
                "network_check_url": self.network_url.text().strip(),
                "enable_smart_cache": self.smart_cache.isChecked(),
            },
            backup={
                "auto_backup": self.auto_backup.isChecked(),
                "interval_hours": int(self.backup_interval.value()),
                "keep_last": int(self.backup_keep.value()),
            },
        )
        get_notifier().notify("Settings", "Configuration saved", "success")
