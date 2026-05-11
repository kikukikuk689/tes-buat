"""Aplikasi-wide logger dengan callback ke UI."""
from __future__ import annotations

import logging
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, List

_LOG_FILE = Path(__file__).resolve().parents[2] / "musicviz.log"
_lock = threading.Lock()
_subscribers: List[Callable[[str, str], None]] = []


def _ensure_logfile() -> Path:
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    return _LOG_FILE


def subscribe(callback: Callable[[str, str], None]) -> None:
    """Register a UI listener: callback(level, message)."""
    with _lock:
        if callback not in _subscribers:
            _subscribers.append(callback)


def unsubscribe(callback: Callable[[str, str], None]) -> None:
    with _lock:
        if callback in _subscribers:
            _subscribers.remove(callback)


class _UICallbackHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        with _lock:
            subs = list(_subscribers)
        for cb in subs:
            try:
                cb(record.levelname, msg)
            except Exception:  # noqa: BLE001
                pass


_logger: logging.Logger | None = None


def get_logger(name: str = "musicviz") -> logging.Logger:
    """Lazy-initialised singleton logger."""
    global _logger
    if _logger is None:
        log = logging.getLogger("musicviz")
        log.setLevel(logging.INFO)
        log.propagate = False
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            "%H:%M:%S",
        )

        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        log.addHandler(sh)

        try:
            fh = logging.FileHandler(_ensure_logfile(), encoding="utf-8")
            fh.setFormatter(fmt)
            log.addHandler(fh)
        except OSError:
            pass

        uh = _UICallbackHandler()
        uh.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
        log.addHandler(uh)

        _logger = log

    return _logger if name == "musicviz" else _logger.getChild(name)


def log_session_header() -> None:
    log = get_logger()
    log.info("=" * 50)
    log.info("MusicViz Studio session start %s", datetime.now().isoformat(timespec="seconds"))
    log.info("=" * 50)
