"""Audio decoding + spectrum frame extraction."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from ..utils.logger import get_logger
from .ffmpeg_utils import find_ffmpeg

_log = get_logger("audio")


@dataclass
class AudioData:
    samples: np.ndarray   # shape (N,), float32, mono, -1..1
    sample_rate: int
    duration: float

    @property
    def n_samples(self) -> int:
        return int(self.samples.shape[0])


def decode_audio_mono(path: str | Path, sr: int = 44100) -> AudioData:
    """Decode any audio file ke PCM mono float32 via ffmpeg."""
    ff = find_ffmpeg()
    if not ff:
        raise RuntimeError("FFmpeg tidak ditemukan. Install via tombol di status bar.")
    path = str(path)
    cmd = [
        ff, "-v", "error", "-nostdin",
        "-i", path,
        "-ac", "1",
        "-ar", str(sr),
        "-f", "f32le",
        "-",
    ]
    _log.info("Decoding audio: %s @ %d Hz", Path(path).name, sr)
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="ignore")
        raise RuntimeError(f"FFmpeg gagal decode audio: {err.strip()[:400]}")
    data = np.frombuffer(proc.stdout, dtype=np.float32).copy()
    if data.size == 0:
        raise RuntimeError("Audio kosong / decode menghasilkan 0 sample.")
    duration = data.size / float(sr)
    _log.info("Audio decoded: %d samples (%.2fs)", data.size, duration)
    return AudioData(samples=data, sample_rate=sr, duration=duration)


# ===== Spectrum frames =====

def _logspace_bins(n_bands: int, low_hz: float, high_hz: float, sr: int, fft_size: int) -> np.ndarray:
    """Return integer FFT bin indices (length n_bands+1) untuk batas band log."""
    freqs = np.logspace(np.log10(low_hz), np.log10(high_hz), n_bands + 1)
    bins = (freqs * fft_size / sr).astype(np.int64)
    bins = np.clip(bins, 1, fft_size // 2)
    # ensure strictly increasing
    for i in range(1, bins.size):
        if bins[i] <= bins[i - 1]:
            bins[i] = bins[i - 1] + 1
    return np.clip(bins, 1, fft_size // 2)


class SpectrumExtractor:
    """Extract STFT magnitude untuk visualisasi.

    Membagi spektrum ke `n_bands` band logaritmik, lalu menyimpan magnitude
    setiap frame untuk durasi video.
    """

    def __init__(self,
                 audio: AudioData,
                 fps: int = 30,
                 n_bands: int = 64,
                 fft_size: int = 2048,
                 low_hz: float = 40.0,
                 high_hz: float = 16000.0,
                 smoothing: float = 0.55,
                 gain: float = 1.0):
        self.audio = audio
        self.fps = max(1, int(fps))
        self.n_bands = max(8, int(n_bands))
        self.fft_size = int(fft_size)
        self.low_hz = float(low_hz)
        self.high_hz = float(high_hz)
        self.smoothing = float(smoothing)
        self.gain = float(gain)

        sr = audio.sample_rate
        self.hop = max(1, sr // self.fps)
        self.bin_edges = _logspace_bins(self.n_bands, self.low_hz, self.high_hz, sr, self.fft_size)
        self.window = np.hanning(self.fft_size).astype(np.float32)

        self._cache: Optional[np.ndarray] = None
        self._envelope_cache: Optional[np.ndarray] = None
        self._beat_cache: Optional[np.ndarray] = None

    @property
    def n_frames(self) -> int:
        return int(np.ceil(self.audio.duration * self.fps))

    def compute_all(self, log_progress: bool = False) -> np.ndarray:
        """Return array shape (n_frames, n_bands) float32, range 0..~1."""
        if self._cache is not None:
            return self._cache

        x = self.audio.samples
        sr = self.audio.sample_rate
        N = self.fft_size
        hop = self.hop
        n_frames = self.n_frames

        # Pre-allocate
        out = np.zeros((n_frames, self.n_bands), dtype=np.float32)
        # Pre-emphasis-ish weighting (boost mid/high)
        edges = self.bin_edges
        # Loudness curve approximation per band
        center = (edges[:-1] + edges[1:]) / 2.0
        freq_center = center * sr / N
        weight = (freq_center / 1000.0) ** 0.35
        weight = weight / weight.max()
        weight = (0.55 + 0.45 * weight).astype(np.float32)

        # Pad audio
        pad = np.zeros(N, dtype=np.float32)
        padded = np.concatenate([pad, x, pad])

        prev = np.zeros(self.n_bands, dtype=np.float32)
        sm = self.smoothing
        gain = self.gain

        for fi in range(n_frames):
            start = fi * hop  # offset by N due to padding cancels because we use padded
            frame = padded[start:start + N]
            if frame.shape[0] < N:
                frame = np.pad(frame, (0, N - frame.shape[0]))
            # Window + FFT
            mag = np.abs(np.fft.rfft(frame * self.window))
            # Aggregate per band
            band = np.zeros(self.n_bands, dtype=np.float32)
            for i in range(self.n_bands):
                a, b = edges[i], edges[i + 1]
                if b <= a:
                    b = a + 1
                band[i] = mag[a:b].mean()
            # Normalise
            band /= (N / 4.0)
            # Perceptual / log compression
            band = np.log1p(band * 16.0) / np.log1p(16.0)
            band *= weight * gain
            # Smoothing (envelope follower)
            sm_arr = sm * prev + (1.0 - sm) * band
            # Attack faster than release for "lively" feel
            faster = np.maximum(band, sm_arr * 0.97)
            prev = faster
            out[fi] = np.clip(faster, 0.0, 1.5)

        # Per-track normalisasi: pakai persentil 95 dari max per frame supaya
        # tampilan terlihat punya range penuh tanpa kepotong terlalu sering.
        per_frame_max = out.max(axis=1)
        scale = float(np.percentile(per_frame_max, 95))
        if scale < 1e-3:
            scale = 1.0
        # target supaya p95 dari peak per-frame berada di ~0.85
        out *= (0.85 / scale)
        out = np.clip(out, 0.0, 1.2)

        self._cache = out
        if log_progress:
            _log.info("Spectrum extracted: %d frames x %d bands (norm scale=%.3f)",
                      n_frames, self.n_bands, scale)
        return out

    def envelope(self) -> np.ndarray:
        """Overall loudness envelope per video frame (0..1)."""
        if self._envelope_cache is not None:
            return self._envelope_cache
        spec = self.compute_all()
        env = spec.mean(axis=1)
        if env.max() > 0:
            env = env / max(env.max(), 1e-6)
        # Mild smoothing
        env = _ema(env, alpha=0.25)
        self._envelope_cache = env.astype(np.float32)
        return self._envelope_cache

    def beats(self, threshold: float = 0.55) -> np.ndarray:
        """Boolean per-frame beat events (peaks dari envelope)."""
        if self._beat_cache is not None:
            return self._beat_cache
        env = self.envelope()
        d = np.diff(env, prepend=env[0])
        peak = (d > 0.04) & (env > threshold)
        # debounce
        last = -10
        for i in range(peak.size):
            if peak[i]:
                if i - last < 5:
                    peak[i] = False
                else:
                    last = i
        self._beat_cache = peak.astype(bool)
        return self._beat_cache


def _ema(x: np.ndarray, alpha: float) -> np.ndarray:
    out = np.empty_like(x)
    acc = x[0]
    for i, v in enumerate(x):
        acc = alpha * v + (1 - alpha) * acc
        out[i] = acc
    return out
