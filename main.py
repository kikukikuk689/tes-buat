#!/usr/bin/env python3
"""ASMR Broadcast Studio - desktop entry point.

This thin launcher only configures crash protection and hands control off
to :func:`app.app.run`.  The real bootstrap (logging, database, services,
UI) lives in :mod:`app.app` so that the same code can be invoked from
the Nuitka-built executable, tests, or development runs.
"""
from __future__ import annotations

import faulthandler
import os
import sys
import traceback
from pathlib import Path

# Make sure relative imports resolve when running as a script or from a
# Nuitka one-file build.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _excepthook(exc_type, exc, tb) -> None:
    """Last-resort exception handler so the app never dies silently."""
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    sys.stderr.write(text)
    try:
        from app.core.logger import get_logger

        get_logger("crash").exception("Unhandled exception", exc_info=(exc_type, exc, tb))
    except Exception:  # pragma: no cover - logger may not be ready yet
        pass


def main() -> int:
    faulthandler.enable()
    sys.excepthook = _excepthook
    # Enable High-DPI before any Qt import.
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

    from app.app import run

    return run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
