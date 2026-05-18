"""Entry point that delegates to :mod:`app.cli`."""

from __future__ import annotations

import sys

from app.cli import main


if __name__ == "__main__":
    sys.exit(main())
