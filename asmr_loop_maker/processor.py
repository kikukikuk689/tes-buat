"""High-level orchestration: analyse + render + mux a single video."""

from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

from asmr_loop_maker.analyzer import LoopAnalysis, analyze_video
from asmr_loop_maker.audio import render_audio_loop
from asmr_loop_maker.utils import (
    ensure_ffmpeg,
    humanise_seconds,
    is_supported_video,
    run_command,
    unique_path,
)
from asmr_loop_maker.video import render_video_loop

logger = logging.getLogger("asmr_loop_maker.processor")


@dataclass
class ProcessResult:
    input_path: str
    output_path: str
    analysis: LoopAnalysis
    target_duration: float
    crossfade_seconds: float
    has_audio: bool
    duration_achieved: float

    def to_dict(self) -> dict:
        data = asdict(self)
        # Flatten the analysis dict into the row for CSV friendliness.
        analysis_dict = data.pop("analysis")
        for key, value in analysis_dict.items():
            data[f"analysis_{key}"] = value
        return data


def _mux_video_audio(
    video_path: Path, audio_path: Optional[Path], output_path: Path
) -> None:
    """Mux a silent video with an optional audio track to ``output_path``."""

    ffmpeg = ensure_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if audio_path is None or not audio_path.exists():
        shutil.copyfile(video_path, output_path)
        return

    cmd = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    run_command(cmd)


def process_video(
    input_path: str | Path,
    output_path: str | Path,
    *,
    target_hours: float = 1.0,
    crossfade_seconds: float = 0.5,
    min_loop_seconds: float = 1.5,
    max_loop_seconds: Optional[float] = None,
    crf: int = 20,
    preset: str = "medium",
    overwrite: bool = True,
    progress: Optional[Callable[[str, float], None]] = None,
    pre_analysis: Optional[LoopAnalysis] = None,
) -> ProcessResult:
    """Analyse ``input_path`` and render a long seamless loop to ``output_path``.

    ``progress(stage, fraction)`` is called with stage names
    ``"analyze"``, ``"video"``, ``"audio"``, ``"mux"`` and a ``fraction``
    in ``[0, 1]``.  ``fraction`` is best-effort and may jump.
    """

    in_path = Path(input_path)
    out_path = Path(output_path)
    if not in_path.exists():
        raise FileNotFoundError(f"Input video not found: {in_path}")
    if not is_supported_video(in_path):
        raise ValueError(
            f"Unsupported video format: {in_path.suffix} (expected .mp4/.mov/.mkv/.avi)"
        )
    if target_hours <= 0:
        raise ValueError("target_hours must be positive")
    if crossfade_seconds < 0:
        raise ValueError("crossfade_seconds must be non-negative")

    if not overwrite and out_path.exists():
        out_path = unique_path(out_path)

    target_seconds = float(target_hours) * 3600.0

    if progress:
        progress("analyze", 0.0)
    analysis = pre_analysis or analyze_video(
        in_path,
        min_loop_seconds=min_loop_seconds,
        max_loop_seconds=max_loop_seconds,
    )
    if progress:
        progress("analyze", 1.0)

    effective_crossfade = min(
        crossfade_seconds, max(0.0, analysis.loop_duration / 3.0)
    )
    if effective_crossfade < crossfade_seconds:
        logger.info(
            "Reducing crossfade for %s from %.2fs to %.2fs to fit segment of %.2fs",
            in_path.name,
            crossfade_seconds,
            effective_crossfade,
            analysis.loop_duration,
        )

    with tempfile.TemporaryDirectory(prefix="asmr_loop_") as tmpdir:
        tmp_root = Path(tmpdir)
        tmp_video = tmp_root / "loop_video.mp4"
        tmp_audio = tmp_root / "loop_audio.wav"

        def video_progress(written: int, total: int) -> None:
            if progress and total > 0:
                progress("video", min(1.0, written / total))

        render_video_loop(
            in_path,
            analysis.start_frame,
            analysis.end_frame,
            target_seconds,
            effective_crossfade,
            tmp_video,
            crf=crf,
            preset=preset,
            progress=video_progress,
        )
        if progress:
            progress("video", 1.0)

        if progress:
            progress("audio", 0.0)
        achieved_audio = render_audio_loop(
            in_path,
            analysis.start_time,
            analysis.end_time,
            target_seconds,
            effective_crossfade,
            tmp_audio,
            work_dir=tmp_root,
        )
        has_audio = achieved_audio is not None
        if progress:
            progress("audio", 1.0)

        if progress:
            progress("mux", 0.0)
        _mux_video_audio(tmp_video, tmp_audio if has_audio else None, out_path)
        if progress:
            progress("mux", 1.0)

    logger.info(
        "Wrote %s (%s) for %s", out_path, humanise_seconds(target_seconds), in_path
    )

    return ProcessResult(
        input_path=str(in_path),
        output_path=str(out_path),
        analysis=analysis,
        target_duration=target_seconds,
        crossfade_seconds=effective_crossfade,
        has_audio=has_audio,
        duration_achieved=target_seconds,
    )
