"""Video rendering: write looped segments with visual crossfades."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from tqdm import tqdm

from .analyzer import LoopInfo
from .config import DEFAULT_CROSSFADE_SEC, DEFAULT_VIDEO_CODEC


def _load_loop_frames(input_path: str | Path, start_frame: int, end_frame: int) -> list[np.ndarray]:
    """Read frames ``[start_frame, end_frame]`` (inclusive) into memory.

    Args:
        input_path: Source video path.
        start_frame: Index of the first frame to keep.
        end_frame: Index of the last frame to keep.

    Returns:
        List of BGR frames in capture order.

    Raises:
        IOError: If the video cannot be opened or contains no frames.
        ValueError: If the requested range is empty.
    """

    if end_frame < start_frame:
        raise ValueError(f"end_frame ({end_frame}) < start_frame ({start_frame})")

    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise IOError(f"Tidak bisa membuka video: {input_path}")

    frames: list[np.ndarray] = []
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, float(start_frame))
        for _ in range(end_frame - start_frame + 1):
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            frames.append(frame)
    finally:
        cap.release()

    if not frames:
        raise IOError(f"Tidak ada frame yang bisa dibaca dari {input_path}")
    return frames


def _crossfade_pairs(
    tail: Iterable[np.ndarray],
    head: Iterable[np.ndarray],
    crossfade_frames: int,
) -> list[np.ndarray]:
    """Alpha-blend ``tail`` with ``head`` over ``crossfade_frames`` frames."""

    blended: list[np.ndarray] = []
    tail_list = list(tail)
    head_list = list(head)
    n = min(len(tail_list), len(head_list), crossfade_frames)
    for i in range(n):
        alpha = (i + 1) / (n + 1)
        a = tail_list[i].astype(np.float32)
        b = head_list[i].astype(np.float32)
        mixed = (1.0 - alpha) * a + alpha * b
        blended.append(np.clip(mixed, 0, 255).astype(np.uint8))
    return blended


def render_looped_video(
    input_path: str | Path,
    output_video_path: str | Path,
    loop_info: LoopInfo,
    target_hours: float,
    crossfade_sec: float = DEFAULT_CROSSFADE_SEC,
) -> Path:
    """Render a long, silent looped video using OpenCV's :class:`cv2.VideoWriter`.

    Consecutive loops are joined with an alpha-blend crossfade of length
    ``crossfade_sec``. The output is written as MP4 with the codec configured
    in :data:`~app.config.DEFAULT_VIDEO_CODEC` and does **not** include audio;
    the audio track is produced separately and combined in
    :func:`app.audio.mux_audio_video`.

    Args:
        input_path: Source video path.
        output_video_path: Destination path for the silent intermediate video.
        loop_info: Loop boundaries returned by
            :func:`app.analyzer.find_best_loop_points`.
        target_hours: Desired total duration of the rendered video, in hours.
        crossfade_sec: Crossfade duration between consecutive loops, in seconds.

    Returns:
        The :class:`~pathlib.Path` of the written intermediate video.

    Raises:
        IOError: If the source video cannot be read or the writer cannot be opened.
        ValueError: If ``target_hours`` is not positive.
    """

    if target_hours <= 0:
        raise ValueError("target_hours harus > 0")

    fps = float(loop_info["fps"])
    start_frame = int(loop_info["start_frame"])
    end_frame = int(loop_info["end_frame"])

    base_frames = _load_loop_frames(input_path, start_frame, end_frame)
    loop_len = len(base_frames)
    if loop_len < 2:
        raise ValueError("Loop segment terlalu pendek untuk dirender.")

    height, width = base_frames[0].shape[:2]
    target_frames = max(loop_len, int(round(target_hours * 3600.0 * fps)))

    crossfade_frames = max(0, int(round(crossfade_sec * fps)))
    crossfade_frames = min(crossfade_frames, loop_len // 2)

    out_path = Path(output_video_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*DEFAULT_VIDEO_CODEC)
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (width, height))
    if not writer.isOpened():
        raise IOError(f"Tidak bisa membuka VideoWriter untuk {out_path}")

    progress = tqdm(total=target_frames, desc="Rendering video", unit="f", leave=False)
    try:
        if crossfade_frames <= 0:
            num_loops = math.ceil(target_frames / loop_len)
            written = 0
            for _ in range(num_loops):
                for frame in base_frames:
                    if written >= target_frames:
                        break
                    writer.write(frame)
                    written += 1
                    progress.update(1)
                if written >= target_frames:
                    break
        else:
            body_len = loop_len - crossfade_frames
            head = base_frames[:crossfade_frames]
            body = base_frames[crossfade_frames:]
            written = 0

            for frame in base_frames:
                if written >= target_frames:
                    break
                writer.write(frame)
                written += 1
                progress.update(1)

            while written < target_frames:
                tail = base_frames[-crossfade_frames:]
                blended = _crossfade_pairs(tail, head, crossfade_frames)
                for frame in blended:
                    if written >= target_frames:
                        break
                    writer.write(frame)
                    written += 1
                    progress.update(1)
                if written >= target_frames:
                    break
                for frame in body:
                    if written >= target_frames:
                        break
                    writer.write(frame)
                    written += 1
                    progress.update(1)
    finally:
        progress.close()
        writer.release()

    return out_path
