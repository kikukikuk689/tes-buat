"""Notification center.

Publishes notifications on the event bus and dispatches them to:

* the in-app toast widget (subscribed by ``MainWindow``)
* the system tray icon (subscribed by :class:`SystemTrayService`)
* the desktop OS via PySide6's ``QSystemTrayIcon.showMessage``
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Literal

from ..core.config import get_config
from ..core.events import Topics, event_bus

Severity = Literal["info", "success", "warning", "error", "critical"]


@dataclass
class Notification:
    title: str
    message: str
    severity: Severity = "info"
    ts: float = field(default_factory=time.time)
    duration_ms: int = 4500


class NotificationCenter:
    def __init__(self) -> None:
        self._history: list[Notification] = []
        self._lock = threading.RLock()

    def notify(
        self,
        title: str,
        message: str,
        severity: Severity = "info",
        duration_ms: int = 4500,
    ) -> Notification:
        n = Notification(title=title, message=message, severity=severity, duration_ms=duration_ms)
        with self._lock:
            self._history.append(n)
            self._history = self._history[-200:]
        cfg = get_config().config.general
        if cfg.enable_notifications:
            event_bus.publish(
                Topics.NOTIFICATION,
                {
                    "title": n.title,
                    "message": n.message,
                    "severity": n.severity,
                    "duration_ms": n.duration_ms,
                    "ts": n.ts,
                },
            )
        return n

    def history(self) -> list[Notification]:
        with self._lock:
            return list(self._history)


_GLOBAL: NotificationCenter | None = None


def get_notifier() -> NotificationCenter:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = NotificationCenter()
    return _GLOBAL
