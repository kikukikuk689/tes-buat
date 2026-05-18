"""Allow ``python -m asmr_loop_maker`` to invoke the CLI."""

from asmr_loop_maker.cli import main

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
