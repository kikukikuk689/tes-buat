"""FFmpeg detection / installation / encoder discovery.

The manager exposes the following capabilities:

* Detect a usable ``ffmpeg`` binary on PATH or under the user data
  directory.
* Detect the bundled / installed version and the list of available
  encoders.
* Download an official static build (Windows / Linux / macOS) on demand
  with progress reporting and verify the resulting binary.
* Repair / update the installed FFmpeg copy.

The download URLs point at the well-known static distributions:

* Windows: https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
* Linux  : https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
* macOS  : https://evermeet.cx/ffmpeg/ffmpeg.zip (universal)

All downloads happen through ``requests`` with a streaming response so
the UI can report progress.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import requests

from ..core.events import Topics, event_bus
from ..core.exceptions import FFmpegError
from ..core.logger import get_logger
from ..core.paths import paths

DOWNLOAD_URLS = {
    "win32": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "linux": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
    "darwin": "https://evermeet.cx/ffmpeg/ffmpeg.zip",
}


class FFmpegState(str, Enum):
    UNKNOWN = "unknown"
    READY = "ready"
    MISSING = "missing"
    INSTALLING = "installing"
    ERROR = "error"


@dataclass
class FFmpegInfo:
    state: FFmpegState = FFmpegState.UNKNOWN
    binary: str = ""
    ffprobe: str = ""
    version: str = ""
    encoders: list[str] = field(default_factory=list)
    decoders: list[str] = field(default_factory=list)
    formats: list[str] = field(default_factory=list)
    last_error: str = ""

    @property
    def hardware_encoders(self) -> list[str]:
        keys = ("nvenc", "qsv", "amf", "videotoolbox", "vaapi")
        return [e for e in self.encoders if any(k in e for k in keys)]


class FFmpegManager:
    """Singleton-ish manager that mediates all FFmpeg related operations."""

    def __init__(self) -> None:
        self._log = get_logger("ffmpeg.manager")
        self._info = FFmpegInfo()
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def info(self) -> FFmpegInfo:
        return self._info

    @property
    def is_ready(self) -> bool:
        return self._info.state == FFmpegState.READY

    def refresh(self) -> FFmpegInfo:
        """Re-run discovery and update internal state."""
        with self._lock:
            binary = self._find_binary("ffmpeg")
            probe = self._find_binary("ffprobe")
            if not binary:
                self._info = FFmpegInfo(state=FFmpegState.MISSING)
            else:
                version, encoders, formats = self._inspect(binary)
                self._info = FFmpegInfo(
                    state=FFmpegState.READY,
                    binary=binary,
                    ffprobe=probe or binary,
                    version=version,
                    encoders=encoders,
                    decoders=[],
                    formats=formats,
                )
            event_bus.publish(
                Topics.FFMPEG_STATE,
                {
                    "state": self._info.state.value,
                    "version": self._info.version,
                    "binary": self._info.binary,
                },
            )
            return self._info

    def install(self, progress: Callable[[float, str], None] | None = None) -> FFmpegInfo:
        """Download + extract FFmpeg into the user data directory.

        ``progress(percent, message)`` is called repeatedly so the UI can
        animate a progress bar.  Raises :class:`FFmpegError` on failure.
        """
        with self._lock:
            self._info = FFmpegInfo(state=FFmpegState.INSTALLING)
            event_bus.publish(Topics.FFMPEG_STATE, {"state": self._info.state.value})
        try:
            target = self._download_and_extract(progress=progress or (lambda *_: None))
            self._set_executable(target)
            return self.refresh()
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._info = FFmpegInfo(
                    state=FFmpegState.ERROR, last_error=str(exc)
                )
            event_bus.publish(
                Topics.FFMPEG_STATE,
                {"state": self._info.state.value, "error": str(exc)},
            )
            raise FFmpegError(str(exc)) from exc

    def repair(self, progress: Callable[[float, str], None] | None = None) -> FFmpegInfo:
        """Force a re-download, replacing any locally installed binaries."""
        target_dir = paths.ffmpeg_dir
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        target_dir.mkdir(parents=True, exist_ok=True)
        return self.install(progress=progress)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    def _find_binary(self, name: str) -> str:
        # 1. user data dir (preferred so updates stick)
        candidates: list[Path] = []
        exe = name + (".exe" if sys.platform == "win32" else "")
        candidates.append(paths.ffmpeg_dir / exe)
        candidates.extend(paths.ffmpeg_dir.rglob(exe))
        for c in candidates:
            if c.is_file() and os.access(c, os.X_OK):
                return str(c)
        # 2. PATH
        which = shutil.which(name)
        return which or ""

    def _inspect(self, binary: str) -> tuple[str, list[str], list[str]]:
        try:
            version = subprocess.check_output(
                [binary, "-version"], text=True, stderr=subprocess.STDOUT, timeout=10
            ).splitlines()[0]
        except Exception as exc:  # noqa: BLE001
            self._log.warning("ffmpeg -version failed: %s", exc)
            version = "ffmpeg"
        encoders: list[str] = []
        formats: list[str] = []
        try:
            enc_out = subprocess.check_output(
                [binary, "-hide_banner", "-encoders"],
                text=True,
                stderr=subprocess.STDOUT,
                timeout=10,
            )
            for line in enc_out.splitlines():
                line = line.strip()
                if not line or line.startswith(("Encoders:", "------", "V", "A", "S")):
                    parts = line.split()
                    if len(parts) >= 3 and len(parts[0]) <= 7 and parts[0].startswith(
                        ("V", "A", "S")
                    ):
                        encoders.append(parts[1])
        except Exception as exc:  # noqa: BLE001
            self._log.warning("ffmpeg -encoders failed: %s", exc)
        try:
            fmt_out = subprocess.check_output(
                [binary, "-hide_banner", "-formats"],
                text=True,
                stderr=subprocess.STDOUT,
                timeout=10,
            )
            for line in fmt_out.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0] in {"D", "E", "DE"}:
                    formats.append(parts[1])
        except Exception:  # noqa: BLE001
            pass
        return version, sorted(set(encoders)), sorted(set(formats))

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------
    def _download_and_extract(self, progress: Callable[[float, str], None]) -> Path:
        platform_key = "win32" if sys.platform == "win32" else (
            "darwin" if sys.platform == "darwin" else "linux"
        )
        url = DOWNLOAD_URLS.get(platform_key)
        if not url:
            raise FFmpegError(f"No download URL configured for {sys.platform}")

        progress(2.0, f"Downloading FFmpeg ({platform_key})...")
        target_dir = paths.ffmpeg_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        archive = Path(tempfile.mkstemp(prefix="ffmpeg-", suffix=Path(url).suffix or ".bin")[1])
        try:
            with requests.get(url, stream=True, timeout=60) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length") or 0)
                downloaded = 0
                with archive.open("wb") as fh:
                    for chunk in resp.iter_content(chunk_size=128 * 1024):
                        if not chunk:
                            continue
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = 2.0 + (downloaded / total) * 88.0
                            progress(pct, f"Downloading... {downloaded // 1024} KB")
            progress(92.0, "Extracting archive...")
            self._extract(archive, target_dir)
        finally:
            try:
                archive.unlink()
            except OSError:
                pass

        progress(98.0, "Verifying installation...")
        # find the binary
        binary_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        found = next(iter(target_dir.rglob(binary_name)), None)
        if found is None:
            raise FFmpegError("FFmpeg archive did not contain a usable binary")
        # Promote to ffmpeg_dir root so subsequent runs find it instantly.
        flat = target_dir / found.name
        if found.resolve() != flat.resolve():
            shutil.copy2(found, flat)
        progress(100.0, "Installation complete")
        return flat

    def _extract(self, archive: Path, dest: Path) -> None:
        suffix = "".join(archive.suffixes).lower()
        if suffix.endswith(".zip"):
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(dest)
            return
        if suffix.endswith((".tar.xz", ".tar.gz", ".tar.bz2", ".tar")):
            with tarfile.open(archive, mode="r:*") as tf:
                tf.extractall(dest, filter="data")  # type: ignore[arg-type]
            return
        # Some macOS builds ship a single bare binary
        with archive.open("rb") as src, (dest / "ffmpeg").open("wb") as dst:
            shutil.copyfileobj(src, dst)

    def _set_executable(self, binary: Path) -> None:
        if sys.platform != "win32":
            try:
                mode = binary.stat().st_mode
                binary.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            except OSError:  # pragma: no cover
                pass


_GLOBAL: FFmpegManager | None = None


def get_ffmpeg_manager() -> FFmpegManager:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = FFmpegManager()
    return _GLOBAL
