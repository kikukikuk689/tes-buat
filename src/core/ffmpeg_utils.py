"""Deteksi FFmpeg & installer online."""
from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import threading
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ..utils.logger import get_logger

_log = get_logger("ffmpeg")

_ROOT = Path(__file__).resolve().parents[2]
_LOCAL_DIR = _ROOT / "tools" / "ffmpeg"

# Cache the resolved path so repeated calls during a render are cheap
_FFMPEG_PATH: Optional[str] = None
_FFPROBE_PATH: Optional[str] = None


def _candidate_local_binaries() -> list[Path]:
    bins: list[Path] = []
    if not _LOCAL_DIR.exists():
        return bins
    # Walk a few levels deep
    for p in _LOCAL_DIR.rglob("*"):
        if p.is_file() and p.stem.lower() == "ffmpeg":
            bins.append(p)
    return bins


def _local_ffmpeg() -> Optional[str]:
    """Return path to bundled ffmpeg if present."""
    for p in _candidate_local_binaries():
        if os.name == "nt" and p.suffix.lower() != ".exe":
            continue
        if os.access(p, os.X_OK) or os.name == "nt":
            return str(p)
    return None


def find_ffmpeg() -> Optional[str]:
    global _FFMPEG_PATH
    if _FFMPEG_PATH and Path(_FFMPEG_PATH).exists():
        return _FFMPEG_PATH
    local = _local_ffmpeg()
    if local:
        _FFMPEG_PATH = local
        return local
    found = shutil.which("ffmpeg")
    if found:
        _FFMPEG_PATH = found
        return found
    return None


def find_ffprobe() -> Optional[str]:
    global _FFPROBE_PATH
    if _FFPROBE_PATH and Path(_FFPROBE_PATH).exists():
        return _FFPROBE_PATH
    if _LOCAL_DIR.exists():
        for p in _LOCAL_DIR.rglob("*"):
            if p.is_file() and p.stem.lower() == "ffprobe":
                if os.name == "nt" and p.suffix.lower() != ".exe":
                    continue
                _FFPROBE_PATH = str(p)
                return str(p)
    found = shutil.which("ffprobe")
    if found:
        _FFPROBE_PATH = found
        return found
    return None


def ffmpeg_version() -> Optional[str]:
    p = find_ffmpeg()
    if not p:
        return None
    try:
        out = subprocess.check_output([p, "-version"], stderr=subprocess.STDOUT, text=True)
        return out.splitlines()[0]
    except (OSError, subprocess.SubprocessError):
        return None


@dataclass
class FFmpegStatus:
    available: bool
    path: Optional[str]
    version: Optional[str]


def status() -> FFmpegStatus:
    p = find_ffmpeg()
    if not p:
        return FFmpegStatus(False, None, None)
    return FFmpegStatus(True, p, ffmpeg_version())


# --------- Online installer ----------

_WIN_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
_LINUX_URL = "https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz"
# macOS: use evermeet
_MAC_URL_FFMPEG = "https://evermeet.cx/ffmpeg/getrelease/zip"
_MAC_URL_FFPROBE = "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip"


def _download(url: str, dest: Path, progress: Optional[Callable[[int, int], None]] = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _log.info("Downloading %s ...", url)
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
        total = int(resp.headers.get("Content-Length") or 0)
        read = 0
        chunk = 1024 * 256
        with open(dest, "wb") as f:
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                f.write(buf)
                read += len(buf)
                if progress:
                    try:
                        progress(read, total)
                    except Exception:  # noqa: BLE001
                        pass
    _log.info("Downloaded -> %s (%.1f MiB)", dest.name, dest.stat().st_size / 1048576)


def _extract(archive: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(out_dir)
    elif archive.name.endswith(".tar.xz") or archive.suffix == ".xz":
        with tarfile.open(archive, "r:xz") as t:
            t.extractall(out_dir)
    elif archive.name.endswith(".tar.gz") or archive.suffix in {".tgz", ".gz"}:
        with tarfile.open(archive, "r:gz") as t:
            t.extractall(out_dir)
    else:
        raise RuntimeError(f"Format arsip tidak dikenal: {archive.name}")


def install_online(progress: Optional[Callable[[int, int], None]] = None,
                   status_cb: Optional[Callable[[str], None]] = None) -> bool:
    """Download & install FFmpeg ke folder lokal `tools/ffmpeg`."""
    def _say(msg: str) -> None:
        _log.info(msg)
        if status_cb:
            try:
                status_cb(msg)
            except Exception:  # noqa: BLE001
                pass

    system = platform.system().lower()
    _LOCAL_DIR.mkdir(parents=True, exist_ok=True)

    try:
        if system == "windows":
            archive = _LOCAL_DIR / "ffmpeg.zip"
            _say("Mengunduh FFmpeg untuk Windows ...")
            _download(_WIN_URL, archive, progress)
            _say("Mengekstrak ...")
            _extract(archive, _LOCAL_DIR)
            archive.unlink(missing_ok=True)
        elif system == "linux":
            archive = _LOCAL_DIR / "ffmpeg.tar.xz"
            _say("Mengunduh FFmpeg untuk Linux ...")
            _download(_LINUX_URL, archive, progress)
            _say("Mengekstrak ...")
            _extract(archive, _LOCAL_DIR)
            archive.unlink(missing_ok=True)
        elif system == "darwin":
            for label, url in (("ffmpeg", _MAC_URL_FFMPEG), ("ffprobe", _MAC_URL_FFPROBE)):
                archive = _LOCAL_DIR / f"{label}.zip"
                _say(f"Mengunduh {label} untuk macOS ...")
                _download(url, archive, progress)
                _extract(archive, _LOCAL_DIR)
                archive.unlink(missing_ok=True)
        else:
            _say(f"Sistem tidak dikenal: {system}")
            return False

        # Mark executable
        for p in _LOCAL_DIR.rglob("*"):
            if p.is_file() and p.stem.lower() in {"ffmpeg", "ffprobe"}:
                try:
                    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                except OSError:
                    pass

        global _FFMPEG_PATH, _FFPROBE_PATH
        _FFMPEG_PATH = None
        _FFPROBE_PATH = None
        if find_ffmpeg():
            _say("FFmpeg terinstall! " + (ffmpeg_version() or ""))
            return True
        _say("Install selesai tapi binary tidak ditemukan. Cek folder tools/ffmpeg manual.")
        return False
    except Exception as e:  # noqa: BLE001
        _log.exception("Gagal install FFmpeg")
        if status_cb:
            try:
                status_cb(f"Gagal install: {e}")
            except Exception:  # noqa: BLE001
                pass
        return False


def install_online_async(on_done: Callable[[bool], None],
                         progress: Optional[Callable[[int, int], None]] = None,
                         status_cb: Optional[Callable[[str], None]] = None) -> threading.Thread:
    def _run() -> None:
        ok = install_online(progress, status_cb)
        on_done(ok)

    th = threading.Thread(target=_run, name="ffmpeg-installer", daemon=True)
    th.start()
    return th


# --------- Media probing ----------

def probe_duration(media_path: str | Path) -> Optional[float]:
    """Probe durasi (detik) audio/video via ffprobe atau ffmpeg fallback."""
    media_path = str(media_path)
    pp = find_ffprobe()
    if pp:
        try:
            out = subprocess.check_output(
                [pp, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", media_path],
                text=True,
                stderr=subprocess.STDOUT,
            ).strip()
            return float(out)
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    # ffmpeg fallback: parse stderr for Duration: hh:mm:ss.xx
    fp = find_ffmpeg()
    if fp:
        try:
            res = subprocess.run([fp, "-i", media_path],
                                 capture_output=True, text=True, check=False)
            for line in (res.stderr or "").splitlines():
                line = line.strip()
                if line.lower().startswith("duration:"):
                    seg = line.split(",")[0].split(":", 1)[1].strip()
                    h, m, s = seg.split(":")
                    return int(h) * 3600 + int(m) * 60 + float(s)
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def encoder_choices() -> list[str]:
    """Daftar encoder video umum yang bisa dipilih."""
    return ["libx264", "h264_nvenc", "h264_qsv", "h264_amf", "libx265", "mpeg4"]
