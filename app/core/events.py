"""Thread-safe in-process event bus.

A tiny pub/sub abstraction so services (which run on threads or asyncio
loops) and the Qt UI can exchange messages without circular imports.
Subscribers are invoked synchronously in the publisher's thread; the UI
layer therefore wraps its handlers with :class:`QtCore.QMetaObject` or
``QTimer.singleShot`` to marshal back to the GUI thread.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Callable
from typing import Any

Handler = Callable[[Any], None]


class EventBus:
    """Simple synchronous pub/sub broker."""

    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, topic: str, handler: Handler) -> Callable[[], None]:
        with self._lock:
            self._subs[topic].append(handler)

        def unsubscribe() -> None:
            with self._lock:
                if handler in self._subs.get(topic, []):
                    self._subs[topic].remove(handler)

        return unsubscribe

    def publish(self, topic: str, payload: Any = None) -> None:
        with self._lock:
            subs = list(self._subs.get(topic, []))
        for handler in subs:
            try:
                handler(payload)
            except Exception:  # noqa: BLE001
                # We never let a buggy subscriber take down the publisher.
                import logging

                logging.getLogger("app.events").exception(
                    "Subscriber raised while handling %s", topic
                )

    def clear(self) -> None:
        with self._lock:
            self._subs.clear()


event_bus = EventBus()


# Canonical event topic names ------------------------------------------------
class Topics:
    STREAM_STATE = "stream.state"          # payload: {channel_id, state, info}
    STREAM_STATS = "stream.stats"          # payload: dict of per-channel stats
    STREAM_LOG = "stream.log"              # payload: {channel_id, line}
    SYSTEM_STATS = "system.stats"          # payload: SystemStats dict
    FFMPEG_STATE = "ffmpeg.state"          # payload: {state, version, path}
    NETWORK_STATE = "network.state"        # payload: {online, latency_ms}
    NOTIFICATION = "notification"          # payload: Notification dict
    SCHEDULER_TICK = "scheduler.tick"      # payload: {at}
    WATCHDOG_EVENT = "watchdog.event"      # payload: {channel_id, action}
    CHANNEL_CHANGED = "channel.changed"    # payload: {channel_id, action}
    PLAYLIST_CHANGED = "playlist.changed"  # payload: {playlist_id}
