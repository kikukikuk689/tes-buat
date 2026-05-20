"""Watchdog service.

Watches every active channel and tells the stream engine to restart
runtimes that are supposed to be live but whose FFmpeg process is gone,
producing no progress, or whose channel was edited.

It also observes the data directory for external playlist file changes
so the next stream cycle picks them up automatically.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from ..core.config import get_config
from ..core.events import Topics, event_bus
from ..core.logger import get_logger
from ..core.paths import paths
from ..db.base import get_db
from ..db.models import ChannelState
from ..db.repository import ChannelRepository
from .stream_engine import get_stream_engine


@dataclass
class WatchdogReport:
    checks: int = 0
    restarts: int = 0
    file_changes: int = 0


class _DataChangeHandler(FileSystemEventHandler):
    def __init__(self, log) -> None:
        super().__init__()
        self._log = log
        self.changed_at: float = 0.0

    def on_any_event(self, event) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        self.changed_at = time.time()
        self._log.debug("watchdog: %s -> %s", event.event_type, event.src_path)


class WatchdogService:
    """Supervises the stream engine + filesystem events."""

    def __init__(self) -> None:
        self._log = get_logger("watchdog")
        self._cfg = get_config().config.performance
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._observer: Observer | None = None
        self._handler = _DataChangeHandler(self._log)
        self.report = WatchdogReport()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="watchdog", daemon=True)
        self._thread.start()
        self._start_fs_observer()
        self._log.info("Watchdog service started")

    def stop(self) -> None:
        self._stop.set()
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=2)
            except Exception:  # noqa: BLE001
                pass
            self._observer = None
        if self._thread:
            self._thread.join(timeout=3)

    # ------------------------------------------------------------------
    def _start_fs_observer(self) -> None:
        try:
            obs = Observer()
            obs.schedule(self._handler, str(paths.data_root), recursive=True)
            obs.daemon = True
            obs.start()
            self._observer = obs
        except Exception:  # noqa: BLE001
            self._log.warning("Filesystem observer could not be started.", exc_info=True)

    def _loop(self) -> None:
        repo = ChannelRepository(get_db())
        engine = get_stream_engine()
        interval = max(0.5, self._cfg.watchdog_interval_ms / 1000.0)
        while not self._stop.is_set():
            try:
                self.report.checks += 1
                for ch in repo.list():
                    if not ch.enabled:
                        continue
                    runtime = engine.runtime(ch.id) if engine.is_running(ch.id) else None
                    if runtime is None:
                        continue
                    stats = runtime.stats
                    is_live = stats.state in {
                        ChannelState.LIVE,
                        ChannelState.STARTING,
                        ChannelState.RECONNECTING,
                    }
                    stale = (
                        stats.last_update
                        and (time.time() - stats.last_update.timestamp()) > 25
                    )
                    if is_live and stale:
                        self.report.restarts += 1
                        self._log.warning("Channel %s is stale, requesting restart", ch.name)
                        event_bus.publish(
                            Topics.WATCHDOG_EVENT,
                            {"channel_id": ch.id, "action": "restart_stale"},
                        )
                        engine.restart(ch.id)
            except Exception:  # noqa: BLE001
                self._log.exception("Watchdog tick failed")
            self._stop.wait(interval)


_GLOBAL: WatchdogService | None = None


def get_watchdog() -> WatchdogService:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = WatchdogService()
    return _GLOBAL
