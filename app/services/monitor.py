"""Real-time system + process monitor."""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field

import psutil

from ..core.config import get_config
from ..core.events import Topics, event_bus
from ..core.logger import get_logger


@dataclass
class SystemStats:
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    ram_used_mb: float = 0.0
    ram_total_mb: float = 0.0
    gpu_percent: float | None = None
    net_up_kbps: float = 0.0
    net_down_kbps: float = 0.0
    process_count: int = 0
    uptime_sec: float = 0.0
    history_cpu: list[float] = field(default_factory=list)
    history_net_up: list[float] = field(default_factory=list)
    history_net_down: list[float] = field(default_factory=list)


class MonitorService:
    """Periodically samples system metrics and publishes them."""

    def __init__(self) -> None:
        self._log = get_logger("monitor")
        self._cfg = get_config().config.performance
        self._stats = SystemStats(ram_total_mb=psutil.virtual_memory().total / (1024 * 1024))
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_net = psutil.net_io_counters()
        self._last_ts = time.monotonic()
        self._started_at = time.monotonic()
        self._history_cap = 60

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def stats(self) -> SystemStats:
        with self._lock:
            return self._stats

    # ------------------------------------------------------------------
    def _loop(self) -> None:
        interval = max(0.25, self._cfg.monitor_interval_ms / 1000.0)
        # prime CPU readings
        psutil.cpu_percent(None)
        while not self._stop.is_set():
            try:
                cpu = psutil.cpu_percent(None)
                mem = psutil.virtual_memory()
                now = time.monotonic()
                net = psutil.net_io_counters()
                dt = max(0.001, now - self._last_ts)
                up_kbps = max(0.0, (net.bytes_sent - self._last_net.bytes_sent) * 8 / dt / 1000.0)
                down_kbps = max(0.0, (net.bytes_recv - self._last_net.bytes_recv) * 8 / dt / 1000.0)
                self._last_net = net
                self._last_ts = now
                gpu = self._sample_gpu()
                with self._lock:
                    s = self._stats
                    s.cpu_percent = cpu
                    s.ram_percent = mem.percent
                    s.ram_used_mb = mem.used / (1024 * 1024)
                    s.ram_total_mb = mem.total / (1024 * 1024)
                    s.net_up_kbps = up_kbps
                    s.net_down_kbps = down_kbps
                    s.gpu_percent = gpu
                    s.process_count = len(psutil.pids())
                    s.uptime_sec = now - self._started_at
                    s.history_cpu = (s.history_cpu + [cpu])[-self._history_cap :]
                    s.history_net_up = (s.history_net_up + [up_kbps])[-self._history_cap :]
                    s.history_net_down = (s.history_net_down + [down_kbps])[-self._history_cap :]
                event_bus.publish(Topics.SYSTEM_STATS, asdict(self._stats))
            except Exception:  # noqa: BLE001
                self._log.exception("Monitor sample failed")
            self._stop.wait(interval)

    @staticmethod
    def _sample_gpu() -> float | None:
        try:
            import subprocess

            out = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
            lines = [l.strip() for l in out.splitlines() if l.strip()]
            if lines:
                return float(lines[0])
        except Exception:  # noqa: BLE001
            return None
        return None


_GLOBAL: MonitorService | None = None


def get_monitor() -> MonitorService:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = MonitorService()
    return _GLOBAL
