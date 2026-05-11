"""Main rendering pipeline.

Composes background + spectrum + effects + logo + lyrics in Python per
frame and pipes RGB24 frames to FFmpeg for fast h.264 encoding (audio is
muxed straight from the source file, no re-encoding of audio data unless
needed).  This keeps Python's job to "draw one image per frame" and lets
FFmpeg + libx264 do what they're fastest at.

Designed to be light enough for low-end PCs:
- Default 24 fps + libx264 ``-preset ultrafast`` keeps CPU usage low.
- Background videos are pre-decoded once into a small JPEG strip so we
  never re-decode video inside the per-frame Python loop.
- All overlays are composed with PIL into one image before being sent.
"""
from __future__ import annotations

import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .audio_analyzer import AnalyzedAudio, analyze_audio, cleanup_audio
from .background_handler import BackgroundConfig, BackgroundEngine
from .effects import Effect, create_effect
from .ffmpeg_utils import ffmpeg_path
from .logo_handler import LogoConfig, LogoOverlay
from .lrc_parser import LyricLine, lyric_at, parse_lrc
from .spectrum_styles import SpectrumConfig, render_frame as render_spectrum
from ..utils.fonts import load_font
from ..utils.logger import AppLogger


# Common preset resolutions.
RESOLUTIONS = {
    "480p (854x480)":   (854, 480),
    "720p (1280x720)":  (1280, 720),
    "1080p (1920x1080)": (1920, 1080),
    "1440p (2560x1440)": (2560, 1440),
    "2160p (3840x2160)": (3840, 2160),
    "Vertical 720x1280": (720, 1280),
    "Vertical 1080x1920": (1080, 1920),
    "Square 1080x1080":  (1080, 1080),
}


@dataclass
class LyricStyle:
    font_family: str = "Montserrat"
    font_size_pct: float = 0.055   # of canvas height
    color: Tuple[int, int, int] = (255, 255, 255)
    outline_color: Tuple[int, int, int] = (0, 0, 0)
    outline_width: int = 3
    shadow: bool = True
    bold_box: bool = False
    box_color: Tuple[int, int, int] = (0, 0, 0)
    box_opacity: float = 0.35
    position_pct: float = 0.68     # vertical center as fraction of height (above spectrum)
    align: str = "center"          # "center" / "left" / "right"
    fade_in: float = 0.25          # seconds for fade-in animation
    uppercase: bool = False


@dataclass
class RenderConfig:
    audio_input: str
    lyrics_input: Optional[str] = None
    output_path: str = "output/render/output.mp4"
    resolution: str = "720p (1280x720)"
    fps: int = 24
    spectrum: SpectrumConfig = field(default_factory=SpectrumConfig)
    background: BackgroundConfig = field(default_factory=BackgroundConfig)
    logo: LogoConfig = field(default_factory=LogoConfig)
    lyric: LyricStyle = field(default_factory=LyricStyle)
    effect_name: str = "Fireflies"
    effect_intensity: float = 1.0
    effect_color: Tuple[int, int, int] = (255, 230, 160)
    encoder_preset: str = "veryfast"  # ultrafast/superfast/veryfast/faster/fast/medium
    crf: int = 23
    show_preview: bool = False
    lyric_offset_ms: int = 0
    lyric_lead_in: float = 0.1
    lyric_linger: float = 0.2

    @property
    def size(self) -> Tuple[int, int]:
        return RESOLUTIONS.get(self.resolution, (1280, 720))


def _draw_lyric(canvas: Image.Image, text: str, cfg: RenderConfig,
                fade_alpha: float = 1.0) -> None:
    if not text:
        return
    w, h = canvas.size
    style = cfg.lyric
    if style.uppercase:
        text = text.upper()
    size = max(14, int(h * style.font_size_pct))
    font = load_font(style.font_family, size)

    draw = ImageDraw.Draw(canvas, "RGBA")
    # Wrap to ~90% of canvas width
    max_w = int(w * 0.9)
    lines = _wrap_text(text, font, max_w, draw)

    # Measure total block
    line_heights = [draw.textbbox((0, 0), L, font=font)[3] for L in lines]
    block_h = sum(line_heights) + (len(lines) - 1) * 6
    cy = int(h * style.position_pct)
    block_top = cy - block_h // 2

    # Optional box behind lyrics for readability.
    if style.bold_box:
        box_pad = int(size * 0.4)
        widths = [draw.textbbox((0, 0), L, font=font)[2] for L in lines]
        box_w = max(widths) + box_pad * 2
        box = Image.new("RGBA", (box_w, block_h + box_pad * 2),
                        style.box_color + (int(255 * style.box_opacity * fade_alpha),))
        bx = (w - box_w) // 2
        by = block_top - box_pad
        canvas.alpha_composite(box, (bx, by))

    if style.shadow:
        sh_offset = max(2, size // 14)
        for L, lh in zip(lines, line_heights):
            bbox = draw.textbbox((0, 0), L, font=font)
            tw = bbox[2] - bbox[0]
            x = (w - tw) // 2
            y = block_top
            draw.text((x + sh_offset, y + sh_offset), L, font=font,
                      fill=(0, 0, 0, int(180 * fade_alpha)))
            block_top += lh + 6
        block_top = cy - block_h // 2

    # Outlined text on top.
    for L, lh in zip(lines, line_heights):
        bbox = draw.textbbox((0, 0), L, font=font)
        tw = bbox[2] - bbox[0]
        x = (w - tw) // 2
        y = block_top
        if style.outline_width > 0:
            ow = style.outline_width
            oc = style.outline_color + (int(255 * fade_alpha),)
            for dx in range(-ow, ow + 1):
                for dy in range(-ow, ow + 1):
                    if dx == 0 and dy == 0:
                        continue
                    draw.text((x + dx, y + dy), L, font=font, fill=oc)
        draw.text((x, y), L, font=font, fill=style.color + (int(255 * fade_alpha),))
        block_top += lh + 6


def _wrap_text(text: str, font, max_w: int, draw) -> List[str]:
    words = text.split()
    if not words:
        return []
    lines: List[str] = []
    cur = words[0]
    for w in words[1:]:
        trial = cur + " " + w
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def _build_ffmpeg_cmd(cfg: RenderConfig, audio_path: str, video_w: int,
                      video_h: int) -> List[str]:
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("FFmpeg tidak tersedia.")
    cmd = [
        ffmpeg, "-y", "-loglevel", "error", "-hide_banner",
        # raw rgb24 frames from Python
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{video_w}x{video_h}", "-r", str(cfg.fps),
        "-i", "pipe:0",
        # audio source
        "-i", audio_path,
        # video encoder (libx264 with chosen preset/CRF for quality/speed)
        "-c:v", "libx264", "-preset", cfg.encoder_preset, "-crf", str(cfg.crf),
        "-pix_fmt", "yuv420p",
        "-tune", "stillimage,fastdecode",
        "-movflags", "+faststart",
        # audio: keep AAC if possible, else encode to AAC
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        cfg.output_path,
    ]
    return cmd


class Renderer:
    """Synchronous renderer; intended to be called from a background thread."""

    def __init__(self, cfg: RenderConfig):
        self.cfg = cfg
        self.log = AppLogger.get()
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def render(self, progress: Optional[Callable[[float, str], None]] = None) -> bool:
        cfg = self.cfg
        size = cfg.size
        Path(cfg.output_path).parent.mkdir(parents=True, exist_ok=True)

        # Audio analysis
        self.log.info(f"Menganalisis audio: {Path(cfg.audio_input).name}")
        analysis = analyze_audio(
            cfg.audio_input,
            fps=cfg.fps,
            n_bars=64,
            smoothing=0.55 + (1.0 - cfg.spectrum.density) * 0.2,
            gamma=0.55,
        )
        try:
            duration = analysis.duration_sec
            total_frames = int(duration * cfg.fps)
            self.log.info(f"Durasi: {duration:.2f}s, total frame: {total_frames}")

            # Background
            self.log.info("Menyiapkan background...")
            bg = BackgroundEngine(size, duration, cfg.background)

            # Logo
            logo = LogoOverlay(size, cfg.logo)

            # Effect
            effect = create_effect(cfg.effect_name, size, cfg.fps,
                                    intensity=cfg.effect_intensity,
                                    color=cfg.effect_color)

            # Lyrics
            lyrics: List[LyricLine] = []
            if cfg.lyrics_input and Path(cfg.lyrics_input).exists():
                lyrics = parse_lrc(cfg.lyrics_input, offset_ms=cfg.lyric_offset_ms)
                self.log.info(f"Lirik dimuat: {len(lyrics)} baris")
            else:
                self.log.info("Tidak ada lirik dipakai.")

            cmd = _build_ffmpeg_cmd(cfg, analysis.audio_path, size[0], size[1])
            self.log.info("Menjalankan FFmpeg encoder...")
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                    stderr=subprocess.PIPE)

            stderr_buf: List[str] = []
            def _drain_stderr():
                if proc.stderr is None:
                    return
                for raw in iter(proc.stderr.readline, b""):
                    s = raw.decode("utf-8", "replace").strip()
                    if s:
                        stderr_buf.append(s)
                        if "error" in s.lower():
                            self.log.error(f"ffmpeg: {s}")
            t_err = threading.Thread(target=_drain_stderr, daemon=True)
            t_err.start()

            start_t = time.time()
            try:
                for i in range(total_frames):
                    if self._cancel.is_set():
                        self.log.warning("Render dibatalkan oleh user")
                        break
                    t = i / cfg.fps
                    # Background
                    canvas = bg.frame(t).convert("RGBA")
                    # Spectrum overlay
                    bar_idx = min(i, analysis.bars.shape[0] - 1)
                    bars = analysis.bars[bar_idx]
                    loud = float(analysis.loudness[bar_idx])
                    beat = float(analysis.beat[bar_idx])
                    spec = render_spectrum(size, bars, cfg.spectrum, loud, beat, t)
                    canvas.alpha_composite(spec)
                    # Effect overlay
                    if effect is not None:
                        eff_img = effect.step(beat, loud, t)
                        canvas.alpha_composite(eff_img)
                    # Logo
                    logo.composite(canvas)
                    # Lyrics (only if active at this time)
                    active = lyric_at(lyrics, t, cfg.lyric_lead_in, cfg.lyric_linger)
                    if active is not None:
                        # Fade in across fade_in seconds from start of line
                        fade_t = (t - active.start) / max(1e-3, cfg.lyric.fade_in)
                        fade_alpha = max(0.0, min(1.0, fade_t))
                        _draw_lyric(canvas, active.text, cfg, fade_alpha)
                    # Send to ffmpeg as rgb24
                    rgb = np.array(canvas.convert("RGB"))
                    try:
                        proc.stdin.write(rgb.tobytes())
                    except BrokenPipeError:
                        self.log.error("FFmpeg menutup pipe lebih awal")
                        break
                    if progress and i % max(1, cfg.fps // 4) == 0:
                        elapsed = time.time() - start_t
                        fps_now = (i + 1) / max(1e-3, elapsed)
                        eta = (total_frames - i) / max(1e-3, fps_now)
                        progress(i / total_frames,
                                 f"Frame {i}/{total_frames}  "
                                 f"({fps_now:.1f} fps, ETA {eta:.0f}s)")
            finally:
                try:
                    if proc.stdin:
                        proc.stdin.close()
                except OSError:
                    pass
                proc.wait()
                t_err.join(timeout=1.0)
                bg.cleanup()

            ok = proc.returncode == 0 and not self._cancel.is_set()
            if ok:
                self.log.info(f"Render selesai: {cfg.output_path}")
            else:
                msg = "\n".join(stderr_buf[-20:])
                self.log.error(f"FFmpeg gagal (code {proc.returncode}): {msg}")
            return ok
        finally:
            cleanup_audio(analysis)
