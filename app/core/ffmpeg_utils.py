"""FFmpeg detection and online installation helpers."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional, Tuple


# Default install location: <app-root>/bin/ffmpeg(.exe)
APP_ROOT = Path(__file__).resolve().parent.parent.parent
BUNDLED_BIN = APP_ROOT / "bin"


def _candidate_paths():
    """Return paths we should check for an existing ffmpeg binary."""
    name = "ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg"
    yield shutil.which(name)
    yield str(BUNDLED_BIN / name)


def ffmpeg_path() -> Optional[str]:
    """Return a usable ffmpeg path, or None."""
    for c in _candidate_paths():
        if c and Path(c).exists():
            try:
                subprocess.run([c, "-version"], capture_output=True, check=True, timeout=5, stdin=subprocess.DEVNULL)
                return c
            except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
                continue
    return None


def ffprobe_path() -> Optional[str]:
    name = "ffprobe.exe" if sys.platform.startswith("win") else "ffprobe"
    p = shutil.which(name)
    if p:
        return p
    bundled = BUNDLED_BIN / name
    if bundled.exists():
        return str(bundled)
    return None


def status() -> Tuple[bool, str]:
    p = ffmpeg_path()
    if not p:
        return False, "FFmpeg tidak ditemukan."
    try:
        out = subprocess.run([p, "-version"], capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL).stdout
        first = out.splitlines()[0] if out else "unknown"
        return True, f"OK: {p}\n{first}"
    except Exception as exc:  # pragma: no cover
        return False, f"FFmpeg error: {exc}"


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------

# Static builds, no auth required.
DOWNLOAD_URLS = {
    "Windows": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "Linux": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
    "Darwin": "https://evermeet.cx/ffmpeg/getrelease/zip",
}


def install_ffmpeg(progress: Optional[Callable[[str, float], None]] = None) -> Tuple[bool, str]:
    """Download a static ffmpeg build into ``BUNDLED_BIN``.

    Returns ``(success, message)``.  Reports progress via the optional
    ``progress(text, ratio)`` callback (``ratio`` in [0, 1] or ``-1``).
    """
    sys_name = platform.system()
    url = DOWNLOAD_URLS.get(sys_name)
    if not url:
        return False, f"Belum support OS: {sys_name}"

    BUNDLED_BIN.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / "ffmpeg_archive"

        def _report(text: str, ratio: float):
            if progress:
                progress(text, ratio)

        _report(f"Mengunduh dari {url}", -1)
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0)) or -1
                with open(archive, "wb") as f:
                    downloaded = 0
                    while True:
                        chunk = resp.read(64 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            _report(f"Unduh {downloaded/1e6:.1f}/{total/1e6:.1f} MB",
                                    downloaded / total)
        except Exception as exc:
            return False, f"Gagal mengunduh: {exc}"

        _report("Mengekstrak arsip...", 0.95)
        try:
            extracted = tmp_path / "extracted"
            extracted.mkdir(exist_ok=True)
            if str(archive).endswith(".zip") or sys_name in ("Windows", "Darwin"):
                with zipfile.ZipFile(archive) as zf:
                    zf.extractall(extracted)
            else:
                with tarfile.open(archive, "r:xz") as tf:
                    tf.extractall(extracted)
        except Exception as exc:
            return False, f"Gagal ekstrak: {exc}"

        # Find ffmpeg/ffprobe binaries inside the extracted tree.
        bin_name = "ffmpeg.exe" if sys_name == "Windows" else "ffmpeg"
        probe_name = "ffprobe.exe" if sys_name == "Windows" else "ffprobe"
        found_ffmpeg = None
        found_ffprobe = None
        for p in extracted.rglob("*"):
            if p.is_file():
                if p.name.lower() == bin_name.lower():
                    found_ffmpeg = p
                elif p.name.lower() == probe_name.lower():
                    found_ffprobe = p
            if found_ffmpeg and found_ffprobe:
                break
        if not found_ffmpeg:
            return False, "ffmpeg tidak ditemukan dalam arsip"

        for src, dst_name in [(found_ffmpeg, bin_name)] + (
                [(found_ffprobe, probe_name)] if found_ffprobe else []):
            dst = BUNDLED_BIN / dst_name
            shutil.copy2(src, dst)
            if sys_name != "Windows":
                os.chmod(dst, 0o755)

        _report("Selesai.", 1.0)
        return True, f"Terpasang di {BUNDLED_BIN}"


def get_ffmpeg_command_or_install_warning() -> str:
    p = ffmpeg_path()
    if p:
        return p
    raise RuntimeError("FFmpeg tidak tersedia. Klik tombol Install FFmpeg di GUI.")
