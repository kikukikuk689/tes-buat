"""Playlist Manager - manage media playlists used by channels."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ...core.events import Topics, event_bus
from ...db.base import get_db
from ...db.repository import PlaylistRepository
from ...services import get_playlist_engine
from ...utils.time_utils import fmt_duration
from .base_page import BasePage

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".m4v"}
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}


class PlaylistManagerPage(BasePage):
    title = "Playlist Manager"
    subtitle = "Drag & drop media, shuffle, schedule, infinite loop"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.repo = PlaylistRepository(get_db())
        self.engine = get_playlist_engine()

        body = QHBoxLayout()

        # Left column: playlists
        left = QVBoxLayout()
        left.addWidget(QLabel("Playlists"))
        self.playlist_list = QListWidget()
        self.playlist_list.itemSelectionChanged.connect(self._on_select_playlist)
        left.addWidget(self.playlist_list)
        left_buttons = QHBoxLayout()
        self.new_btn = QPushButton("＋ New")
        self.new_btn.clicked.connect(self._new_playlist)
        self.rename_btn = QPushButton("✎ Rename")
        self.rename_btn.clicked.connect(self._rename_playlist)
        self.delete_btn = QPushButton("🗑 Delete")
        self.delete_btn.setObjectName("danger")
        self.delete_btn.clicked.connect(self._delete_playlist)
        for b in (self.new_btn, self.rename_btn, self.delete_btn):
            left_buttons.addWidget(b)
        left.addLayout(left_buttons)
        body.addLayout(left, 1)

        # Right column: items
        right = QVBoxLayout()
        meta = QHBoxLayout()
        self.name_label = QLabel("Select a playlist")
        self.name_label.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: 700;")
        self.duration_label = QLabel("")
        self.duration_label.setStyleSheet("color: #8A8AAE;")
        meta.addWidget(self.name_label)
        meta.addStretch()
        meta.addWidget(self.duration_label)
        right.addLayout(meta)

        opts = QHBoxLayout()
        self.shuffle = QCheckBox("Shuffle")
        self.loop = QCheckBox("Loop")
        self.normalize = QCheckBox("Auto loudness normalize")
        self.crossfade = QSpinBox()
        self.crossfade.setRange(0, 5000)
        self.crossfade.setSuffix(" ms crossfade")
        for b in (self.shuffle, self.loop, self.normalize, self.crossfade):
            opts.addWidget(b)
        opts.addStretch()
        self.save_meta_btn = QPushButton("Save")
        self.save_meta_btn.setObjectName("primary")
        self.save_meta_btn.clicked.connect(self._save_meta)
        opts.addWidget(self.save_meta_btn)
        right.addLayout(opts)

        self.items_list = QListWidget()
        self.items_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.items_list.setDragDropMode(QAbstractItemView.InternalMove)
        right.addWidget(self.items_list, 1)

        item_buttons = QHBoxLayout()
        self.add_files_btn = QPushButton("＋ Add media…")
        self.add_files_btn.setObjectName("primary")
        self.add_files_btn.clicked.connect(self._add_files)
        self.add_folder_btn = QPushButton("📁 Add folder…")
        self.add_folder_btn.clicked.connect(self._add_folder)
        self.remove_btn = QPushButton("✕ Remove")
        self.remove_btn.clicked.connect(self._remove_selected)
        self.shuffle_btn = QPushButton("🔀 Shuffle now")
        self.shuffle_btn.clicked.connect(self._shuffle_now)
        self.save_order_btn = QPushButton("💾 Save order")
        self.save_order_btn.clicked.connect(self._save_order)
        for b in (
            self.add_files_btn,
            self.add_folder_btn,
            self.remove_btn,
            self.shuffle_btn,
            self.save_order_btn,
        ):
            item_buttons.addWidget(b)
        item_buttons.addStretch()
        right.addLayout(item_buttons)
        body.addLayout(right, 3)

        self.content_layout.addLayout(body)
        event_bus.subscribe(Topics.PLAYLIST_CHANGED, lambda _: self._reload_playlists())
        self._reload_playlists()

    def on_show(self) -> None:
        super().on_show()
        self._reload_playlists()

    # ------------------------------------------------------------------
    def _reload_playlists(self) -> None:
        current_id = self._current_playlist_id()
        self.playlist_list.clear()
        for pl in self.repo.list():
            item = QListWidgetItem(f"{pl.name}  ({len(pl.items)})")
            item.setData(Qt.UserRole, pl.id)
            self.playlist_list.addItem(item)
            if pl.id == current_id:
                self.playlist_list.setCurrentItem(item)
        if current_id is None and self.playlist_list.count() > 0:
            self.playlist_list.setCurrentRow(0)
        self._on_select_playlist()

    def _current_playlist_id(self) -> int | None:
        item = self.playlist_list.currentItem()
        return int(item.data(Qt.UserRole)) if item else None

    def _on_select_playlist(self) -> None:
        pid = self._current_playlist_id()
        if pid is None:
            self.items_list.clear()
            self.name_label.setText("Select a playlist")
            self.duration_label.setText("")
            return
        pl = self.repo.get(pid)
        if pl is None:
            return
        self.name_label.setText(pl.name)
        total = self.engine.total_duration(pid)
        self.duration_label.setText(f"{len(pl.items)} items · {fmt_duration(total)}")
        self.shuffle.setChecked(pl.shuffle)
        self.loop.setChecked(pl.loop)
        self.normalize.setChecked(pl.normalize_audio)
        self.crossfade.setValue(pl.crossfade_ms)
        self.items_list.clear()
        for it in pl.items:
            lw = QListWidgetItem(f"{it.position+1:03d}.  {Path(it.path).name}   ·   {fmt_duration(it.duration_sec)}")
            lw.setData(Qt.UserRole, it.id)
            lw.setData(Qt.UserRole + 1, it.path)
            self.items_list.addItem(lw)

    def _save_meta(self) -> None:
        pid = self._current_playlist_id()
        if pid is None:
            return
        self.repo.update(
            pid,
            shuffle=self.shuffle.isChecked(),
            loop=self.loop.isChecked(),
            normalize_audio=self.normalize.isChecked(),
            crossfade_ms=int(self.crossfade.value()),
        )
        event_bus.publish(Topics.PLAYLIST_CHANGED, {"playlist_id": pid})

    # ------------------------------------------------------------------
    def _new_playlist(self) -> None:
        name, ok = QInputDialog.getText(self, "New playlist", "Name:")
        if not ok or not name.strip():
            return
        try:
            self.repo.create(name=name.strip())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Failed", str(exc))
            return
        event_bus.publish(Topics.PLAYLIST_CHANGED, {"action": "created"})

    def _rename_playlist(self) -> None:
        pid = self._current_playlist_id()
        if pid is None:
            return
        pl = self.repo.get(pid)
        name, ok = QInputDialog.getText(self, "Rename", "New name:", text=pl.name)
        if not ok or not name.strip():
            return
        self.repo.update(pid, name=name.strip())
        event_bus.publish(Topics.PLAYLIST_CHANGED, {"playlist_id": pid})

    def _delete_playlist(self) -> None:
        pid = self._current_playlist_id()
        if pid is None:
            return
        if QMessageBox.question(self, "Delete playlist", "Delete this playlist?") != QMessageBox.Yes:
            return
        self.repo.delete(pid)
        event_bus.publish(Topics.PLAYLIST_CHANGED, {"action": "deleted"})

    # ------------------------------------------------------------------
    def _add_files(self) -> None:
        pid = self._current_playlist_id()
        if pid is None:
            QMessageBox.information(self, "No playlist", "Select or create a playlist first.")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add media",
            "",
            "Media (*.mp4 *.mkv *.mov *.avi *.webm *.flv *.mp3 *.wav *.flac *.m4a *.aac);;All files (*)",
        )
        if paths:
            self.engine.add_media(pid, paths)

    def _add_folder(self) -> None:
        pid = self._current_playlist_id()
        if pid is None:
            return
        folder = QFileDialog.getExistingDirectory(self, "Add folder")
        if not folder:
            return
        media = []
        for f in Path(folder).rglob("*"):
            if f.is_file() and f.suffix.lower() in (VIDEO_EXTS | AUDIO_EXTS):
                media.append(str(f))
        if media:
            self.engine.add_media(pid, media)
            QMessageBox.information(self, "Added", f"Added {len(media)} files.")
        else:
            QMessageBox.warning(self, "Nothing found", "No supported media files in that folder.")

    def _remove_selected(self) -> None:
        pid = self._current_playlist_id()
        if pid is None:
            return
        ids = [it.data(Qt.UserRole) for it in self.items_list.selectedItems()]
        for item_id in ids:
            self.repo.remove_item(pid, int(item_id))
        event_bus.publish(Topics.PLAYLIST_CHANGED, {"playlist_id": pid})

    def _shuffle_now(self) -> None:
        pid = self._current_playlist_id()
        if pid is None:
            return
        self.engine.shuffle(pid)

    def _save_order(self) -> None:
        pid = self._current_playlist_id()
        if pid is None:
            return
        new_items = []
        for index in range(self.items_list.count()):
            it = self.items_list.item(index)
            new_items.append(
                {
                    "path": it.data(Qt.UserRole + 1),
                    "title": Path(it.data(Qt.UserRole + 1)).stem,
                    "duration_sec": 0.0,
                    "enabled": True,
                }
            )
        # Preserve existing durations from DB
        pl = self.repo.get(pid)
        durations = {it.path: it.duration_sec for it in pl.items} if pl else {}
        for entry in new_items:
            entry["duration_sec"] = durations.get(entry["path"], 0.0)
        self.repo.replace_items(pid, new_items)
        event_bus.publish(Topics.PLAYLIST_CHANGED, {"playlist_id": pid})
