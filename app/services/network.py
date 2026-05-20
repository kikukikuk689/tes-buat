"""Internet connectivity monitor.

Periodically hits a lightweight URL to detect when the network goes
down or recovers, publishing events the stream engine can react to.
"""
from __future__ import annotations

import threading
import time

import httpx

from ..core.config import get_config
from ..core.events import Topics, event_bus
from ..core.logger import get_logger


class NetworkMonitor:
    def __init__(self) -> None:
        self._log = get_logger("network")
        self._cfg = get_config().config.performance
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.online: bool = True
        self.latency_ms: float = 0.0
        self.last_check: float = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="network", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        interval = max(1.0, self._cfg.network_check_interval_ms / 1000.0)
        url = self._cfg.network_check_url
        client = httpx.Client(timeout=5)
        while not self._stop.is_set():
            online = False
            latency = 0.0
            t0 = time.monotonic()
            try:
                resp = client.get(url)
                latency = (time.monotonic() - t0) * 1000.0
                online = resp.status_code < 500
            except httpx.HTTPError as exc:
                online = False
                self._log.debug("Network probe failed: %s", exc)
            self.last_check = time.time()
            changed = online != self.online
            self.online = online
            self.latency_ms = latency
            if changed:
                self._log.info("Internet %s (%.0f ms)", "ONLINE" if online else "OFFLINE", latency)
                event_bus.publish(
                    Topics.NETWORK_STATE,
                    {"online": online, "latency_ms": latency, "ts": self.last_check},
                )
            else:
                event_bus.publish(
                    Topics.NETWORK_STATE,
                    {"online": online, "latency_ms": latency, "ts": self.last_check, "silent": True},
                )
            self._stop.wait(interval)
        client.close()


_GLOBAL: NetworkMonitor | None = None


def get_network_monitor() -> NetworkMonitor:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = NetworkMonitor()
    return _GLOBAL
