"""Multi Channel Manager - CRUD for channels."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
)

from ...core.events import Topics, event_bus
from ...db.base import get_db
from ...db.repository import ChannelRepository, PlaylistRepository
from ...security.crypto import get_crypto
from .base_page import BasePage

PLATFORMS = ["youtube", "twitch", "facebook", "tiktok", "custom"]
PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"]
HW_OPTIONS = ["auto", "none", "nvenc", "qsv", "amf", "videotoolbox", "vaapi"]
RESOLUTIONS = ["1280x720", "1920x1080", "2560x1440", "3840x2160"]


class ChannelDialog(QDialog):
    """Create / edit a single channel."""

    def __init__(self, *, title: str = "Channel", channel=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 640)
        playlists = PlaylistRepository(get_db()).list()
        form = QFormLayout(self)

        self.name = QLineEdit(channel.name if channel else "")
        self.platform = QComboBox()
        self.platform.addItems(PLATFORMS)
        if channel:
            idx = self.platform.findText(channel.platform)
            if idx >= 0:
                self.platform.setCurrentIndex(idx)
        self.rtmp_url = QLineEdit(channel.rtmp_url if channel else "rtmp://a.rtmp.youtube.com/live2")
        self.stream_key = QLineEdit("")
        self.stream_key.setEchoMode(QLineEdit.Password)
        self.stream_key.setPlaceholderText("(stored encrypted — leave blank to keep existing)")

        self.playlist = QComboBox()
        self.playlist.addItem("— none —", None)
        for pl in playlists:
            self.playlist.addItem(pl.name, pl.id)
        if channel and channel.playlist_id is not None:
            idx = self.playlist.findData(channel.playlist_id)
            if idx >= 0:
                self.playlist.setCurrentIndex(idx)

        self.resolution = QComboBox()
        self.resolution.addItems(RESOLUTIONS)
        if channel:
            self.resolution.setCurrentText(channel.resolution)
        self.fps = QSpinBox()
        self.fps.setRange(15, 60)
        self.fps.setValue(channel.fps if channel else 30)
        self.v_bitrate = QSpinBox()
        self.v_bitrate.setRange(500, 50_000)
        self.v_bitrate.setSuffix(" kbps")
        self.v_bitrate.setValue(channel.video_bitrate_kbps if channel else 4500)
        self.a_bitrate = QSpinBox()
        self.a_bitrate.setRange(64, 512)
        self.a_bitrate.setSuffix(" kbps")
        self.a_bitrate.setValue(channel.audio_bitrate_kbps if channel else 160)
        self.preset = QComboBox()
        self.preset.addItems(PRESETS)
        if channel:
            self.preset.setCurrentText(channel.preset)
        self.hw = QComboBox()
        self.hw.addItems(HW_OPTIONS)
        if channel:
            self.hw.setCurrentText(channel.hw_accel)

        self.auto_restart = QCheckBox("Auto restart on failure")
        self.auto_restart.setChecked(channel.auto_restart if channel else True)
        self.auto_reconnect = QCheckBox("Auto reconnect")
        self.auto_reconnect.setChecked(channel.auto_reconnect if channel else True)
        self.loop = QCheckBox("Loop playlist (24/7)")
        self.loop.setChecked(channel.loop_playlist if channel else True)
        self.shuffle = QCheckBox("Shuffle playlist")
        self.shuffle.setChecked(channel.shuffle if channel else False)
        self.enabled = QCheckBox("Channel enabled")
        self.enabled.setChecked(channel.enabled if channel else True)

        self.description = QTextEdit(channel.description if channel else "")
        self.description.setFixedHeight(80)
        self.tags = QLineEdit(channel.tags if channel else "")
        self.tags.setPlaceholderText("comma separated tags")
        self.category = QLineEdit(channel.category if channel else "")

        form.addRow("Name", self.name)
        form.addRow("Platform", self.platform)
        form.addRow("RTMP URL", self.rtmp_url)
        form.addRow("Stream key", self.stream_key)
        form.addRow("Playlist", self.playlist)
        form.addRow("Resolution", self.resolution)
        form.addRow("FPS", self.fps)
        form.addRow("Video bitrate", self.v_bitrate)
        form.addRow("Audio bitrate", self.a_bitrate)
        form.addRow("Preset", self.preset)
        form.addRow("Hardware accel", self.hw)
        form.addRow("Tags", self.tags)
        form.addRow("Category", self.category)
        form.addRow("Description", self.description)
        for box in (self.auto_restart, self.auto_reconnect, self.loop, self.shuffle, self.enabled):
            form.addRow(box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self, *, existing_key_cipher: str = "") -> dict:
        crypto = get_crypto()
        key_plain = self.stream_key.text().strip()
        stream_key_encrypted = (
            crypto.encrypt(key_plain) if key_plain else existing_key_cipher
        )
        playlist_data = self.playlist.currentData()
        return {
            "name": self.name.text().strip(),
            "platform": self.platform.currentText(),
            "rtmp_url": self.rtmp_url.text().strip(),
            "stream_key_encrypted": stream_key_encrypted,
            "playlist_id": int(playlist_data) if playlist_data else None,
            "resolution": self.resolution.currentText(),
            "fps": int(self.fps.value()),
            "video_bitrate_kbps": int(self.v_bitrate.value()),
            "audio_bitrate_kbps": int(self.a_bitrate.value()),
            "preset": self.preset.currentText(),
            "hw_accel": self.hw.currentText(),
            "auto_restart": self.auto_restart.isChecked(),
            "auto_reconnect": self.auto_reconnect.isChecked(),
            "loop_playlist": self.loop.isChecked(),
            "shuffle": self.shuffle.isChecked(),
            "enabled": self.enabled.isChecked(),
            "tags": self.tags.text().strip(),
            "category": self.category.text().strip(),
            "description": self.description.toPlainText().strip(),
        }


class MultiChannelPage(BasePage):
    title = "Multi Channel Manager"
    subtitle = "Create, edit and delete channels"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        toolbar = QHBoxLayout()
        self.add_btn = QPushButton("＋  Add channel")
        self.add_btn.setObjectName("primary")
        self.edit_btn = QPushButton("✎  Edit selected")
        self.delete_btn = QPushButton("🗑  Delete selected")
        self.delete_btn.setObjectName("danger")
        self.refresh_btn = QPushButton("↻  Refresh")
        for b in (self.add_btn, self.edit_btn, self.delete_btn, self.refresh_btn):
            toolbar.addWidget(b)
        toolbar.addStretch()
        self.content_layout.addLayout(toolbar)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["#", "Name", "Platform", "Resolution", "Bitrate", "Enabled", "State", "RTMP"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.content_layout.addWidget(self.table)

        self.add_btn.clicked.connect(self._add_channel)
        self.edit_btn.clicked.connect(self._edit_channel)
        self.delete_btn.clicked.connect(self._delete_channel)
        self.refresh_btn.clicked.connect(self._reload)
        self.table.itemDoubleClicked.connect(lambda _: self._edit_channel())

        event_bus.subscribe(Topics.CHANNEL_CHANGED, lambda _: self._reload())
        self._reload()

    def on_show(self) -> None:
        super().on_show()
        self._reload()

    def _reload(self) -> None:
        repo = ChannelRepository(get_db())
        channels = repo.list()
        self.table.setRowCount(len(channels))
        for row, ch in enumerate(channels):
            self.table.setItem(row, 0, QTableWidgetItem(str(ch.id)))
            self.table.setItem(row, 1, QTableWidgetItem(ch.name))
            self.table.setItem(row, 2, QTableWidgetItem(ch.platform))
            self.table.setItem(row, 3, QTableWidgetItem(ch.resolution))
            self.table.setItem(row, 4, QTableWidgetItem(f"{ch.video_bitrate_kbps} kbps"))
            self.table.setItem(row, 5, QTableWidgetItem("Yes" if ch.enabled else "No"))
            self.table.setItem(row, 6, QTableWidgetItem(ch.last_state.value))
            self.table.setItem(row, 7, QTableWidgetItem(ch.rtmp_url))

    def _selected_id(self) -> int | None:
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return None
        return int(self.table.item(sel[0].row(), 0).text())

    def _add_channel(self) -> None:
        dlg = ChannelDialog(title="New channel", parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            ChannelRepository(get_db()).create(**dlg.values())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        event_bus.publish(Topics.CHANNEL_CHANGED, {"action": "created"})

    def _edit_channel(self) -> None:
        cid = self._selected_id()
        if cid is None:
            return
        repo = ChannelRepository(get_db())
        ch = repo.get(cid)
        if ch is None:
            return
        dlg = ChannelDialog(title=f"Edit channel — {ch.name}", channel=ch, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            repo.update(cid, **dlg.values(existing_key_cipher=ch.stream_key_encrypted))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        event_bus.publish(Topics.CHANNEL_CHANGED, {"action": "updated", "channel_id": cid})

    def _delete_channel(self) -> None:
        cid = self._selected_id()
        if cid is None:
            return
        if QMessageBox.question(self, "Delete channel", "Delete this channel and all its sessions?") != QMessageBox.Yes:
            return
        ChannelRepository(get_db()).delete(cid)
        event_bus.publish(Topics.CHANNEL_CHANGED, {"action": "deleted", "channel_id": cid})
