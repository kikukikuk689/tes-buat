"""Lightweight signal-based logger that writes to file AND emits Qt signals."""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional


_LOG_DIR = Path.cwd() / "output" / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / f"app_{time.strftime('%Y%m%d_%H%M%S')}.log"


class AppLogger:
    """Singleton-style logger with optional GUI listener.

    Use ``AppLogger.get()`` to obtain the shared instance.
    """

    _instance: Optional["AppLogger"] = None

    def __init__(self):
        self._listeners: List[Callable[[str, str], None]] = []
        fmt = logging.Formatter("[%(asctime)s] %(levelname)s | %(message)s",
                                datefmt="%H:%M:%S")
        self._logger = logging.getLogger("music_spectrum_studio")
        self._logger.setLevel(logging.DEBUG)
        # Avoid duplicate handlers on hot-reload.
        if not self._logger.handlers:
            fh = logging.FileHandler(_LOG_FILE, encoding="utf-8")
            fh.setFormatter(fmt)
            fh.setLevel(logging.DEBUG)
            self._logger.addHandler(fh)

            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(fmt)
            sh.setLevel(logging.INFO)
            self._logger.addHandler(sh)

    @classmethod
    def get(cls) -> "AppLogger":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def add_listener(self, fn: Callable[[str, str], None]) -> None:
        self._listeners.append(fn)

    def _emit(self, level: str, msg: str) -> None:
        for fn in self._listeners:
            try:
                fn(level, msg)
            except Exception:  # pragma: no cover
                pass

    def debug(self, msg: str) -> None:
        self._logger.debug(msg)
        self._emit("DEBUG", msg)

    def info(self, msg: str) -> None:
        self._logger.info(msg)
        self._emit("INFO", msg)

    def warning(self, msg: str) -> None:
        self._logger.warning(msg)
        self._emit("WARNING", msg)

    def error(self, msg: str) -> None:
        self._logger.error(msg)
        self._emit("ERROR", msg)

    @property
    def log_path(self) -> Path:
        return _LOG_FILE
