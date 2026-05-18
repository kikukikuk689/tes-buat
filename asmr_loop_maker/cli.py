"""Command-line interface for ASMR Seamless Loop Maker."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

from asmr_loop_maker.batch import process_batch
from asmr_loop_maker.processor import process_video
from asmr_loop_maker.utils import (
    SUPPORTED_EXTENSIONS,
    ensure_ffmpeg,
    humanise_seconds,
    is_supported_video,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="asmr-loop-maker",
        description=(
            "Turn a short clip into a long, seamlessly looping ASMR video. "
            "Accepts a single file or a folder for batch processing."
        ),
    )
    parser.add_argument(
        "input",
        type=Path,
        help=(
            "Input video file or folder containing videos "
            f"({', '.join(SUPPORTED_EXTENSIONS)})."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help=(
            "Output path. For a single file input, this is the .mp4 output "
            "file. For a folder input, this is the output folder."
        ),
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=1.0,
        help="Target output duration in hours (default: %(default)s).",
    )
    parser.add_argument(
        "--crossfade",
        type=float,
        default=0.5,
        help="Crossfade duration between loops, in seconds (default: %(default)s).",
    )
    parser.add_argument(
        "--min-loop",
        type=float,
        default=1.5,
        help="Minimum loop length in seconds (default: %(default)s).",
    )
    parser.add_argument(
        "--max-loop",
        type=float,
        default=None,
        help="Optional maximum loop length in seconds.",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=20,
        help="x264 CRF quality (lower = better, default: %(default)s).",
    )
    parser.add_argument(
        "--preset",
        type=str,
        default="medium",
        help="x264 preset (default: %(default)s).",
    )
    parser.add_argument(
        "--report",
        type=str,
        default="batch_report.csv",
        help="Filename for the batch report CSV (default: %(default)s).",
    )
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Do not overwrite existing output files; append _N instead.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output after processing.",
    )
    return parser


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _print_single_progress(stage: str, fraction: float) -> None:
    bar_width = 24
    filled = int(round(bar_width * fraction))
    bar = "#" * filled + "-" * (bar_width - filled)
    sys.stdout.write(f"\r[{stage:>8}] |{bar}| {fraction * 100:5.1f}%")
    sys.stdout.flush()
    if fraction >= 1.0:
        sys.stdout.write("\n")
        sys.stdout.flush()


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    try:
        ensure_ffmpeg()
    except RuntimeError as exc:
        parser.error(str(exc))

    input_path: Path = args.input
    output_path: Path = args.output
    start_time = time.monotonic()

    if input_path.is_dir():
        result = process_batch(
            input_path,
            output_path,
            target_hours=args.hours,
            crossfade_seconds=args.crossfade,
            min_loop_seconds=args.min_loop,
            max_loop_seconds=args.max_loop,
            crf=args.crf,
            preset=args.preset,
            overwrite=not args.no_overwrite,
            report_name=args.report,
            progress=lambda idx, total, path: print(
                f"[{idx}/{total}] {path}", flush=True
            ),
        )
        elapsed = time.monotonic() - start_time
        ok = len(result.succeeded)
        fail = len(result.failed)
        print(
            f"Batch finished in {humanise_seconds(elapsed)}: "
            f"{ok} ok, {fail} failed. Report: {result.report_path}",
            flush=True,
        )
        if args.json:
            print(
                json.dumps(
                    {
                        "ok": ok,
                        "failed": fail,
                        "report_path": result.report_path,
                        "items": [
                            {
                                "input": item.input_path,
                                "output": item.output_path,
                                "status": item.status,
                                "message": item.message,
                                "elapsed_seconds": item.elapsed_seconds,
                            }
                            for item in result.items
                        ],
                    },
                    indent=2,
                )
            )
        return 0 if fail == 0 else 1

    if not input_path.exists():
        parser.error(f"Input does not exist: {input_path}")
    if not is_supported_video(input_path):
        parser.error(
            f"Unsupported input video: {input_path} "
            f"(supported: {', '.join(SUPPORTED_EXTENSIONS)})"
        )

    result = process_video(
        input_path,
        output_path,
        target_hours=args.hours,
        crossfade_seconds=args.crossfade,
        min_loop_seconds=args.min_loop,
        max_loop_seconds=args.max_loop,
        crf=args.crf,
        preset=args.preset,
        overwrite=not args.no_overwrite,
        progress=_print_single_progress,
    )
    elapsed = time.monotonic() - start_time
    print(
        f"Wrote {result.output_path} ({humanise_seconds(result.duration_achieved)}) "
        f"in {humanise_seconds(elapsed)}. "
        f"Loop score: {result.analysis.score:.3f} "
        f"(gray={result.analysis.grayscale_score:.3f}, "
        f"hist={result.analysis.histogram_score:.3f})",
        flush=True,
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
