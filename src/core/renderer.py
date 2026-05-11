"""High-level render pipeline.

Pipeline:
  audio -> spectrum frames + envelope/beats
  per video frame:
      background frame -> tint -> spectrum -> effects -> logo -> lyrics
  raw RGB bytes -> ffmpeg pipe (encode to mp4 with audio)
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np
from PIL import Image

from ..effects.effects import EffectConfig, EffectRenderer, list_effects
from ..overlays.logo import LogoConfig, LogoOverlay
from ..overlays.lyrics import LyricsConfig, LyricsOverlay
from ..spectrum.styles import SpectrumConfig, SpectrumRenderer
from ..utils.logger import get_logger
from .audio import AudioData, SpectrumExtractor, decode_audio_mono
from .background import BackgroundConfig, BackgroundProvider
from .ffmpeg_utils import find_ffmpeg
from .lrc import LRC, parse_lrc

_log = get_logger("render")


RESOLUTION_PRESETS: dict[str, Tuple[int, int]] = {
    "360p":  (640, 360),
    "480p":  (854, 480),
    "720p":  (1280, 720),
    "1080p": (1920, 1080),
    "1440p": (2560, 1440),
    "2160p": (3840, 2160),
}


@dataclass
class RenderJob:
    audio_path: str
    output_path: str
    lrc_path: Optional[str] = None
    background: BackgroundConfig = field(default_factory=BackgroundConfig)
    spectrum: SpectrumConfig = field(default_factory=SpectrumConfig)
    effects: List[EffectConfig] = field(default_factory=list)
    logo: LogoConfig = field(default_factory=LogoConfig)
    lyrics: LyricsConfig = field(default_factory=LyricsConfig)
    resolution: str = "720p"
    custom_width: int = 1280
    custom_height: int = 720
    fps: int = 30
    encoder: str = "libx264"
    bitrate_kbps: int = 4500
    threads: int = 0     # ffmpeg threads; 0 = auto
    preset: str = "veryfast"
    crf: int = 21

    def size(self) -> Tuple[int, int]:
        if self.resolution == "custom":
            return (max(64, self.custom_width), max(64, self.custom_height))
        return RESOLUTION_PRESETS.get(self.resolution, RESOLUTION_PRESETS["720p"])


# Progress callback signature
ProgressCB = Callable[[float, str], None]


# ============================================================
# Frame compositor (single frame)
# ============================================================

class FrameComposer:
    def __init__(self, job: RenderJob, audio: AudioData,
                 spectrum_data: np.ndarray, env: np.ndarray, beats: np.ndarray,
                 lrc: Optional[LRC], duration: float):
        self.job = job
        self.size = job.size()
        self.spec_data = spectrum_data
        self.env = env
        self.beats = beats
        self.duration = duration

        self.bg = BackgroundProvider(job.background, self.size, job.fps, duration)
        self.spectrum = SpectrumRenderer(job.spectrum)
        self.effects = EffectRenderer(job.effects, self.size, job.fps)
        self.logo = LogoOverlay(job.logo, self.size)
        self.lyrics = LyricsOverlay(job.lyrics, lrc, self.size)
        self.n_frames = spectrum_data.shape[0]

    def close(self) -> None:
        self.bg.close()

    def render_frame(self, idx: int) -> Image.Image:
        t = idx / self.job.fps
        bg = self.bg.get_frame(t).convert("RGBA")
        # Spectrum
        bands = self.spec_data[idx] if idx < self.spec_data.shape[0] else self.spec_data[-1]
        e = float(self.env[idx]) if idx < self.env.shape[0] else 0.0
        beat = bool(self.beats[idx]) if idx < self.beats.shape[0] else False
        self.spectrum.draw(bg, t, idx, bands, e)
        # Effects on top of spectrum
        self.effects.draw(bg, t, idx, e, beat)
        # Logo
        self.logo.draw(bg)
        # Lyrics
        self.lyrics.draw(bg, t)
        return bg


# ============================================================
# Renderer orchestration
# ============================================================

@dataclass
class _CancelToken:
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True


def render_preview_frame(job: RenderJob, t: float) -> Image.Image:
    """Render satu frame untuk preview (decode audio jika belum)."""
    audio = decode_audio_mono(job.audio_path)
    ex = SpectrumExtractor(audio, fps=job.fps, n_bands=job.spectrum.n_bands)
    # We only need one frame's worth of bands; compute envelope quickly by computing all (cached)
    spec = ex.compute_all()
    env = ex.envelope()
    beats = ex.beats()
    lrc = parse_lrc(job.lrc_path) if job.lrc_path else LRC()
    comp = FrameComposer(job, audio, spec, env, beats, lrc, audio.duration)
    try:
        idx = max(0, min(comp.n_frames - 1, int(t * job.fps)))
        return comp.render_frame(idx).convert("RGB")
    finally:
        comp.close()


def render(job: RenderJob, progress_cb: Optional[ProgressCB] = None,
           cancel: Optional[_CancelToken] = None) -> str:
    """Render satu video. Return path output. Raise on error."""
    cancel = cancel or _CancelToken()
    t0 = time.time()
    _log.info("Mulai render -> %s", job.output_path)
    ff = find_ffmpeg()
    if not ff:
        raise RuntimeError("FFmpeg tidak tersedia. Install via UI dulu.")

    audio = decode_audio_mono(job.audio_path)
    extractor = SpectrumExtractor(audio, fps=job.fps, n_bands=job.spectrum.n_bands,
                                   smoothing=job.spectrum.smoothness)
    spec = extractor.compute_all(log_progress=True)
    env = extractor.envelope()
    beats = extractor.beats()

    lrc = parse_lrc(job.lrc_path) if job.lrc_path else LRC()
    _log.info("Lyrics lines: %d", len(lrc.lines))

    composer = FrameComposer(job, audio, spec, env, beats, lrc, audio.duration)

    W, H = job.size()
    total_frames = composer.n_frames
    _log.info("Total frames: %d (%.2fs @ %d fps, %dx%d)",
              total_frames, audio.duration, job.fps, W, H)

    Path(job.output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ff, "-y",
        "-v", "warning",
        "-stats",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{W}x{H}",
        "-pix_fmt", "rgb24",
        "-r", str(job.fps),
        "-i", "-",
        "-i", job.audio_path,
        "-c:v", job.encoder,
        "-preset", job.preset,
        "-crf", str(job.crf),
        "-pix_fmt", "yuv420p",
        "-b:v", f"{job.bitrate_kbps}k",
        "-maxrate", f"{int(job.bitrate_kbps * 1.4)}k",
        "-bufsize", f"{int(job.bitrate_kbps * 2)}k",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
    ]
    if job.threads > 0:
        cmd.extend(["-threads", str(job.threads)])
    cmd.append(job.output_path)
    _log.info("FFmpeg cmd: %s", " ".join(cmd))

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            bufsize=10 ** 7)

    stderr_lines: List[str] = []

    def _stderr_reader() -> None:
        if proc.stdout is None:
            return
        for raw in iter(proc.stdout.readline, b""):
            try:
                line = raw.decode("utf-8", errors="ignore").rstrip()
            except (OSError, UnicodeError):
                continue
            stderr_lines.append(line)
            if line.startswith("frame=") or "speed=" in line or "error" in line.lower():
                _log.info("ffmpeg: %s", line)

    reader_t = threading.Thread(target=_stderr_reader, name="ffmpeg-stderr", daemon=True)
    reader_t.start()

    # Use a small pipeline: produce frames in a worker thread, write in main.
    # For now keep it simple/serial because pickling Image+PIL across threads
    # is fine but ffmpeg stdin write should be serial.
    last_log = time.time()
    try:
        for i in range(total_frames):
            if cancel.cancelled:
                _log.warning("Render dibatalkan pada frame %d/%d", i, total_frames)
                break
            frame = composer.render_frame(i).convert("RGB")
            try:
                proc.stdin.write(frame.tobytes())
            except BrokenPipeError as e:
                raise RuntimeError(f"FFmpeg pipe putus: {e}") from e

            if progress_cb and (i % max(1, job.fps // 2) == 0 or i == total_frames - 1):
                pct = (i + 1) / total_frames
                progress_cb(pct, f"frame {i + 1}/{total_frames}")

            now = time.time()
            if now - last_log > 5.0:
                elapsed = now - t0
                speed = (i + 1) / elapsed if elapsed > 0 else 0
                eta = (total_frames - i) / max(0.1, speed)
                _log.info("Progress: %d/%d (%.1f%%) | %.1f fps | ETA %.0fs",
                          i + 1, total_frames, 100 * (i + 1) / total_frames,
                          speed, eta)
                last_log = now
    finally:
        composer.close()
        if proc.stdin:
            try:
                proc.stdin.close()
            except (OSError, BrokenPipeError):
                pass

    rc = proc.wait()
    reader_t.join(timeout=2)
    if rc != 0:
        tail = "\n".join(stderr_lines[-20:])
        raise RuntimeError(f"FFmpeg exit dengan kode {rc}:\n{tail}")

    elapsed = time.time() - t0
    _log.info("Render selesai dalam %.1fs -> %s", elapsed, job.output_path)
    return job.output_path
