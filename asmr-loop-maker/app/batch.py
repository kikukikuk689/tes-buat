"""Single-video and batch processing pipelines for ASMR loop generation."""

from __future__ import annotations

import csv
import tempfile
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from tqdm import tqdm

from .analyzer import LoopInfo, find_best_loop_points
from .audio import extract_audio, mux_audio_video, render_looped_audio
from .config import (
    DEFAULT_CROSSFADE_SEC,
    DEFAULT_MIN_LOOP_SEC,
    DEFAULT_REPORTS_DIR,
    DEFAULT_TARGET_HOURS,
    OUTPUT_EXTENSION,
    OUTPUT_SUFFIX,
)
from .renderer import render_looped_video
from .utils import (
    build_output_path,
    ensure_dir,
    ensure_ffmpeg_available,
    list_videos_in_dir,
)

ProgressCallback = Callable[[str, float], None]


@dataclass
class ProcessResult:
    """Outcome of processing a single video.

    Attributes:
        filename: Source file name (basename only).
        status: ``"success"`` or ``"error"``.
        start_sec: Loop start time, in seconds.
        end_sec: Loop end time, in seconds.
        loop_sec: Loop duration, in seconds.
        score: Loop quality score (lower is better).
        output_path: Path to the final MP4 if successful, else empty.
        error: Error message if processing failed, else empty.
        loop_info: Full :class:`LoopInfo` for downstream consumers.
    """

    filename: str
    status: str
    start_sec: float = 0.0
    end_sec: float = 0.0
    loop_sec: float = 0.0
    score: float = 0.0
    output_path: str = ""
    error: str = ""
    loop_info: LoopInfo | None = field(default=None, repr=False)

    def to_row(self) -> dict[str, str]:
        """Return a CSV-friendly representation of this result."""

        row = asdict(self)
        row.pop("loop_info", None)
        return {k: ("" if v is None else str(v)) for k, v in row.items()}


def process_single_video(
    input_path: str | Path,
    output_dir: str | Path,
    target_hours: float = DEFAULT_TARGET_HOURS,
    crossfade_sec: float = DEFAULT_CROSSFADE_SEC,
    min_loop_sec: float = DEFAULT_MIN_LOOP_SEC,
    progress: ProgressCallback | None = None,
) -> ProcessResult:
    """Analyze, render and mux a single video into a long ASMR loop.

    All intermediate files (silent video, extracted audio, looped audio) are
    written to a temporary directory that is cleaned up automatically. The
    final MP4 is written to ``output_dir`` using
    :func:`~app.utils.build_output_path`.

    Args:
        input_path: Source video file.
        output_dir: Directory where the final MP4 is written.
        target_hours: Desired output duration in hours.
        crossfade_sec: Crossfade duration in seconds (visual & audio).
        min_loop_sec: Minimum allowed loop length in seconds.
        progress: Optional callback ``(stage_name, fraction)`` that the UI can
            use to surface progress. ``fraction`` is in ``[0.0, 1.0]``.

    Returns:
        A populated :class:`ProcessResult`. Failures never raise; the error is
        attached to the result.
    """

    input_path = Path(input_path)
    filename = input_path.name

    def emit(stage: str, frac: float) -> None:
        if progress is not None:
            progress(stage, max(0.0, min(1.0, frac)))

    try:
        ensure_ffmpeg_available()
        ensure_dir(output_dir)
        final_path = build_output_path(input_path, output_dir, OUTPUT_SUFFIX, OUTPUT_EXTENSION)

        emit("analyzing", 0.0)
        loop_info = find_best_loop_points(input_path, min_loop_sec=min_loop_sec)
        emit("analyzing", 1.0)

        with tempfile.TemporaryDirectory(prefix="asmr_loop_") as tmpdir:
            tmp_path = Path(tmpdir)
            silent_video = tmp_path / "loop_silent.mp4"
            source_wav = tmp_path / "source.wav"
            looped_wav = tmp_path / "loop.wav"

            emit("rendering_video", 0.0)
            render_looped_video(
                input_path=input_path,
                output_video_path=silent_video,
                loop_info=loop_info,
                target_hours=target_hours,
                crossfade_sec=crossfade_sec,
            )
            emit("rendering_video", 1.0)

            emit("extracting_audio", 0.0)
            extract_audio(input_path, source_wav)
            emit("extracting_audio", 1.0)

            emit("rendering_audio", 0.0)
            render_looped_audio(
                input_wav=source_wav,
                output_wav=looped_wav,
                start_sec=loop_info["start_sec"],
                end_sec=loop_info["end_sec"],
                target_hours=target_hours,
                crossfade_sec=crossfade_sec,
            )
            emit("rendering_audio", 1.0)

            emit("muxing", 0.0)
            mux_audio_video(silent_video, looped_wav, final_path)
            emit("muxing", 1.0)

        return ProcessResult(
            filename=filename,
            status="success",
            start_sec=float(loop_info["start_sec"]),
            end_sec=float(loop_info["end_sec"]),
            loop_sec=float(loop_info["loop_sec"]),
            score=float(loop_info["score"]),
            output_path=str(final_path),
            error="",
            loop_info=loop_info,
        )
    except Exception as exc:  # noqa: BLE001 - we want to report any failure
        return ProcessResult(
            filename=filename,
            status="error",
            error=f"{type(exc).__name__}: {exc}",
            loop_info=None,
        )


_REPORT_FIELDS: tuple[str, ...] = (
    "filename",
    "status",
    "start_sec",
    "end_sec",
    "loop_sec",
    "score",
    "output_path",
    "error",
)


def _write_report(results: list[ProcessResult], reports_dir: str | Path) -> Path:
    """Write a CSV summary of ``results`` to ``reports_dir`` and return its path."""

    reports_dir_path = ensure_dir(reports_dir)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir_path / f"batch_report_{ts}.csv"
    with report_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(_REPORT_FIELDS))
        writer.writeheader()
        for r in results:
            writer.writerow({k: r.to_row().get(k, "") for k in _REPORT_FIELDS})
    return report_path


def process_batch(
    input_dir: str | Path,
    output_dir: str | Path,
    target_hours: float = DEFAULT_TARGET_HOURS,
    crossfade_sec: float = DEFAULT_CROSSFADE_SEC,
    min_loop_sec: float = DEFAULT_MIN_LOOP_SEC,
    reports_dir: str | Path = DEFAULT_REPORTS_DIR,
    progress: ProgressCallback | None = None,
) -> tuple[list[ProcessResult], Path]:
    """Process every supported video inside ``input_dir``.

    Files are processed in alphabetical order. A failure on one file does not
    stop the batch; the error is recorded in the result row instead. After all
    files are processed, a CSV report is written to ``reports_dir``.

    Args:
        input_dir: Directory containing source videos.
        output_dir: Directory where rendered MP4s are written.
        target_hours: Desired duration of each output, in hours.
        crossfade_sec: Crossfade duration in seconds.
        min_loop_sec: Minimum loop length in seconds.
        reports_dir: Directory where the CSV report is written.
        progress: Optional per-file callback ``(stage, fraction)``.

    Returns:
        A tuple ``(results, report_path)``.

    Raises:
        FileNotFoundError: If ``input_dir`` does not exist.
        ValueError: If no supported videos were found in ``input_dir``.
    """

    input_dir_path = Path(input_dir)
    if not input_dir_path.is_dir():
        raise FileNotFoundError(f"Folder input tidak ditemukan: {input_dir_path}")

    videos = list_videos_in_dir(input_dir_path)
    if not videos:
        raise ValueError(f"Tidak ada video yang didukung di {input_dir_path}")

    results: list[ProcessResult] = []
    progress_bar = tqdm(videos, desc="Batch", unit="vid")
    for video in progress_bar:
        progress_bar.set_postfix_str(video.name)
        try:
            result = process_single_video(
                input_path=video,
                output_dir=output_dir,
                target_hours=target_hours,
                crossfade_sec=crossfade_sec,
                min_loop_sec=min_loop_sec,
                progress=progress,
            )
        except Exception as exc:  # pragma: no cover - safety net
            result = ProcessResult(
                filename=video.name,
                status="error",
                error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=2)}",
            )
        results.append(result)

    report_path = _write_report(results, reports_dir)
    return results, report_path
