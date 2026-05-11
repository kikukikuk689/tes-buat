"""Audio analysis for spectrum visualization.

Loads audio, computes per-frame frequency bands grouped logarithmically so
they look musical (and not flat / mathematical). Results are smoothed in
time so spectrum animation looks fluid and "alive", not stiff.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import librosa
    import librosa.feature
    _HAVE_LIBROSA = True
except Exception:  # pragma: no cover
    librosa = None  # type: ignore
    _HAVE_LIBROSA = False


@dataclass
class AnalyzedAudio:
    """Result of analyzing a track."""

    sample_rate: int
    duration_sec: float
    fps: int
    n_bars: int
    # Shape: (num_frames, n_bars). Values in [0,1] after smoothing & gamma.
    bars: np.ndarray
    # Shape: (num_frames,). RMS / loudness envelope in [0,1].
    loudness: np.ndarray
    # Shape: (num_frames,). Beat strength in [0,1].
    beat: np.ndarray
    audio_path: str
    extracted_temp: bool = False
    meta: dict = field(default_factory=dict)

    @property
    def num_frames(self) -> int:
        return self.bars.shape[0]


def extract_audio(input_path: str, target_sr: int = 22050) -> str:
    """Extract audio track to temp WAV using ffmpeg.

    Always re-encode to a known mono/stereo WAV at target_sr so librosa/soundfile
    loading is consistent regardless of source container.
    """
    fd, out_path = tempfile.mkstemp(suffix=".wav", prefix="mss_audio_")
    os.close(fd)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", input_path,
        "-vn", "-ac", "2", "-ar", str(target_sr),
        "-c:a", "pcm_s16le",
        out_path,
    ]
    subprocess.run(cmd, check=True)
    return out_path


def _logspace_bin_edges(n_bars: int, sr: int, n_fft: int,
                        fmin: float = 40.0, fmax: Optional[float] = None) -> np.ndarray:
    """Compute log-spaced FFT bin edges so low frequencies get more bands.

    This produces a much more musical-looking spectrum than linear bins.
    """
    if fmax is None:
        fmax = sr / 2.0
    fmin = max(20.0, fmin)
    fmax = min(sr / 2.0, fmax)
    edges_hz = np.geomspace(fmin, fmax, n_bars + 1)
    edges_bin = np.round(edges_hz / sr * n_fft).astype(int)
    edges_bin = np.clip(edges_bin, 0, n_fft // 2)
    # Ensure strictly increasing.
    for i in range(1, edges_bin.size):
        if edges_bin[i] <= edges_bin[i - 1]:
            edges_bin[i] = edges_bin[i - 1] + 1
    edges_bin = np.clip(edges_bin, 0, n_fft // 2)
    return edges_bin


def analyze_audio(
    audio_path: str,
    fps: int = 30,
    n_bars: int = 64,
    sr: int = 22050,
    smoothing: float = 0.55,
    gamma: float = 0.55,
    sensitivity: float = 1.0,
) -> AnalyzedAudio:
    """Analyze ``audio_path`` and return per-frame spectrum + loudness + beat.

    ``audio_path`` may be a video or audio file; if not WAV, audio is extracted
    via ffmpeg first.

    The bar values are smoothed exponentially over time which is what gives
    spectrum animation a "smooth, characterful" feel instead of being stiff.
    """
    if not _HAVE_LIBROSA:
        raise RuntimeError("librosa is required for audio analysis")

    extracted_temp = False
    src = audio_path
    suffix = Path(audio_path).suffix.lower()
    if suffix not in (".wav", ".flac"):
        src = extract_audio(audio_path, target_sr=sr)
        extracted_temp = True

    try:
        y, file_sr = librosa.load(src, sr=sr, mono=True)
    finally:
        # Keep the temp file alive until we're done with it.
        pass

    duration = float(librosa.get_duration(y=y, sr=file_sr))

    # FFT parameters: hop length sized to give exactly ``fps`` frames per
    # second.  n_fft is the next power of two >= 4*hop for good resolution.
    hop = max(1, int(round(file_sr / float(fps))))
    n_fft = 1
    while n_fft < hop * 4:
        n_fft *= 2
    n_fft = max(n_fft, 1024)

    stft = librosa.stft(y, n_fft=n_fft, hop_length=hop, center=True, window="hann")
    mag = np.abs(stft).astype(np.float32)  # (1+n_fft/2, frames)

    # Bucket FFT bins into n_bars log-spaced bands.
    edges = _logspace_bin_edges(n_bars, file_sr, n_fft, fmin=40.0,
                                 fmax=min(file_sr / 2.0, 16000.0))
    bars = np.zeros((mag.shape[1], n_bars), dtype=np.float32)
    for b in range(n_bars):
        lo, hi = edges[b], edges[b + 1]
        if hi <= lo:
            hi = lo + 1
        bars[:, b] = mag[lo:hi].mean(axis=0)

    # Convert to dB for perceptual scaling, then normalize.
    bars_db = 20.0 * np.log10(bars + 1e-6)
    bars_db = bars_db - bars_db.max()
    bars_norm = 1.0 + (bars_db / 80.0)  # values >= -80 dB map to >= 0
    bars_norm = np.clip(bars_norm, 0.0, 1.0)

    # Gentle low-end emphasis so kicks/bass have presence without dominating.
    band_idx = np.linspace(0.0, 1.0, n_bars, dtype=np.float32)
    boost = 1.0 + 0.35 * np.cos(band_idx * np.pi) ** 2
    bars_norm = np.clip(bars_norm * boost, 0.0, 1.0)

    # Time smoothing with attack/release asymmetry => bars rise quickly,
    # fall smoothly.  This is what makes the spectrum feel alive.
    attack = float(np.clip(1.0 - smoothing * 0.3, 0.4, 1.0))
    release = float(np.clip(1.0 - smoothing, 0.04, 1.0))
    smoothed = np.empty_like(bars_norm)
    state = np.zeros(n_bars, dtype=np.float32)
    for t in range(bars_norm.shape[0]):
        target = bars_norm[t] * sensitivity
        rising = target > state
        coef = np.where(rising, attack, release)
        state = state + coef * (target - state)
        smoothed[t] = state
    smoothed = np.clip(smoothed, 0.0, 1.0) ** gamma

    # Loudness envelope (RMS) for global pulsing effects.
    rms = librosa.feature.rms(y=y, frame_length=n_fft, hop_length=hop, center=True)[0]
    rms = rms / (rms.max() + 1e-9)
    rms = np.clip(rms, 0.0, 1.0)

    # Beat tracking for sparkle/strobe effects.
    onset_env = librosa.onset.onset_strength(y=y, sr=file_sr, hop_length=hop)
    if onset_env.max() > 0:
        onset_env = onset_env / onset_env.max()
    onset_env = np.clip(onset_env, 0.0, 1.0)

    # Align frame counts (rms/onset may differ by 1).
    n_frames = min(smoothed.shape[0], rms.shape[0], onset_env.shape[0])
    smoothed = smoothed[:n_frames]
    rms = rms[:n_frames]
    onset_env = onset_env[:n_frames]

    return AnalyzedAudio(
        sample_rate=file_sr,
        duration_sec=duration,
        fps=fps,
        n_bars=n_bars,
        bars=smoothed,
        loudness=rms.astype(np.float32),
        beat=onset_env.astype(np.float32),
        audio_path=src,
        extracted_temp=extracted_temp,
        meta={"hop": hop, "n_fft": n_fft, "edges": edges.tolist()},
    )


def cleanup_audio(result: AnalyzedAudio) -> None:
    """Remove temp WAV if we extracted one."""
    if result.extracted_temp and os.path.exists(result.audio_path):
        try:
            os.remove(result.audio_path)
        except OSError:
            pass


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
