"""ffprobe wrapper to extract duration / codec info from media files."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..core.logger import get_logger

_log = get_logger("ffprobe")


@dataclass
class MediaInfo:
    path: str
    duration_sec: float
    has_video: bool
    has_audio: bool
    width: int
    height: int
    video_codec: str
    audio_codec: str
    bitrate_kbps: float

    @classmethod
    def unknown(cls, path: str) -> MediaInfo:
        return cls(
            path=path,
            duration_sec=0.0,
            has_video=False,
            has_audio=False,
            width=0,
            height=0,
            video_codec="",
            audio_codec="",
            bitrate_kbps=0.0,
        )


def probe_media(media_path: str | Path, ffprobe_bin: str = "ffprobe") -> MediaInfo:
    """Probe a media file with ``ffprobe`` and return :class:`MediaInfo`.

    Returns ``MediaInfo.unknown(path)`` if probing fails for any reason
    (so callers can degrade gracefully rather than raise).
    """
    path = str(media_path)
    cmd = [
        ffprobe_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        path,
    ]
    try:
        result = subprocess.run(  # noqa: S603
            cmd, check=False, capture_output=True, text=True, timeout=20
        )
        if result.returncode != 0:
            _log.debug("ffprobe failed for %s: %s", path, result.stderr.strip())
            return MediaInfo.unknown(path)
        info = json.loads(result.stdout or "{}")
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        _log.debug("ffprobe unavailable for %s: %s", path, exc)
        return MediaInfo.unknown(path)

    fmt = info.get("format", {}) or {}
    streams = info.get("streams", []) or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = float(fmt.get("duration") or (video and video.get("duration")) or 0.0 or 0.0)
    bitrate_kbps = float(fmt.get("bit_rate") or 0) / 1000.0
    return MediaInfo(
        path=path,
        duration_sec=duration,
        has_video=video is not None,
        has_audio=audio is not None,
        width=int(video.get("width") or 0) if video else 0,
        height=int(video.get("height") or 0) if video else 0,
        video_codec=(video or {}).get("codec_name", ""),
        audio_codec=(audio or {}).get("codec_name", ""),
        bitrate_kbps=bitrate_kbps,
    )
