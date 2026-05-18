"""Audio extraction and seamless looping with crossfade.

The audio pipeline uses ``ffmpeg`` to extract the chosen segment as a raw
``pcm_s16le`` WAV file, then constructs a "loop unit" whose first
``crossfade_seconds`` are an equal-power-style linear blend of the segment's
tail and head.  Concatenating copies of this unit produces a seamless, click
free track.
"""

from __future__ import annotations

import logging
import math
import shutil
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from asmr_loop_maker.utils import ensure_ffmpeg, format_duration, run_command

logger = logging.getLogger("asmr_loop_maker.audio")

_TARGET_SAMPLE_RATE = 44_100
_TARGET_CHANNELS = 2


@dataclass
class AudioSegment:
    sample_rate: int
    channels: int
    samples: np.ndarray  # shape: (frames, channels), dtype float32 in [-1, 1]

    @property
    def duration(self) -> float:
        return self.samples.shape[0] / float(self.sample_rate)


def has_audio_stream(video_path: Path) -> bool:
    """Return ``True`` if ``video_path`` contains at least one audio stream."""

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return False
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "csv=p=0",
        str(video_path),
    ]
    try:
        result = run_command(cmd, check=False)
    except RuntimeError:
        return False
    return "audio" in result.stdout.lower()


def extract_segment(
    video_path: Path,
    start_time: float,
    end_time: float,
    output_wav: Path,
    *,
    sample_rate: int = _TARGET_SAMPLE_RATE,
    channels: int = _TARGET_CHANNELS,
) -> AudioSegment:
    """Extract ``[start_time, end_time]`` from ``video_path`` as a WAV file.

    Returns the loaded ``AudioSegment`` for further processing.
    """

    ffmpeg = ensure_ffmpeg()
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.0, end_time - start_time)
    cmd = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-ss",
        format_duration(start_time),
        "-t",
        format_duration(duration),
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        "-c:a",
        "pcm_s16le",
        str(output_wav),
    ]
    run_command(cmd)
    return load_wav(output_wav)


def load_wav(path: Path) -> AudioSegment:
    """Load a 16-bit PCM WAV file as a normalised float32 ``AudioSegment``."""

    with wave.open(str(path), "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sample_rate = wf.getframerate()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)
    if sampwidth != 2:
        raise RuntimeError(
            f"Expected 16-bit PCM audio, got {sampwidth * 8}-bit ({path})"
        )
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if nchannels > 1:
        samples = samples.reshape(-1, nchannels)
    else:
        samples = samples.reshape(-1, 1)
    return AudioSegment(sample_rate=sample_rate, channels=nchannels, samples=samples)


def build_loop_unit(
    segment: AudioSegment, crossfade_seconds: float
) -> tuple[np.ndarray, int]:
    """Build a click-free loop unit for ``segment``.

    The returned unit, when concatenated with itself, transitions smoothly
    between iterations because its first ``crossfade_seconds`` already
    contain a linear blend of the tail and the head of the original segment.
    """

    samples = segment.samples
    sample_rate = segment.sample_rate
    total = samples.shape[0]

    crossfade_samples = int(round(max(0.0, crossfade_seconds) * sample_rate))
    crossfade_samples = max(0, min(crossfade_samples, total // 2))

    if crossfade_samples == 0:
        return samples.copy(), 0

    fade_in = np.linspace(0.0, 1.0, crossfade_samples, dtype=np.float32).reshape(-1, 1)
    fade_out = 1.0 - fade_in
    head = samples[:crossfade_samples]
    tail = samples[-crossfade_samples:]
    blended = tail * fade_out + head * fade_in
    middle = samples[crossfade_samples : total - crossfade_samples]
    if middle.size:
        unit = np.concatenate([blended, middle], axis=0)
    else:
        unit = blended
    return unit, crossfade_samples


def render_audio_loop(
    video_path: Path,
    start_time: float,
    end_time: float,
    target_duration_seconds: float,
    crossfade_seconds: float,
    output_wav: Path,
    *,
    work_dir: Optional[Path] = None,
) -> Optional[float]:
    """Render a seamless looped audio track to ``output_wav``.

    Returns the achieved duration in seconds, or ``None`` if the source
    video has no audio stream.
    """

    if not has_audio_stream(video_path):
        logger.info("No audio stream detected for %s; skipping audio render", video_path)
        return None

    work_dir = work_dir or output_wav.parent
    work_dir.mkdir(parents=True, exist_ok=True)
    tmp_segment_wav = work_dir / "_segment.wav"
    segment = extract_segment(video_path, start_time, end_time, tmp_segment_wav)

    unit, _ = build_loop_unit(segment, crossfade_seconds)
    unit_frames = unit.shape[0]
    if unit_frames == 0:
        raise RuntimeError("Audio segment has zero samples after processing")

    target_frames = int(round(target_duration_seconds * segment.sample_rate))
    if target_frames <= 0:
        raise ValueError("Target duration must be positive")

    int_unit = np.clip(unit * 32767.0, -32768.0, 32767.0).astype(np.int16)

    output_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_wav), "wb") as wf:
        wf.setnchannels(segment.channels)
        wf.setsampwidth(2)
        wf.setframerate(segment.sample_rate)
        written = 0
        while written < target_frames:
            remaining = target_frames - written
            chunk_len = min(unit_frames, remaining)
            wf.writeframes(int_unit[:chunk_len].tobytes())
            written += chunk_len

    try:
        tmp_segment_wav.unlink()
    except OSError:
        pass

    achieved = target_frames / float(segment.sample_rate)
    return achieved


def total_loop_iterations(
    segment_seconds: float, crossfade_seconds: float, target_seconds: float
) -> int:
    """Return the number of loop iterations required for ``target_seconds``."""

    effective = max(segment_seconds - crossfade_seconds, 0.001)
    return max(1, math.ceil(target_seconds / effective))
