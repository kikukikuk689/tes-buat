"""Video analysis helpers for finding the best seamless loop segment.

The analyzer reads every frame of the input video, downscales it for cheap
comparison, and scores candidate ``(start_frame, end_frame)`` pairs using:

* mean absolute grayscale difference (lower = more similar)
* HSV color histogram correlation (higher = more similar)

The final loop score is a weighted blend of both signals plus a small bonus
for longer segments (so the chosen loop has meaningful content rather than
collapsing to a 1-frame window).
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

logger = logging.getLogger("asmr_loop_maker.analyzer")

# Resolution used for cheap frame comparisons.  Small enough to score
# thousands of candidate pairs quickly, large enough to remain meaningful.
_ANALYSIS_WIDTH = 160
_ANALYSIS_HEIGHT = 90

# Histogram resolution for HSV comparison.
_HIST_BINS = (16, 16)


@dataclass
class LoopAnalysis:
    """Result of analyzing a video for the best seamless loop window."""

    video_path: str
    fps: float
    total_frames: int
    duration: float
    start_frame: int
    end_frame: int
    start_time: float
    end_time: float
    loop_duration: float
    score: float
    grayscale_score: float
    histogram_score: float
    duration_score: float

    def to_dict(self) -> dict:
        return asdict(self)


def _read_frames(path: Path) -> tuple[List[np.ndarray], List[np.ndarray], float]:
    """Return (gray frames, HSV histograms, fps) for the entire video."""

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    if fps <= 0:
        fps = 30.0
        logger.warning("FPS metadata missing for %s; assuming 30 fps", path)

    gray_frames: List[np.ndarray] = []
    hist_frames: List[np.ndarray] = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        small = cv2.resize(frame, (_ANALYSIS_WIDTH, _ANALYSIS_HEIGHT))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist(
            [hsv],
            [0, 1],
            None,
            list(_HIST_BINS),
            [0, 180, 0, 256],
        )
        cv2.normalize(hist, hist)
        gray_frames.append(gray)
        hist_frames.append(hist.flatten())
    cap.release()

    if not gray_frames:
        raise RuntimeError(f"Video has no decodable frames: {path}")
    return gray_frames, hist_frames, fps


def _candidate_indices(total: int, max_candidates: int) -> List[int]:
    """Return ``max_candidates`` evenly spaced indices in ``[0, total)``."""

    if total <= max_candidates:
        return list(range(total))
    step = total / float(max_candidates)
    return sorted({int(round(i * step)) for i in range(max_candidates)})


def analyze_video(
    video_path: str | Path,
    *,
    min_loop_seconds: float = 1.5,
    max_loop_seconds: Optional[float] = None,
    grayscale_weight: float = 0.5,
    histogram_weight: float = 0.4,
    duration_weight: float = 0.1,
    max_candidates: int = 240,
) -> LoopAnalysis:
    """Analyze ``video_path`` and return the best loop window.

    Parameters
    ----------
    video_path:
        Path to the source video.
    min_loop_seconds:
        Minimum allowed loop length.  Avoids degenerate single-frame loops.
    max_loop_seconds:
        Optional upper bound on the loop length.
    grayscale_weight, histogram_weight, duration_weight:
        Weights for the three signals contributing to the final score.  The
        function does not require them to sum to ``1`` but you typically want
        them to.
    max_candidates:
        Caps the number of candidate frames considered on each side of the
        loop to keep ``O(N^2)`` comparison cheap for longer clips.
    """

    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"Video not found: {path}")

    gray_frames, hist_frames, fps = _read_frames(path)
    total = len(gray_frames)
    duration = total / fps

    min_frames = max(1, int(round(min_loop_seconds * fps)))
    if max_loop_seconds is None:
        max_frames = total
    else:
        max_frames = max(min_frames + 1, int(round(max_loop_seconds * fps)))

    if total <= min_frames + 1:
        logger.warning(
            "Video %s is shorter than min_loop_seconds=%.2f; using full clip",
            path,
            min_loop_seconds,
        )
        start_idx = 0
        end_idx = total - 1
        gray_score = 1.0
        hist_score = 1.0
        dur_score = 1.0
        score = 1.0
        return LoopAnalysis(
            video_path=str(path),
            fps=fps,
            total_frames=total,
            duration=duration,
            start_frame=start_idx,
            end_frame=end_idx,
            start_time=start_idx / fps,
            end_time=end_idx / fps,
            loop_duration=(end_idx - start_idx) / fps,
            score=score,
            grayscale_score=gray_score,
            histogram_score=hist_score,
            duration_score=dur_score,
        )

    # Look for the loop start in the first ~40% and the loop end in the last
    # ~40% of the clip.  This bias keeps the loop meaningful and avoids
    # selecting near-identical adjacent frames.
    start_pool = _candidate_indices(max(1, int(total * 0.4)), max_candidates)
    end_pool_start = max(min_frames, int(total * 0.6))
    end_pool = _candidate_indices(total - end_pool_start, max_candidates)
    end_pool = [end_pool_start + i for i in end_pool if end_pool_start + i < total]

    best_score = -math.inf
    best_start = 0
    best_end = total - 1
    best_gray = 0.0
    best_hist = 0.0
    best_dur = 0.0

    for start in start_pool:
        gray_start = gray_frames[start].astype(np.int16)
        hist_start = hist_frames[start]
        for end in end_pool:
            gap = end - start
            if gap < min_frames or gap > max_frames:
                continue

            diff = float(
                np.mean(np.abs(gray_start - gray_frames[end].astype(np.int16)))
            )
            gray_score = float(max(0.0, 1.0 - diff / 64.0))

            hist_sim = float(
                cv2.compareHist(hist_start, hist_frames[end], cv2.HISTCMP_CORREL)
            )
            hist_score = float(max(0.0, min(1.0, (hist_sim + 1.0) / 2.0)))

            dur_score = float(min(1.0, gap / float(total)))

            score = (
                grayscale_weight * gray_score
                + histogram_weight * hist_score
                + duration_weight * dur_score
            )
            if score > best_score:
                best_score = score
                best_start = start
                best_end = end
                best_gray = gray_score
                best_hist = hist_score
                best_dur = dur_score

    return LoopAnalysis(
        video_path=str(path),
        fps=fps,
        total_frames=total,
        duration=duration,
        start_frame=best_start,
        end_frame=best_end,
        start_time=best_start / fps,
        end_time=best_end / fps,
        loop_duration=(best_end - best_start) / fps,
        score=best_score,
        grayscale_score=best_gray,
        histogram_score=best_hist,
        duration_score=best_dur,
    )
