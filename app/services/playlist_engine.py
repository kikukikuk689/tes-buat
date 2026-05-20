"""Playlist materialisation + helpers.

Provides utilities to:

* convert a stored :class:`~app.db.models.Playlist` into the list of
  media file paths a :class:`StreamRuntime` should feed FFmpeg
* apply shuffling / smart randomisation
* probe newly added files with ``ffprobe`` to back-fill durations
"""
from __future__ import annotations

import random
import threading
from pathlib import Path

from ..core.events import Topics, event_bus
from ..core.logger import get_logger
from ..db.base import get_db
from ..db.repository import ChannelRepository, PlaylistRepository
from ..utils.ffprobe import probe_media


class PlaylistEngine:
    """Materialises playlists and keeps duration/metadata up to date."""

    def __init__(self) -> None:
        self._log = get_logger("playlist")
        self._lock = threading.RLock()
        self._channels = ChannelRepository(get_db())
        self._playlists = PlaylistRepository(get_db())

    def materialise(self, playlist_id: int, *, shuffle: bool | None = None) -> list[str]:
        pl = self._playlists.get(playlist_id)
        if pl is None:
            return []
        items = [it for it in pl.items if it.enabled and Path(it.path).exists()]
        items.sort(key=lambda it: it.position)
        files = [it.path for it in items]
        if shuffle if shuffle is not None else pl.shuffle:
            random.shuffle(files)
        return files

    def materialise_for_channel(self, channel_id: int) -> list[str]:
        channel = self._channels.get(channel_id)
        if channel is None or channel.playlist_id is None:
            return []
        return self.materialise(channel.playlist_id, shuffle=channel.shuffle)

    def add_media(self, playlist_id: int, files: list[str]) -> int:
        """Add files to a playlist; probe each for duration; return count added."""
        items = []
        for f in files:
            p = Path(f)
            if not p.exists():
                self._log.warning("Skipping missing file: %s", f)
                continue
            info = probe_media(p)
            items.append(
                {
                    "path": str(p),
                    "title": p.stem,
                    "duration_sec": info.duration_sec,
                }
            )
        if items:
            self._playlists.add_items(playlist_id, items)
            event_bus.publish(Topics.PLAYLIST_CHANGED, {"playlist_id": playlist_id})
        return len(items)

    def total_duration(self, playlist_id: int) -> float:
        pl = self._playlists.get(playlist_id)
        if pl is None:
            return 0.0
        return sum(it.duration_sec for it in pl.items if it.enabled)

    def shuffle(self, playlist_id: int) -> None:
        pl = self._playlists.get(playlist_id)
        if pl is None:
            return
        items = [
            {
                "path": it.path,
                "title": it.title,
                "duration_sec": it.duration_sec,
                "enabled": it.enabled,
            }
            for it in pl.items
        ]
        random.shuffle(items)
        self._playlists.replace_items(playlist_id, items)
        event_bus.publish(Topics.PLAYLIST_CHANGED, {"playlist_id": playlist_id})


_GLOBAL: PlaylistEngine | None = None


def get_playlist_engine() -> PlaylistEngine:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = PlaylistEngine()
    return _GLOBAL
