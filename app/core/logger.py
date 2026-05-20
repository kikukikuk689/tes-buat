"""Logging configuration.

Configures rotating file handlers and a console handler.  All other
modules import :func:`get_logger` and never call ``logging.getLogger``
directly so we can swap handlers (e.g. add a Qt-aware sink) in one
place.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
from collections.abc import Iterable
from pathlib import Path

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_INITIALISED = False
_HANDLERS: list[logging.Handler] = []


def setup_logging(
    log_dir: Path,
    level: int = logging.INFO,
    extra_handlers: Iterable[logging.Handler] | None = None,
) -> None:
    """Initialise the root logger.  Safe to call multiple times."""
    global _INITIALISED
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    if _INITIALISED:
        for h in extra_handlers or []:
            h.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))
            root.addHandler(h)
            _HANDLERS.append(h)
        return

    # Remove default handlers so we don't double-log under pytest.
    for h in list(root.handlers):
        root.removeHandler(h)

    formatter = logging.Formatter(_LOG_FORMAT, _DATE_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "studio.log",
        maxBytes=8 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    root.addHandler(file_handler)
    _HANDLERS.append(file_handler)

    ffmpeg_handler = logging.handlers.RotatingFileHandler(
        log_dir / "ffmpeg.log",
        maxBytes=16 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    ffmpeg_handler.setFormatter(formatter)
    ffmpeg_handler.addFilter(_NameFilter("ffmpeg"))
    root.addHandler(ffmpeg_handler)
    _HANDLERS.append(ffmpeg_handler)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(level)
    root.addHandler(stream_handler)
    _HANDLERS.append(stream_handler)

    for h in extra_handlers or []:
        h.setFormatter(formatter)
        root.addHandler(h)
        _HANDLERS.append(h)

    # Tame noisy third-parties.
    for noisy in ("urllib3", "httpx", "httpcore", "PIL", "uvicorn.error"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _INITIALISED = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger qualified to the application namespace."""
    if name.startswith("app.") or name in {"app", "ffmpeg", "crash"}:
        return logging.getLogger(name)
    return logging.getLogger(f"app.{name}")


class _NameFilter(logging.Filter):
    def __init__(self, prefix: str) -> None:
        super().__init__()
        self._prefix = prefix

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name == self._prefix or record.name.startswith(self._prefix + ".")
