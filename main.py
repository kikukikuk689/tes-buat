"""MusicViz Studio entrypoint."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root in path for direct invocation
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.utils.logger import get_logger, log_session_header  # noqa: E402
from src.ui.main_window import run_app  # noqa: E402


def main() -> int:
    log_session_header()
    log = get_logger()
    try:
        run_app()
        return 0
    except Exception as e:  # noqa: BLE001
        log.exception("Fatal: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
