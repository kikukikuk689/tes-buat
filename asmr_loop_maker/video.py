"""Video loop rendering with frame-level crossfade.

The renderer reads the chosen segment into memory once, builds a
crossfaded "loop unit" (where the first ``crossfade_seconds`` blend the
segment's tail and head), then streams that unit into an ``ffmpeg``
encoder over and over until the target duration is reached.

This keeps memory usage bounded to a single segment of frames regardless
of how long the output is.
"""

from __future__ import annotations

import logging
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional

import cv2
import numpy as np

from asmr_loop_maker.utils import ensure_ffmpeg

logger = logging.getLogger("asmr_loop_maker.video")


@dataclass
class VideoMeta:
    width: int
    height: int
    fps: float
    total_frames: int


def read_segment_frames(
    video_path: Path, start_frame: int, end_frame: int
) -> tuple[List[np.ndarray], VideoMeta]:
    """Read frames ``[start_frame, end_frame]`` from ``video_path``.

    Both endpoints are inclusive.
    """

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if start_frame < 0:
        start_frame = 0
    if end_frame >= total:
        end_frame = total - 1

    frames: List[np.ndarray] = []
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    remaining = end_frame - start_frame + 1
    while remaining > 0:
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(frame)
        remaining -= 1
    cap.release()

    if not frames:
        raise RuntimeError(
            f"Could not read frames {start_frame}-{end_frame} from {video_path}"
        )

    return frames, VideoMeta(width=width, height=height, fps=fps, total_frames=total)


def build_loop_unit(
    frames: List[np.ndarray], crossfade_frames: int
) -> List[np.ndarray]:
    """Return a list of frames that loops seamlessly when concatenated."""

    n = len(frames)
    crossfade_frames = max(0, min(crossfade_frames, n // 2))

    if crossfade_frames == 0:
        return [frame.copy() for frame in frames]

    unit: List[np.ndarray] = []
    for i in range(crossfade_frames):
        alpha = float(i) / float(crossfade_frames)
        tail_frame = frames[n - crossfade_frames + i]
        head_frame = frames[i]
        blended = cv2.addWeighted(tail_frame, 1.0 - alpha, head_frame, alpha, 0.0)
        unit.append(blended)
    for i in range(crossfade_frames, n - crossfade_frames):
        unit.append(frames[i])
    return unit


def _open_encoder(
    output_path: Path,
    width: int,
    height: int,
    fps: float,
    *,
    crf: int = 20,
    preset: str = "medium",
) -> subprocess.Popen:
    ffmpeg = ensure_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-s",
        f"{width}x{height}",
        "-pix_fmt",
        "bgr24",
        "-r",
        f"{fps:.6f}",
        "-i",
        "-",
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)


def render_video_loop(
    video_path: Path,
    start_frame: int,
    end_frame: int,
    target_duration_seconds: float,
    crossfade_seconds: float,
    output_path: Path,
    *,
    crf: int = 20,
    preset: str = "medium",
    progress: Optional[Callable[[int, int], None]] = None,
) -> VideoMeta:
    """Render a long looped video to ``output_path``.

    Parameters
    ----------
    video_path:
        Source video.
    start_frame, end_frame:
        Inclusive frame indices defining the loop segment.
    target_duration_seconds:
        Desired output length in seconds.
    crossfade_seconds:
        Duration of the visual crossfade applied between loop iterations.
    output_path:
        Output ``.mp4`` path.
    progress:
        Optional callback ``f(frames_written, target_frames)`` for UI updates.
    """

    frames, meta = read_segment_frames(video_path, start_frame, end_frame)
    crossfade_frames = int(round(max(0.0, crossfade_seconds) * meta.fps))
    unit = build_loop_unit(frames, crossfade_frames)
    unit_count = len(unit)
    if unit_count == 0:
        raise RuntimeError("Could not build a loop unit from the segment frames")

    target_frames = max(1, int(round(target_duration_seconds * meta.fps)))

    proc = _open_encoder(
        output_path,
        meta.width,
        meta.height,
        meta.fps,
        crf=crf,
        preset=preset,
    )

    written = 0
    try:
        assert proc.stdin is not None
        while written < target_frames:
            for frame in unit:
                proc.stdin.write(frame.tobytes())
                written += 1
                if progress and (written % max(1, unit_count) == 0):
                    progress(written, target_frames)
                if written >= target_frames:
                    break
        proc.stdin.flush()
        proc.stdin.close()
    except BrokenPipeError as exc:
        stderr_bytes = proc.stderr.read() if proc.stderr else b""
        if proc.stderr is not None:
            proc.stderr.close()
        stderr = stderr_bytes.decode("utf-8", errors="ignore")
        raise RuntimeError(f"ffmpeg encoder pipe closed early: {stderr}") from exc

    return_code = proc.wait()
    stderr_bytes = proc.stderr.read() if proc.stderr else b""
    if proc.stderr is not None:
        proc.stderr.close()
    stderr = stderr_bytes.decode("utf-8", errors="ignore")
    if return_code != 0:
        raise RuntimeError(f"ffmpeg encoder failed (exit {return_code}): {stderr}")

    if progress:
        progress(target_frames, target_frames)

    return meta


def estimate_unit_count(
    segment_seconds: float, crossfade_seconds: float, target_seconds: float
) -> int:
    """Estimate how many loop units are needed to reach ``target_seconds``."""

    unit_seconds = max(segment_seconds - crossfade_seconds, 0.001)
    return max(1, math.ceil(target_seconds / unit_seconds))


def iter_unit_indices(unit_count: int) -> Iterable[int]:
    """Helper: iterate indices from 0 to ``unit_count`` (inclusive)."""

    return range(unit_count + 1)
