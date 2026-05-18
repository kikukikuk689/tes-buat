"""Utility helpers shared across modules."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, List, Sequence

SUPPORTED_EXTENSIONS = (".mp4", ".mov", ".mkv", ".avi")

logger = logging.getLogger("asmr_loop_maker")


def ensure_ffmpeg() -> str:
    """Return the path to ``ffmpeg`` or raise ``RuntimeError`` if missing."""

    binary = shutil.which("ffmpeg")
    if not binary:
        raise RuntimeError(
            "ffmpeg is required but was not found on PATH. "
            "Install ffmpeg before running ASMR Seamless Loop Maker."
        )
    return binary


def ensure_ffprobe() -> str:
    """Return the path to ``ffprobe`` or raise ``RuntimeError`` if missing."""

    binary = shutil.which("ffprobe")
    if not binary:
        raise RuntimeError(
            "ffprobe is required but was not found on PATH. "
            "Install ffmpeg (which ships with ffprobe) before running."
        )
    return binary


def is_supported_video(path: Path) -> bool:
    """Return ``True`` if ``path`` looks like a supported video file."""

    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


def iter_video_files(folder: Path) -> List[Path]:
    """Return a sorted list of supported videos directly inside ``folder``."""

    if not folder.exists():
        raise FileNotFoundError(f"Input folder does not exist: {folder}")
    if not folder.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {folder}")

    videos = [p for p in folder.iterdir() if is_supported_video(p)]
    videos.sort(key=lambda p: p.name.lower())
    return videos


def run_command(cmd: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess:
    """Run ``cmd`` capturing stdout/stderr and optionally raising on failure."""

    logger.debug("Running command: %s", " ".join(str(c) for c in cmd))
    result = subprocess.run(
        list(cmd),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed (exit {result.returncode}): {' '.join(str(c) for c in cmd)}\n"
            f"stderr:\n{result.stderr.strip()}"
        )
    return result


def format_duration(seconds: float) -> str:
    """Render ``seconds`` as ``HH:MM:SS.mmm`` (positive values only)."""

    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds - hours * 3600 - minutes * 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def humanise_seconds(seconds: float) -> str:
    """Render a duration in a short, human-friendly form."""

    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {secs:.0f}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes)}m {secs:.0f}s"


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def unique_path(path: Path) -> Path:
    """Return a path that does not yet exist by suffixing ``_N`` if needed."""

    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    parent = path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def join_paths(paths: Iterable[Path]) -> str:
    return ", ".join(str(p) for p in paths)
