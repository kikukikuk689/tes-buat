"""Generic helper utilities used across the application."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from .config import SUPPORTED_VIDEO_EXTENSIONS


class FFmpegNotFoundError(RuntimeError):
    """Raised when the FFmpeg binary cannot be located on PATH."""


def ensure_dir(path: str | Path) -> Path:
    """Create ``path`` (and parents) if it does not exist and return it as a ``Path``.

    Args:
        path: Directory to create.

    Returns:
        The resolved :class:`~pathlib.Path` instance for ``path``.
    """

    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def is_video_file(path: str | Path) -> bool:
    """Return ``True`` when ``path`` points at a file with a supported video extension.

    Args:
        path: Filesystem path to inspect.

    Returns:
        ``True`` if the file exists and its extension is in
        :data:`~app.config.SUPPORTED_VIDEO_EXTENSIONS`.
    """

    p = Path(path)
    if not p.is_file():
        return False
    return p.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str) -> str:
    """Sanitize ``name`` so it can be safely used as a filename on any OS.

    Replaces runs of disallowed characters with a single underscore and trims
    leading/trailing separators. Empty results fall back to ``"output"``.

    Args:
        name: Raw filename or stem to sanitize.

    Returns:
        A sanitized filename safe for use across Windows, macOS and Linux.
    """

    cleaned = _SAFE_FILENAME_RE.sub("_", name).strip("._-")
    return cleaned or "output"


def run_command(cmd: Sequence[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run an external command and return the completed process.

    The command is executed without invoking a shell. ``stdout`` and ``stderr``
    are captured as text so callers can inspect them on failure.

    Args:
        cmd: The command tokens to execute.
        check: When ``True`` (the default), a non-zero exit status raises
            :class:`subprocess.CalledProcessError`.

    Returns:
        The :class:`subprocess.CompletedProcess` describing the run.

    Raises:
        subprocess.CalledProcessError: If the command exits non-zero and
            ``check`` is ``True``.
    """

    return subprocess.run(
        list(cmd),
        check=check,
        capture_output=True,
        text=True,
    )


def find_ffmpeg() -> str:
    """Locate the ``ffmpeg`` executable.

    Returns:
        Absolute path to the ``ffmpeg`` binary.

    Raises:
        FFmpegNotFoundError: If the binary is not available on ``PATH``.
    """

    exe = shutil.which("ffmpeg")
    if not exe:
        raise FFmpegNotFoundError(
            "FFmpeg belum terinstall. Install FFmpeg dan pastikan bisa dipanggil dari terminal."
        )
    return exe


def find_ffprobe() -> str:
    """Locate the ``ffprobe`` executable.

    Returns:
        Absolute path to the ``ffprobe`` binary.

    Raises:
        FFmpegNotFoundError: If the binary is not available on ``PATH``.
    """

    exe = shutil.which("ffprobe")
    if not exe:
        raise FFmpegNotFoundError(
            "FFmpeg belum terinstall. Install FFmpeg dan pastikan bisa dipanggil dari terminal."
        )
    return exe


def ensure_ffmpeg_available() -> None:
    """Raise :class:`FFmpegNotFoundError` if FFmpeg is not on ``PATH``."""

    find_ffmpeg()


def list_videos_in_dir(directory: str | Path) -> list[Path]:
    """Return all supported video files directly inside ``directory``.

    The listing is non-recursive and sorted by filename for stable batch order.

    Args:
        directory: Directory to scan.

    Returns:
        A list of absolute paths to supported video files.
    """

    d = Path(directory)
    if not d.is_dir():
        return []
    return sorted(p.resolve() for p in d.iterdir() if is_video_file(p))


def build_output_path(input_video: str | Path, output_dir: str | Path, suffix: str, extension: str) -> Path:
    """Build the output path for a rendered video.

    Args:
        input_video: Source video path; only its stem is used.
        output_dir: Directory that will contain the rendered file.
        suffix: Suffix appended to the sanitized stem (e.g. ``"_asmr_loop"``).
        extension: File extension including the leading dot.

    Returns:
        Absolute :class:`~pathlib.Path` for the desired output file.
    """

    out_dir = ensure_dir(output_dir)
    stem = safe_filename(Path(input_video).stem)
    return out_dir / f"{stem}{suffix}{extension}"
