"""Command-line interface for ASMR Seamless Loop Maker."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .batch import process_batch, process_single_video
from .config import (
    DEFAULT_CROSSFADE_SEC,
    DEFAULT_MIN_LOOP_SEC,
    DEFAULT_REPORTS_DIR,
    DEFAULT_TARGET_HOURS,
)
from .utils import FFmpegNotFoundError, ensure_ffmpeg_available, is_video_file


def build_parser() -> argparse.ArgumentParser:
    """Build the :class:`argparse.ArgumentParser` used by the CLI."""

    parser = argparse.ArgumentParser(
        prog="asmr-loop-maker",
        description=(
            "ASMR Seamless Loop Maker — ubah video pendek menjadi video ASMR "
            "berdurasi panjang dengan loop yang mulus."
        ),
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path file video tunggal atau folder berisi banyak video.",
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Folder output untuk menyimpan hasil video ASMR.",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=DEFAULT_TARGET_HOURS,
        help=f"Durasi target output dalam jam (default: {DEFAULT_TARGET_HOURS}).",
    )
    parser.add_argument(
        "--crossfade",
        type=float,
        default=DEFAULT_CROSSFADE_SEC,
        help=f"Durasi crossfade antar-loop dalam detik (default: {DEFAULT_CROSSFADE_SEC}).",
    )
    parser.add_argument(
        "--min-loop",
        type=float,
        default=DEFAULT_MIN_LOOP_SEC,
        help=f"Durasi minimum satu loop dalam detik (default: {DEFAULT_MIN_LOOP_SEC}).",
    )
    parser.add_argument(
        "--reports",
        default=str(DEFAULT_REPORTS_DIR),
        help="Folder untuk menyimpan CSV report batch (default: reports/).",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Paksa mode batch (proses semua video di folder --input).",
    )
    return parser


def _format_result_line(filename: str, status: str, output_path: str, error: str) -> str:
    if status == "success":
        return f"[OK] {filename} -> {output_path}"
    return f"[ERR] {filename}: {error}"


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point used by both :mod:`main` and ``python -m app.cli``.

    Args:
        argv: Optional argument list (defaults to :data:`sys.argv` ``[1:]``).

    Returns:
        Process exit code (0 on success, non-zero on failure).
    """

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.hours <= 0:
        parser.error("--hours harus > 0")
    if args.crossfade < 0:
        parser.error("--crossfade harus >= 0")
    if args.min_loop <= 0:
        parser.error("--min-loop harus > 0")

    try:
        ensure_ffmpeg_available()
    except FFmpegNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    input_path = Path(args.input)
    output_dir = Path(args.output)

    if not input_path.exists():
        print(f"ERROR: Path input tidak ditemukan: {input_path}", file=sys.stderr)
        return 2

    is_batch = args.batch or input_path.is_dir()
    if is_batch:
        try:
            results, report_path = process_batch(
                input_dir=input_path,
                output_dir=output_dir,
                target_hours=args.hours,
                crossfade_sec=args.crossfade,
                min_loop_sec=args.min_loop,
                reports_dir=args.reports,
            )
        except (FileNotFoundError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

        successes = 0
        for r in results:
            print(_format_result_line(r.filename, r.status, r.output_path, r.error))
            if r.status == "success":
                successes += 1
        print(f"\nBatch selesai: {successes}/{len(results)} berhasil.")
        print(f"Report: {report_path}")
        return 0 if successes == len(results) else 1

    if not is_video_file(input_path):
        print(f"ERROR: File bukan video yang didukung: {input_path}", file=sys.stderr)
        return 2

    result = process_single_video(
        input_path=input_path,
        output_dir=output_dir,
        target_hours=args.hours,
        crossfade_sec=args.crossfade,
        min_loop_sec=args.min_loop,
    )
    print(_format_result_line(result.filename, result.status, result.output_path, result.error))
    if result.status == "success" and result.loop_info is not None:
        info = result.loop_info
        print(
            "Loop terbaik: "
            f"start={info['start_sec']:.3f}s end={info['end_sec']:.3f}s "
            f"durasi={info['loop_sec']:.3f}s score={info['score']:.5f} "
            f"(fps={info['fps']:.2f}, total_frames={info['total_frames']})"
        )
    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
