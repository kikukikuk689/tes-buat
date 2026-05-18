"""Gameplay recorder using OpenCV.

If OpenCV (cv2) or numpy are missing at import time, the recorder reports the
problem instead of crashing -- the rest of the game still works without it.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Optional

import pygame

# Try to import OpenCV / numpy. If either fails we fall back to a no-op
# recorder that surfaces a friendly error to the UI.
try:
    import cv2  # type: ignore
    import numpy as np  # type: ignore

    RECORDING_AVAILABLE = True
    RECORDING_ERROR: Optional[str] = None
except Exception as exc:  # pragma: no cover - depends on environment
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]
    RECORDING_AVAILABLE = False
    RECORDING_ERROR = str(exc)


class Recorder:
    """Captures pygame frames and writes them to an mp4/avi via OpenCV."""

    def __init__(self, output_dir: Path, fps: int = 60) -> None:
        self.output_dir = Path(output_dir)
        self.fps = fps
        self.writer = None  # cv2.VideoWriter when recording
        self.filename: Optional[str] = None
        self.error: Optional[str] = None

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------
    def is_available(self) -> bool:
        return RECORDING_AVAILABLE

    def availability_message(self) -> str:
        if RECORDING_AVAILABLE:
            return "Recording ready (OpenCV detected)."
        return (
            "Recording unavailable: "
            + (RECORDING_ERROR or "opencv-python is not installed")
        )

    def is_recording(self) -> bool:
        return self.writer is not None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self, surface: pygame.Surface) -> bool:
        """Open a new video file and start writing frames.

        Returns True on success, False if recording can't be started. In the
        failure case ``self.error`` describes what went wrong.
        """
        if not RECORDING_AVAILABLE:
            self.error = (
                "OpenCV is not installed. Run: pip install opencv-python"
            )
            return False
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self.filename = str(
                self.output_dir / f"snake_record_{timestamp}.mp4"
            )
            w, h = surface.get_width(), surface.get_height()

            # mp4v works on most installations of opencv-python.
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(self.filename, fourcc, self.fps, (w, h))

            # Fall back to MJPG / .avi if the mp4 codec isn't available.
            if not writer.isOpened():
                self.filename = self.filename.replace(".mp4", ".avi")
                fourcc = cv2.VideoWriter_fourcc(*"MJPG")
                writer = cv2.VideoWriter(self.filename, fourcc, self.fps, (w, h))

            if not writer.isOpened():
                self.error = "Failed to open a video writer (codec missing?)."
                return False

            self.writer = writer
            self.error = None
            return True
        except Exception as exc:  # pragma: no cover - environment dependent
            self.error = f"Recorder error: {exc}"
            self.writer = None
            return False

    def write_frame(self, surface: pygame.Surface) -> None:
        """Send the current screen contents to the video writer."""
        if not self.writer or np is None or cv2 is None:
            return
        try:
            # pygame returns the buffer as (width, height, 3) RGB, but OpenCV
            # expects (height, width, 3) BGR -- so we transpose and flip channels.
            arr = pygame.surfarray.array3d(surface)
            arr = np.transpose(arr, (1, 0, 2))
            arr = arr[:, :, ::-1]
            self.writer.write(arr)
        except Exception as exc:  # pragma: no cover - extremely defensive
            self.error = f"Recording write failed: {exc}"

    def stop(self) -> Optional[str]:
        """Close the writer and return the filename of the saved video."""
        if self.writer:
            try:
                self.writer.release()
            except Exception:
                pass
            self.writer = None
        path = self.filename
        self.filename = None
        return path
