"""Audio extraction, looping with crossfade, and final muxing using FFmpeg."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import soundfile as sf

from .config import (
    AUDIO_SAMPLE_RATE,
    DEFAULT_CROSSFADE_SEC,
    FFMPEG_AUDIO_BITRATE,
    FFMPEG_AUDIO_CODEC,
    FFMPEG_VIDEO_CODEC,
)
from .utils import find_ffmpeg, run_command


def extract_audio(input_video: str | Path, wav_path: str | Path) -> Path:
    """Extract the audio track from ``input_video`` into a WAV file.

    The output is resampled to :data:`~app.config.AUDIO_SAMPLE_RATE` (stereo,
    PCM 16-bit). If the source has no audio, a silent stereo track is created
    so downstream steps still produce a valid file.

    Args:
        input_video: Source video path.
        wav_path: Destination WAV file path.

    Returns:
        The :class:`~pathlib.Path` of the written WAV file.
    """

    ffmpeg = find_ffmpeg()
    wav_path = Path(wav_path)
    wav_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(input_video),
        "-vn",
        "-ac",
        "2",
        "-ar",
        str(AUDIO_SAMPLE_RATE),
        "-acodec",
        "pcm_s16le",
        str(wav_path),
    ]
    proc = run_command(cmd, check=False)
    if proc.returncode != 0 or not wav_path.exists() or wav_path.stat().st_size == 0:
        silence = np.zeros((AUDIO_SAMPLE_RATE, 2), dtype=np.int16)
        sf.write(str(wav_path), silence, AUDIO_SAMPLE_RATE, subtype="PCM_16")
    return wav_path


def _slice_segment(data: np.ndarray, sr: int, start_sec: float, end_sec: float) -> np.ndarray:
    """Return ``data[start_sec:end_sec]`` clipped to valid bounds."""

    start_idx = max(0, int(round(start_sec * sr)))
    end_idx = min(data.shape[0], int(round(end_sec * sr)))
    if end_idx <= start_idx:
        end_idx = min(data.shape[0], start_idx + 1)
    return data[start_idx:end_idx]


def _crossfade(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Equal-power crossfade ``a`` (fade-out) into ``b`` (fade-in)."""

    n = min(a.shape[0], b.shape[0])
    if n <= 0:
        return np.zeros((0,) + a.shape[1:], dtype=np.float32)
    t = np.linspace(0.0, 1.0, n, dtype=np.float32, endpoint=False)
    fade_out = np.cos(t * 0.5 * np.pi)
    fade_in = np.sin(t * 0.5 * np.pi)
    if a.ndim > 1:
        fade_out = fade_out[:, None]
        fade_in = fade_in[:, None]
    return a[:n].astype(np.float32) * fade_out + b[:n].astype(np.float32) * fade_in


def render_looped_audio(
    input_wav: str | Path,
    output_wav: str | Path,
    start_sec: float,
    end_sec: float,
    target_hours: float,
    crossfade_sec: float = DEFAULT_CROSSFADE_SEC,
) -> Path:
    """Loop ``input_wav`` into a long file using a constant-power crossfade.

    The audio segment ``[start_sec, end_sec]`` of ``input_wav`` is repeated
    enough times to fill ``target_hours``, with neighbouring loops blended over
    ``crossfade_sec`` to avoid clicks or hard cuts.

    Args:
        input_wav: Source WAV file (typically produced by :func:`extract_audio`).
        output_wav: Destination WAV file path.
        start_sec: Loop start time in seconds, relative to ``input_wav``.
        end_sec: Loop end time in seconds, relative to ``input_wav``.
        target_hours: Desired duration of the output, in hours.
        crossfade_sec: Crossfade duration between consecutive loops.

    Returns:
        The :class:`~pathlib.Path` of the written WAV file.

    Raises:
        ValueError: If the loop segment is empty or ``target_hours`` <= 0.
    """

    if target_hours <= 0:
        raise ValueError("target_hours harus > 0")

    data, sr = sf.read(str(input_wav), always_2d=True, dtype="float32")
    segment = _slice_segment(data, sr, start_sec, end_sec)
    if segment.shape[0] < 2:
        raise ValueError("Segmen audio terlalu pendek untuk di-loop.")

    seg_len = segment.shape[0]
    xfade_len = max(0, int(round(crossfade_sec * sr)))
    xfade_len = min(xfade_len, seg_len // 2)
    target_samples = max(seg_len, int(round(target_hours * 3600.0 * sr)))

    out = np.zeros((target_samples, segment.shape[1]), dtype=np.float32)
    out[:seg_len] = segment
    write_pos = seg_len

    if xfade_len <= 0:
        while write_pos < target_samples:
            remaining = target_samples - write_pos
            chunk = segment[:remaining]
            out[write_pos : write_pos + chunk.shape[0]] = chunk
            write_pos += chunk.shape[0]
    else:
        body_len = seg_len - xfade_len
        body = segment[xfade_len:]
        head = segment[:xfade_len]
        while write_pos < target_samples:
            xfade_start = write_pos - xfade_len
            tail = out[xfade_start : xfade_start + xfade_len]
            mixed = _crossfade(tail, head)
            n_mix = min(mixed.shape[0], target_samples - xfade_start)
            out[xfade_start : xfade_start + n_mix] = mixed[:n_mix]
            write_pos = xfade_start + n_mix
            if write_pos >= target_samples:
                break
            remaining = target_samples - write_pos
            chunk = body[:remaining]
            out[write_pos : write_pos + chunk.shape[0]] = chunk
            write_pos += chunk.shape[0]
            if chunk.shape[0] == 0:
                break

    out = np.clip(out, -1.0, 1.0)
    output_wav = Path(output_wav)
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output_wav), out, sr, subtype="PCM_16")
    return output_wav


def mux_audio_video(video_path: str | Path, audio_path: str | Path, output_path: str | Path) -> Path:
    """Combine a silent video and a WAV audio track into a final MP4.

    The video is re-encoded to :data:`~app.config.FFMPEG_VIDEO_CODEC` (H.264)
    and the audio to :data:`~app.config.FFMPEG_AUDIO_CODEC` (AAC) at
    :data:`~app.config.FFMPEG_AUDIO_BITRATE`. The shortest stream determines
    the output duration so the file ends cleanly.

    Args:
        video_path: Path to the silent intermediate video.
        audio_path: Path to the looped WAV audio file.
        output_path: Destination MP4 path.

    Returns:
        The :class:`~pathlib.Path` of the muxed MP4.

    Raises:
        RuntimeError: If FFmpeg fails to produce the output file.
    """

    ffmpeg = find_ffmpeg()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        FFMPEG_VIDEO_CODEC,
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        FFMPEG_AUDIO_CODEC,
        "-b:a",
        FFMPEG_AUDIO_BITRATE,
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    proc = run_command(cmd, check=False)
    if proc.returncode != 0 or not output_path.exists():
        raise RuntimeError(
            f"FFmpeg gagal melakukan mux audio+video: {proc.stderr.strip()[-500:]}"
        )
    return output_path


def loops_needed(loop_sec: float, target_hours: float) -> int:
    """Return the integer number of loop repetitions needed for ``target_hours``."""

    if loop_sec <= 0:
        return 0
    return int(math.ceil((target_hours * 3600.0) / loop_sec))
