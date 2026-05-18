"""Batch processing of many videos with a CSV report."""

from __future__ import annotations

import csv
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from asmr_loop_maker.processor import ProcessResult, process_video
from asmr_loop_maker.utils import iter_video_files

logger = logging.getLogger("asmr_loop_maker.batch")


@dataclass
class BatchItem:
    input_path: str
    output_path: str
    status: str  # "ok" or "error"
    elapsed_seconds: float
    message: str = ""
    result: Optional[ProcessResult] = None


@dataclass
class BatchResult:
    items: List[BatchItem] = field(default_factory=list)
    report_path: Optional[str] = None

    @property
    def succeeded(self) -> List[BatchItem]:
        return [item for item in self.items if item.status == "ok"]

    @property
    def failed(self) -> List[BatchItem]:
        return [item for item in self.items if item.status != "ok"]


def _build_output_path(input_path: Path, output_dir: Path) -> Path:
    return output_dir / f"{input_path.stem}_asmr_loop.mp4"


def write_report(items: List[BatchItem], report_path: Path) -> None:
    """Persist a CSV report of ``items`` to ``report_path``."""

    report_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "input_path",
        "output_path",
        "status",
        "elapsed_seconds",
        "message",
        "target_duration_seconds",
        "crossfade_seconds",
        "has_audio",
        "analysis_start_frame",
        "analysis_end_frame",
        "analysis_start_time",
        "analysis_end_time",
        "analysis_loop_duration",
        "analysis_score",
        "analysis_grayscale_score",
        "analysis_histogram_score",
        "analysis_duration_score",
        "analysis_fps",
        "analysis_total_frames",
    ]
    with report_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            row = {
                "input_path": item.input_path,
                "output_path": item.output_path,
                "status": item.status,
                "elapsed_seconds": f"{item.elapsed_seconds:.2f}",
                "message": item.message,
            }
            if item.result is not None:
                row["target_duration_seconds"] = f"{item.result.target_duration:.2f}"
                row["crossfade_seconds"] = f"{item.result.crossfade_seconds:.3f}"
                row["has_audio"] = str(item.result.has_audio).lower()
                analysis = item.result.analysis
                row["analysis_start_frame"] = analysis.start_frame
                row["analysis_end_frame"] = analysis.end_frame
                row["analysis_start_time"] = f"{analysis.start_time:.3f}"
                row["analysis_end_time"] = f"{analysis.end_time:.3f}"
                row["analysis_loop_duration"] = f"{analysis.loop_duration:.3f}"
                row["analysis_score"] = f"{analysis.score:.4f}"
                row["analysis_grayscale_score"] = f"{analysis.grayscale_score:.4f}"
                row["analysis_histogram_score"] = f"{analysis.histogram_score:.4f}"
                row["analysis_duration_score"] = f"{analysis.duration_score:.4f}"
                row["analysis_fps"] = f"{analysis.fps:.3f}"
                row["analysis_total_frames"] = analysis.total_frames
            writer.writerow(row)


def process_batch(
    input_folder: str | Path,
    output_folder: str | Path,
    *,
    target_hours: float = 1.0,
    crossfade_seconds: float = 0.5,
    min_loop_seconds: float = 1.5,
    max_loop_seconds: Optional[float] = None,
    crf: int = 20,
    preset: str = "medium",
    overwrite: bool = True,
    report_name: str = "batch_report.csv",
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> BatchResult:
    """Process every supported video in ``input_folder``.

    ``progress(index, total, current_path)`` is called before each file is
    processed.  Errors on individual videos are captured and reported but
    do not stop the batch.
    """

    in_folder = Path(input_folder)
    out_folder = Path(output_folder)
    videos = iter_video_files(in_folder)
    if not videos:
        raise RuntimeError(f"No supported videos found in {in_folder}")
    out_folder.mkdir(parents=True, exist_ok=True)

    items: List[BatchItem] = []
    total = len(videos)
    for idx, video in enumerate(videos, start=1):
        output_path = _build_output_path(video, out_folder)
        if progress:
            progress(idx, total, str(video))
        start = time.monotonic()
        try:
            result = process_video(
                video,
                output_path,
                target_hours=target_hours,
                crossfade_seconds=crossfade_seconds,
                min_loop_seconds=min_loop_seconds,
                max_loop_seconds=max_loop_seconds,
                crf=crf,
                preset=preset,
                overwrite=overwrite,
            )
            elapsed = time.monotonic() - start
            items.append(
                BatchItem(
                    input_path=str(video),
                    output_path=str(result.output_path),
                    status="ok",
                    elapsed_seconds=elapsed,
                    message="",
                    result=result,
                )
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.exception("Failed to process %s", video)
            items.append(
                BatchItem(
                    input_path=str(video),
                    output_path=str(output_path),
                    status="error",
                    elapsed_seconds=elapsed,
                    message=str(exc),
                )
            )

    report_path = out_folder / report_name
    write_report(items, report_path)
    return BatchResult(items=items, report_path=str(report_path))
