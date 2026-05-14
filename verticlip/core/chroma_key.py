"""
Detect the dominant chroma background of an overlay video so we can
auto-pick the right keying strategy.

The detection samples the four corners (which on a clean greenscreen are
guaranteed to be background) and returns the dominant family.
"""
from __future__ import annotations

import os

import cv2
import numpy as np

from .project import OverlayKey


def detect_key(path: str) -> OverlayKey:
    """Inspect the first frame of an overlay video/image and infer the key color."""
    if not path or not os.path.exists(path):
        return OverlayKey.GREEN

    if path.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp")):
        img = cv2.imread(path, cv2.IMREAD_COLOR)
    else:
        cap = cv2.VideoCapture(path)
        ok, img = cap.read()
        cap.release()
        if not ok:
            return OverlayKey.GREEN

    if img is None or img.size == 0:
        return OverlayKey.GREEN

    h, w = img.shape[:2]
    # Sample 5%-corner patches
    s = max(2, min(h, w) // 20)
    patches = [
        img[0:s, 0:s],
        img[0:s, w - s:w],
        img[h - s:h, 0:s],
        img[h - s:h, w - s:w],
    ]
    avg_bgr = np.mean(np.concatenate([p.reshape(-1, 3) for p in patches], axis=0), axis=0)
    b, g, r = avg_bgr  # BGR
    brightness = (int(b) + int(g) + int(r)) / 3.0

    # Green dominates -> greenscreen
    if g > 100 and g > r * 1.2 and g > b * 1.2:
        return OverlayKey.GREEN
    # Near white
    if brightness > 220 and abs(r - g) < 20 and abs(g - b) < 20:
        return OverlayKey.WHITE
    # Near black
    if brightness < 30:
        return OverlayKey.BLACK
    # default
    return OverlayKey.GREEN


def ffmpeg_key_filter(key: OverlayKey, similarity: float, blend: float) -> str:
    """Return the FFmpeg filter chain that keys out the background.

    Returns a filter string operating on the overlay input.
    """
    sim = max(0.01, min(1.0, similarity))
    bld = max(0.0, min(1.0, blend))
    if key == OverlayKey.GREEN:
        return f"chromakey=color=0x00FF00:similarity={sim}:blend={bld}"
    if key == OverlayKey.WHITE:
        # lumakey: pixels with luma >= threshold become transparent
        return f"format=yuva420p,lumakey=threshold=0.85:tolerance=0.10:softness={bld}"
    if key == OverlayKey.BLACK:
        return f"format=yuva420p,lumakey=threshold=0.10:tolerance=0.10:softness={bld}"
    # AUTO falls back to GREEN here; the caller is expected to resolve AUTO
    # ahead of time using detect_key().
    return f"chromakey=color=0x00FF00:similarity={sim}:blend={bld}"
