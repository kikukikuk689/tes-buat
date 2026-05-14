"""FFmpeg detection and online installer."""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


# Where we install a local FFmpeg copy if user clicks "Install FFmpeg".
def local_ffmpeg_dir() -> Path:
    base = Path.home() / ".verticlip" / "ffmpeg"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _exe_name(name: str) -> str:
    return f"{name}.exe" if platform.system() == "Windows" else name


def _bundled_ffmpeg() -> Optional[Path]:
    """Return path to a locally-installed ffmpeg binary, if any."""
    candidate = local_ffmpeg_dir() / "bin" / _exe_name("ffmpeg")
    return candidate if candidate.exists() else None


def find_ffmpeg() -> Optional[str]:
    """Return path to ffmpeg binary or None."""
    bundled = _bundled_ffmpeg()
    if bundled is not None:
        return str(bundled)
    found = shutil.which("ffmpeg")
    return found


def find_ffprobe() -> Optional[str]:
    bundled_dir = local_ffmpeg_dir() / "bin"
    candidate = bundled_dir / _exe_name("ffprobe")
    if candidate.exists():
        return str(candidate)
    return shutil.which("ffprobe")


@dataclass
class FFmpegStatus:
    available: bool
    path: Optional[str]
    version: Optional[str]
    source: str  # "system", "bundled", "missing"


def probe_ffmpeg() -> FFmpegStatus:
    path = find_ffmpeg()
    if not path:
        return FFmpegStatus(False, None, None, "missing")
    bundled = _bundled_ffmpeg()
    source = "bundled" if (bundled and str(bundled) == path) else "system"
    try:
        out = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        first_line = (out.stdout or out.stderr).splitlines()[0] if out.stdout or out.stderr else ""
        version = first_line.strip() or None
    except Exception:
        version = None
    return FFmpegStatus(True, path, version, source)


# ---- Online installer ---------------------------------------------------

WINDOWS_FFMPEG_URL = (
    "https://github.com/GyanD/codexffmpeg/releases/latest/download/"
    "ffmpeg-release-essentials.zip"
)


ProgressCb = Callable[[int, int, str], None]  # bytes_done, bytes_total, msg


def _download(url: str, dest: Path, progress: Optional[ProgressCb] = None) -> None:
    """Download a URL to ``dest`` with optional progress callback."""
    import requests  # local import so this module is importable without requests

    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length") or 0)
        done = 0
        with open(dest, "wb") as fp:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                fp.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total, f"Downloading FFmpeg ... {done // 1024} KB")


def install_ffmpeg_online(progress: Optional[ProgressCb] = None) -> Path:
    """
    Download a self-contained FFmpeg build into ``~/.verticlip/ffmpeg/``.

    Currently fully supported on Windows (gyan.dev essentials build).
    On Linux/macOS we direct the user to the package manager because
    unsigned static builds vary widely; an exception is raised so the
    UI can surface a helpful message.
    """
    system = platform.system()
    target_dir = local_ffmpeg_dir()
    bin_dir = target_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)

    if system == "Windows":
        url = WINDOWS_FFMPEG_URL
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "ffmpeg.zip"
            if progress:
                progress(0, 0, "Mengunduh FFmpeg ...")
            _download(url, zip_path, progress)
            if progress:
                progress(0, 0, "Mengekstrak FFmpeg ...")
            with zipfile.ZipFile(zip_path) as zf:
                # Extract bin/ffmpeg.exe and bin/ffprobe.exe into our bin dir.
                wanted = ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe")
                for member in zf.namelist():
                    name = os.path.basename(member)
                    if name.lower() in wanted:
                        with zf.open(member) as src, open(bin_dir / name, "wb") as dst:
                            shutil.copyfileobj(src, dst)
        if progress:
            progress(0, 0, "Selesai.")
        return bin_dir / "ffmpeg.exe"

    # Non-Windows: instruct user to use the package manager. We *could*
    # download static builds, but those introduce code-signing pain and
    # are rarely needed in dev environments. The UI catches this error.
    raise RuntimeError(
        "Auto-install hanya didukung di Windows.\n"
        "Linux  : sudo apt install ffmpeg   (atau setara di distro Anda)\n"
        "macOS  : brew install ffmpeg"
    )


# ---- ffprobe helpers ----------------------------------------------------


@dataclass
class VideoInfo:
    path: str
    width: int
    height: int
    duration: float
    fps: float
    has_audio: bool


def probe_video(path: str) -> Optional[VideoInfo]:
    ffprobe = find_ffprobe()
    if not ffprobe:
        return None
    try:
        out = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        data = json.loads(out.stdout or "{}")
    except Exception:
        return None

    streams = data.get("streams", [])
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not v_stream:
        return None

    width = int(v_stream.get("width") or 0)
    height = int(v_stream.get("height") or 0)
    fps_str = v_stream.get("avg_frame_rate") or v_stream.get("r_frame_rate") or "0/1"
    try:
        num, den = fps_str.split("/")
        fps = float(num) / float(den) if float(den) != 0 else 0.0
    except Exception:
        fps = 0.0
    try:
        duration = float(data.get("format", {}).get("duration") or 0.0)
    except Exception:
        duration = 0.0
    return VideoInfo(
        path=path,
        width=width,
        height=height,
        duration=duration,
        fps=fps,
        has_audio=a_stream is not None,
    )
