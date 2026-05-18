"""Default configuration values for ASMR Seamless Loop Maker."""

from __future__ import annotations

from pathlib import Path

SUPPORTED_VIDEO_EXTENSIONS: tuple[str, ...] = (".mp4", ".mov", ".mkv", ".avi")
"""Video file extensions accepted by the application (lowercase, with leading dot)."""

DEFAULT_FPS: float = 30.0
"""Fallback FPS used when a source video does not expose a usable frame rate."""

DEFAULT_TARGET_HOURS: float = 1.0
"""Default total duration of the rendered ASMR loop, in hours."""

DEFAULT_CROSSFADE_SEC: float = 0.8
"""Default crossfade duration between consecutive loop segments, in seconds."""

DEFAULT_MIN_LOOP_SEC: float = 2.0
"""Minimum duration of a single loop segment, in seconds."""

DEFAULT_SEARCH_STEP: int = 2
"""Frame step used while scanning for candidate start/end pairs."""

DEFAULT_WINDOW_SEC: float = 1.5
"""Time window (seconds) around the end of the clip to search for the best end frame."""

ANALYSIS_RESIZE_WIDTH: int = 160
"""Width that frames are downscaled to before computing similarity signatures."""

HIST_BINS: int = 32
"""Number of bins per HSV channel used for color histogram similarity."""

DEFAULT_VIDEO_CODEC: str = "mp4v"
"""FourCC code used by OpenCV's VideoWriter for the intermediate render."""

FFMPEG_VIDEO_CODEC: str = "libx264"
"""Final video codec used when muxing the output MP4 with FFmpeg."""

FFMPEG_AUDIO_CODEC: str = "aac"
"""Final audio codec used when muxing the output MP4 with FFmpeg."""

FFMPEG_AUDIO_BITRATE: str = "192k"
"""Audio bitrate used when re-encoding the final audio track with FFmpeg."""

AUDIO_SAMPLE_RATE: int = 48000
"""Sample rate for the extracted/looped WAV audio track."""

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
"""Absolute path to the ``asmr-loop-maker`` project root."""

DEFAULT_INPUT_DIR: Path = REPO_ROOT / "input"
"""Default directory scanned in batch mode when none is supplied."""

DEFAULT_OUTPUT_DIR: Path = REPO_ROOT / "output"
"""Default directory where rendered videos are written."""

DEFAULT_REPORTS_DIR: Path = REPO_ROOT / "reports"
"""Default directory where batch CSV reports are written."""

OUTPUT_SUFFIX: str = "_asmr_loop"
"""Suffix appended to source filenames when generating the output filename."""

OUTPUT_EXTENSION: str = ".mp4"
"""Extension used for the final muxed output file."""
