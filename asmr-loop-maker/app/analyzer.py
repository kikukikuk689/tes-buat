"""Video frame analysis for finding seamless loop points."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, TypedDict

import cv2
import numpy as np
from tqdm import tqdm

from .config import (
    ANALYSIS_RESIZE_WIDTH,
    DEFAULT_FPS,
    DEFAULT_MIN_LOOP_SEC,
    DEFAULT_SEARCH_STEP,
    DEFAULT_WINDOW_SEC,
    HIST_BINS,
)


class LoopInfo(TypedDict):
    """Structured result returned by :func:`find_best_loop_points`."""

    start_frame: int
    end_frame: int
    start_sec: float
    end_sec: float
    loop_sec: float
    score: float
    fps: float
    total_frames: int


@dataclass(frozen=True)
class FrameSignature:
    """Compact representation of a frame used for similarity comparisons.

    Attributes:
        gray: Downscaled single-channel grayscale image as ``float32``.
        hist: Flattened 3D HSV color histogram, L1-normalized.
    """

    gray: np.ndarray
    hist: np.ndarray


def _open_capture(video_path: str | Path) -> cv2.VideoCapture:
    """Open ``video_path`` with OpenCV and raise if it cannot be read."""

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise IOError(f"Tidak bisa membuka video: {video_path}")
    return cap


def _read_fps(cap: cv2.VideoCapture) -> float:
    """Return a sane FPS for the capture, falling back to :data:`DEFAULT_FPS`."""

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if fps <= 1e-3 or np.isnan(fps) or np.isinf(fps):
        return DEFAULT_FPS
    return fps


def _resize_for_analysis(frame: np.ndarray) -> np.ndarray:
    """Resize ``frame`` to :data:`ANALYSIS_RESIZE_WIDTH` keeping aspect ratio."""

    h, w = frame.shape[:2]
    if w <= 0 or h <= 0:
        return frame
    target_w = ANALYSIS_RESIZE_WIDTH
    target_h = max(1, int(round(h * (target_w / w))))
    return cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)


def read_video_frames(video_path: str | Path) -> Iterator[tuple[int, np.ndarray]]:
    """Yield ``(index, frame)`` pairs for every frame in ``video_path``.

    Frames are emitted in capture order using OpenCV's :class:`cv2.VideoCapture`.
    The capture is released even if iteration is aborted early.

    Args:
        video_path: Path to a readable video file.

    Yields:
        Tuples of ``(frame_index, BGR_frame)``.

    Raises:
        IOError: If OpenCV cannot open the file.
    """

    cap = _open_capture(video_path)
    try:
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            yield idx, frame
            idx += 1
    finally:
        cap.release()


def frame_signature(frame: np.ndarray) -> FrameSignature:
    """Compute a compact :class:`FrameSignature` for similarity comparisons.

    The signature combines a downscaled grayscale image (for structural
    similarity) and an HSV color histogram (for tonal similarity).

    Args:
        frame: A BGR frame as produced by OpenCV.

    Returns:
        The frame's :class:`FrameSignature`.
    """

    small = _resize_for_analysis(frame)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist(
        [hsv],
        [0, 1, 2],
        None,
        [HIST_BINS, HIST_BINS, HIST_BINS],
        [0, 180, 0, 256, 0, 256],
    )
    cv2.normalize(hist, hist, alpha=1.0, beta=0.0, norm_type=cv2.NORM_L1)
    return FrameSignature(gray=gray, hist=hist.flatten())


def compare_frames(frame_a: FrameSignature | np.ndarray, frame_b: FrameSignature | np.ndarray) -> float:
    """Return a similarity *distance* between two frames.

    The score is a weighted combination of normalized grayscale mean absolute
    difference and histogram L1 distance. **Lower scores indicate more similar
    frames** (``0.0`` means identical).

    Args:
        frame_a: First frame, either a :class:`FrameSignature` or a BGR frame.
        frame_b: Second frame, either a :class:`FrameSignature` or a BGR frame.

    Returns:
        A non-negative similarity distance.
    """

    sig_a = frame_a if isinstance(frame_a, FrameSignature) else frame_signature(frame_a)
    sig_b = frame_b if isinstance(frame_b, FrameSignature) else frame_signature(frame_b)

    if sig_a.gray.shape != sig_b.gray.shape:
        h = min(sig_a.gray.shape[0], sig_b.gray.shape[0])
        w = min(sig_a.gray.shape[1], sig_b.gray.shape[1])
        gray_a = sig_a.gray[:h, :w]
        gray_b = sig_b.gray[:h, :w]
    else:
        gray_a, gray_b = sig_a.gray, sig_b.gray

    gray_diff = float(np.mean(np.abs(gray_a - gray_b))) / 255.0
    hist_diff = float(np.sum(np.abs(sig_a.hist - sig_b.hist))) * 0.5
    return 0.6 * gray_diff + 0.4 * hist_diff


def _compute_all_signatures(video_path: str | Path) -> tuple[list[FrameSignature], float, int]:
    """Compute :class:`FrameSignature` for every frame in ``video_path``.

    Returns:
        A tuple ``(signatures, fps, total_frames)``.
    """

    cap = _open_capture(video_path)
    fps = _read_fps(cap)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()

    signatures: list[FrameSignature] = []
    iterator = read_video_frames(video_path)
    if total > 0:
        iterator = tqdm(iterator, total=total, desc="Analyzing frames", unit="f", leave=False)
    for _, frame in iterator:
        signatures.append(frame_signature(frame))
    if not signatures:
        raise IOError(f"Video tidak punya frame yang bisa dibaca: {video_path}")
    return signatures, fps, len(signatures)


def find_best_loop_points(
    video_path: str | Path,
    min_loop_sec: float = DEFAULT_MIN_LOOP_SEC,
    search_step: int = DEFAULT_SEARCH_STEP,
    window_sec: float = DEFAULT_WINDOW_SEC,
) -> LoopInfo:
    """Search ``video_path`` for the best ``(start_frame, end_frame)`` loop pair.

    Candidate start frames are drawn from the first ``window_sec`` of the clip
    and candidate end frames from the last ``window_sec``. For each pair we
    compute :func:`compare_frames` between the start and the frame *immediately
    following* the end frame (i.e. the frame that would visually follow in the
    loop). The pair with the lowest score wins.

    Args:
        video_path: Path to the source video.
        min_loop_sec: Minimum allowed duration of the resulting loop segment.
        search_step: Frame stride used while iterating start/end candidates.
            Must be ``>= 1``.
        window_sec: Width of the start/end search windows in seconds.

    Returns:
        A :class:`LoopInfo` dict describing the chosen loop.

    Raises:
        IOError: If the video cannot be read.
        ValueError: If the clip is too short for the requested ``min_loop_sec``.
    """

    if search_step < 1:
        search_step = 1

    signatures, fps, total_frames = _compute_all_signatures(video_path)

    min_loop_frames = max(1, int(round(min_loop_sec * fps)))
    window_frames = max(1, int(round(window_sec * fps)))

    if total_frames < min_loop_frames + 2:
        raise ValueError(
            f"Video terlalu pendek untuk loop {min_loop_sec:.2f}s "
            f"(total {total_frames} frame, butuh minimal {min_loop_frames + 2})."
        )

    start_max = min(window_frames, total_frames - min_loop_frames - 1)
    start_candidates = list(range(0, max(1, start_max + 1), search_step))
    if 0 not in start_candidates:
        start_candidates.insert(0, 0)

    end_lo = max(min_loop_frames, total_frames - window_frames - 1)
    end_hi = total_frames - 2
    if end_hi < end_lo:
        end_lo, end_hi = end_hi, end_lo
    end_candidates = list(range(end_lo, end_hi + 1, search_step))
    if end_hi not in end_candidates:
        end_candidates.append(end_hi)

    best_score = float("inf")
    best_pair: tuple[int, int] | None = None

    progress = tqdm(
        total=len(start_candidates) * len(end_candidates),
        desc="Scoring loop points",
        unit="pair",
        leave=False,
    )
    try:
        for s in start_candidates:
            sig_s = signatures[s]
            for e in end_candidates:
                if e - s < min_loop_frames:
                    progress.update(1)
                    continue
                next_idx = min(e + 1, total_frames - 1)
                score = compare_frames(sig_s, signatures[next_idx])
                if score < best_score:
                    best_score = score
                    best_pair = (s, e)
                progress.update(1)
    finally:
        progress.close()

    if best_pair is None:
        best_pair = (0, total_frames - 1)
        best_score = compare_frames(signatures[0], signatures[-1])

    start_frame, end_frame = best_pair
    loop_frames = end_frame - start_frame + 1
    return LoopInfo(
        start_frame=int(start_frame),
        end_frame=int(end_frame),
        start_sec=float(start_frame / fps),
        end_sec=float((end_frame + 1) / fps),
        loop_sec=float(loop_frames / fps),
        score=float(best_score),
        fps=float(fps),
        total_frames=int(total_frames),
    )
