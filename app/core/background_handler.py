"""Background image / video handling for the renderer.

Supports:
- A single static image (PNG/JPG/etc).
- A single video file (looped to track duration).
- A list of images / videos, used either:
    * cycled in order across time (each segment = duration / N).
    * randomly chosen segments.

For batch rendering the high-level pipeline picks WHICH background file to
use for each track (by order / by name match / random) -- that's handled in
the renderer, not here.  This class is purely "given these files + a
strategy, produce a frame at time t".
"""
from __future__ import annotations

import random
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter, ImageOps


IMG_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
VID_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


def is_image(p: str) -> bool:
    return Path(p).suffix.lower() in IMG_EXT


def is_video(p: str) -> bool:
    return Path(p).suffix.lower() in VID_EXT


@dataclass
class BackgroundConfig:
    files: List[str] = field(default_factory=list)
    multi_mode: str = "Single"   # "Single" or "Multi"
    multi_strategy: str = "Order"  # "Order" or "Random"
    blur: float = 0.0            # 0..1 (0=no blur)
    darken: float = 0.30         # 0..1 fraction of black overlay
    zoom_pulse: bool = False     # Subtle "ken burns" zoom that breathes
    fit_mode: str = "Cover"      # "Cover" or "Contain"


def _ffprobe_duration(path: str) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            check=True, capture_output=True, text=True,
            stdin=subprocess.DEVNULL,
        ).stdout.strip()
        return float(out)
    except (subprocess.CalledProcessError, ValueError):
        return 0.0


def _video_to_image_frames(path: str, size: Tuple[int, int], fps_video_extract: int = 8,
                           tmpdir: Optional[Path] = None) -> List[str]:
    """Extract one image per ~``1/fps_video_extract`` seconds for a video.

    This trades disk for speed: we precompute a small image strip and the
    renderer just picks frames out of it at run time.  Far faster than
    decoding the video frame-by-frame in Python every render.
    """
    if tmpdir is None:
        tmpdir = Path(tempfile.mkdtemp(prefix="mss_bg_"))
    w, h = size
    out_pat = str(tmpdir / "frame_%05d.jpg")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", path,
        "-vf", f"fps={fps_video_extract},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}",
        "-q:v", "3", out_pat,
    ], check=True, stdin=subprocess.DEVNULL)
    return sorted(str(p) for p in tmpdir.glob("frame_*.jpg"))


def _fit_image(img: Image.Image, size: Tuple[int, int], mode: str) -> Image.Image:
    w, h = size
    if mode == "Contain":
        out = ImageOps.contain(img, size, method=Image.LANCZOS)
        canvas = Image.new("RGB", size, (0, 0, 0))
        canvas.paste(out, ((w - out.width) // 2, (h - out.height) // 2))
        return canvas
    # Cover (default)
    return ImageOps.fit(img, size, method=Image.LANCZOS)


def _apply_treatment(img: Image.Image, cfg: BackgroundConfig, t: float) -> Image.Image:
    if cfg.blur > 0:
        img = img.filter(ImageFilter.GaussianBlur(radius=cfg.blur * 18))
    if cfg.zoom_pulse:
        zoom = 1.02 + 0.025 * np.sin(t * 0.3)
        zw, zh = int(img.width * zoom), int(img.height * zoom)
        big = img.resize((zw, zh), Image.LANCZOS)
        off_x = (zw - img.width) // 2
        off_y = (zh - img.height) // 2
        img = big.crop((off_x, off_y, off_x + img.width, off_y + img.height))
    if cfg.darken > 0:
        overlay = Image.new("RGB", img.size, (0, 0, 0))
        img = Image.blend(img, overlay, cfg.darken)
    return img


class BackgroundEngine:
    """Provides a background frame for any time ``t``.

    Internally handles:
        * a single image (just cached)
        * a single video (frame strip pre-extracted)
        * multiple images/videos cycled across time

    All output frames are RGB PIL images sized exactly to the canvas.
    """

    def __init__(self, canvas_size: Tuple[int, int], duration: float, cfg: BackgroundConfig):
        self.size = canvas_size
        self.duration = max(0.1, duration)
        self.cfg = cfg
        self._tmpdir = Path(tempfile.mkdtemp(prefix="mss_bg_"))
        self._segments: List[dict] = []  # each: {start, end, kind, image|frames|fps}
        self._build()

    def cleanup(self):
        import shutil
        try:
            shutil.rmtree(self._tmpdir)
        except OSError:
            pass

    def _load_image(self, path: str) -> Image.Image:
        img = Image.open(path).convert("RGB")
        return _fit_image(img, self.size, self.cfg.fit_mode)

    def _build(self):
        files = [f for f in self.cfg.files if Path(f).exists()]
        if not files:
            # Default to plain dark gradient if no background is provided.
            img = Image.new("RGB", self.size, (12, 14, 24))
            self._segments = [{"start": 0, "end": self.duration, "kind": "image", "image": img}]
            return

        # Single source mode: just use the first file across the whole track.
        if self.cfg.multi_mode != "Multi" or len(files) == 1:
            chosen = files[0]
            if is_video(chosen):
                frames = _video_to_image_frames(chosen, self.size, 8, self._tmpdir)
                self._segments = [{
                    "start": 0, "end": self.duration, "kind": "video",
                    "frames": frames, "fps": 8,
                }]
            else:
                self._segments = [{
                    "start": 0, "end": self.duration, "kind": "image",
                    "image": self._load_image(chosen),
                }]
            return

        # Multi mode: pick order
        if self.cfg.multi_strategy == "Random":
            ordered = list(files)
            random.shuffle(ordered)
        else:
            ordered = list(files)

        seg_dur = self.duration / len(ordered)
        cur = 0.0
        for f in ordered:
            end = cur + seg_dur
            if is_video(f):
                frames = _video_to_image_frames(f, self.size, 6, self._tmpdir)
                self._segments.append({
                    "start": cur, "end": end, "kind": "video",
                    "frames": frames, "fps": 6,
                })
            else:
                self._segments.append({
                    "start": cur, "end": end, "kind": "image",
                    "image": self._load_image(f),
                })
            cur = end

    def frame(self, t: float) -> Image.Image:
        # Locate segment for this time
        seg = self._segments[0]
        for s in self._segments:
            if s["start"] <= t < s["end"]:
                seg = s
                break
        if seg["kind"] == "image":
            img = seg["image"].copy()
        else:
            frames = seg["frames"]
            if not frames:
                img = Image.new("RGB", self.size, (10, 10, 16))
            else:
                local_t = t - seg["start"]
                idx = int(local_t * seg["fps"]) % len(frames)
                img = Image.open(frames[idx]).convert("RGB")
                if img.size != self.size:
                    img = _fit_image(img, self.size, self.cfg.fit_mode)
        return _apply_treatment(img, self.cfg, t)
