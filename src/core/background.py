"""Background frame provider.

Mendukung:
- single image (Ken Burns gentle zoom-pan)
- single video (loop)
- multi image (slideshow + crossfade)
- multi video (sequential with optional crossfade)
"""
from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from PIL import Image, ImageFilter

from ..utils.logger import get_logger
from .ffmpeg_utils import find_ffmpeg, probe_duration

_log = get_logger("background")

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


@dataclass
class BackgroundConfig:
    paths: List[str] = field(default_factory=list)
    enabled: bool = True
    per_clip_seconds: float = 6.0       # untuk slideshow / cycling
    crossfade: float = 0.8
    ken_burns: bool = True
    blur: int = 0
    dim: float = 0.30                   # 0..1, kurangi brightness supaya spectrum/lirik kebaca
    color: Tuple[int, int, int] = (8, 10, 18)  # background fallback


def is_image(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXT


def is_video(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXT


# ============================================================
# Helpers
# ============================================================

def _fit_cover(im: Image.Image, target: Tuple[int, int]) -> Image.Image:
    """Resize+crop supaya menutupi target."""
    tw, th = target
    iw, ih = im.size
    if iw == 0 or ih == 0:
        return Image.new("RGB", target, (0, 0, 0))
    scale = max(tw / iw, th / ih)
    new = (max(1, int(iw * scale + 0.5)), max(1, int(ih * scale + 0.5)))
    im = im.resize(new, Image.LANCZOS)
    # center crop
    x = (im.width - tw) // 2
    y = (im.height - th) // 2
    return im.crop((x, y, x + tw, y + th))


def _ken_burns(im: Image.Image, target: Tuple[int, int], t: float, duration: float) -> Image.Image:
    """Slow zoom-pan untuk image background."""
    tw, th = target
    if duration <= 0.01:
        return _fit_cover(im, target)
    progress = max(0.0, min(1.0, t / duration))
    # zoom dari 1.0 ke 1.08
    zoom = 1.0 + 0.08 * progress
    base = _fit_cover(im, (int(tw * zoom), int(th * zoom)))
    # slight pan: from -1% to +1%
    pan_x = int(base.width - tw) // 2 + int(math.sin(progress * math.pi) * 0.02 * base.width)
    pan_y = int(base.height - th) // 2
    pan_x = max(0, min(base.width - tw, pan_x))
    pan_y = max(0, min(base.height - th, pan_y))
    return base.crop((pan_x, pan_y, pan_x + tw, pan_y + th))


def _apply_post(im: Image.Image, cfg: BackgroundConfig) -> Image.Image:
    out = im
    if cfg.blur > 0:
        out = out.filter(ImageFilter.GaussianBlur(cfg.blur))
    if cfg.dim > 0.001:
        from PIL import ImageEnhance
        out = ImageEnhance.Brightness(out).enhance(1.0 - cfg.dim)
    return out


# ============================================================
# Video frame stream (lazy, via ffmpeg pipe)
# ============================================================

class _VideoStream:
    """Pull rawvideo frames dari satu file via ffmpeg."""

    def __init__(self, path: str, target: Tuple[int, int], fps: int):
        self.path = path
        self.target = target
        self.fps = fps
        self._proc: Optional[subprocess.Popen] = None
        self._duration = probe_duration(path) or 0.0
        self._frame_size = target[0] * target[1] * 3
        self._frame_idx = 0

    def __enter__(self) -> "_VideoStream":
        self._start()
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def _start(self) -> None:
        ff = find_ffmpeg()
        if not ff:
            raise RuntimeError("FFmpeg tidak ditemukan untuk decode background video.")
        tw, th = self.target
        # auto loop with -stream_loop -1 so we never run out
        cmd = [
            ff, "-v", "error",
            "-stream_loop", "-1",
            "-i", self.path,
            "-vf", (f"scale={tw}:{th}:force_original_aspect_ratio=increase,"
                    f"crop={tw}:{th},fps={self.fps}"),
            "-pix_fmt", "rgb24",
            "-f", "rawvideo",
            "-",
        ]
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL,
                                      bufsize=10 ** 7)

    def read(self) -> Optional[Image.Image]:
        if self._proc is None or self._proc.stdout is None:
            return None
        buf = self._proc.stdout.read(self._frame_size)
        if len(buf) < self._frame_size:
            return None
        im = Image.frombuffer("RGB", self.target, buf, "raw", "RGB", 0, 1).copy()
        self._frame_idx += 1
        return im

    def close(self) -> None:
        if self._proc is not None:
            try:
                if self._proc.stdout:
                    self._proc.stdout.close()
                self._proc.kill()
                self._proc.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                pass
            self._proc = None


# ============================================================
# Provider
# ============================================================

class BackgroundProvider:
    """Provide frame background untuk setiap timestamp."""

    def __init__(self, cfg: BackgroundConfig, target: Tuple[int, int],
                 fps: int, duration: float):
        self.cfg = cfg
        self.target = target
        self.fps = fps
        self.duration = duration

        self._paths = [p for p in cfg.paths if Path(p).exists()] if cfg.enabled else []
        self._videos: List[Tuple[int, _VideoStream]] = []
        self._image_cache: dict[str, Image.Image] = {}

        # Pre-open at most 2 video streams at a time (current + next for crossfade)
        self._active_video_idx: int = -1
        self._active_video: Optional[_VideoStream] = None

    def close(self) -> None:
        if self._active_video is not None:
            self._active_video.close()
            self._active_video = None

    def _segment_for(self, t: float) -> Tuple[int, float, float]:
        """Return (path_index, local_t, segment_duration)."""
        if not self._paths:
            return -1, 0.0, 0.0
        if len(self._paths) == 1:
            return 0, t, self.duration
        per = max(1.0, self.cfg.per_clip_seconds)
        idx = int((t // per) % len(self._paths))
        local = t - idx * per
        return idx, local, per

    def _load_image(self, path: str) -> Image.Image:
        if path in self._image_cache:
            return self._image_cache[path]
        try:
            im = Image.open(path).convert("RGB")
        except OSError as e:
            _log.warning("Background image gagal dibuka %s: %s", path, e)
            im = Image.new("RGB", self.target, self.cfg.color)
        # Pre-fit at slightly larger size for Ken Burns headroom
        tw, th = self.target
        fit = _fit_cover(im, (int(tw * 1.12), int(th * 1.12)))
        self._image_cache[path] = fit
        return fit

    def _ensure_video(self, idx: int) -> Optional[_VideoStream]:
        if idx == self._active_video_idx and self._active_video is not None:
            return self._active_video
        if self._active_video is not None:
            self._active_video.close()
            self._active_video = None
        path = self._paths[idx]
        if not is_video(path):
            return None
        try:
            v = _VideoStream(path, self.target, self.fps)
            v._start()
            self._active_video = v
            self._active_video_idx = idx
            return v
        except (OSError, RuntimeError) as e:
            _log.warning("Video background gagal: %s", e)
            return None

    def get_frame(self, t: float) -> Image.Image:
        tw, th = self.target
        cfg = self.cfg
        if not self._paths or not cfg.enabled:
            return Image.new("RGB", self.target, cfg.color)

        idx, local_t, seg_dur = self._segment_for(t)
        path = self._paths[idx]
        if is_image(path):
            im = self._load_image(path)
            if cfg.ken_burns and len(self._paths) == 1:
                im = _ken_burns(im, self.target, t, max(1.0, self.duration))
            else:
                im = _fit_cover(im, self.target)
        elif is_video(path):
            v = self._ensure_video(idx)
            if v is None:
                im = Image.new("RGB", self.target, cfg.color)
            else:
                frame = v.read()
                im = frame if frame is not None else Image.new("RGB", self.target, cfg.color)
        else:
            im = Image.new("RGB", self.target, cfg.color)

        return _apply_post(im, cfg)


# ============================================================
# Batch matching helpers
# ============================================================

def gather_media(folder: str | Path,
                 include_images: bool = True,
                 include_videos: bool = True) -> List[Path]:
    folder = Path(folder)
    if not folder.exists() or not folder.is_dir():
        return []
    exts = set()
    if include_images:
        exts |= IMAGE_EXT
    if include_videos:
        exts |= VIDEO_EXT
    out = sorted(p for p in folder.iterdir()
                 if p.is_file() and p.suffix.lower() in exts)
    return out
