"""Multi-channel FFmpeg streaming engine.

Each channel is wrapped in a :class:`StreamRuntime` which owns:

* the FFmpeg subprocess
* a dedicated playlist iterator
* a stdout/stderr reader thread that parses progress + log lines
* an auto-reconnect / auto-restart state machine

The :class:`StreamEngine` is a process-global facade that the UI and
remote control talk to.  All operations are thread-safe.
"""
from __future__ import annotations

import re
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..core.config import get_config
from ..core.events import Topics, event_bus
from ..core.exceptions import ChannelError, FFmpegMissingError, StreamError
from ..core.logger import get_logger
from ..db.base import get_db
from ..db.models import ChannelState
from ..db.repository import (
    AnalyticsRepository,
    ChannelRepository,
    LogRepository,
    PlaylistRepository,
    SessionRepository,
)
from ..security.crypto import get_crypto
from .ffmpeg_manager import get_ffmpeg_manager
from .playlist_engine import PlaylistEngine, get_playlist_engine

# FFmpeg progress lines look like "frame= 1234" / "bitrate=4500.1kbits/s" etc.
_PROGRESS_RE = re.compile(
    r"frame=\s*(?P<frame>\d+).*?fps=\s*(?P<fps>[\d.]+)"
    r".*?bitrate=\s*(?P<bitrate>[\d.]+)k.*?speed=\s*(?P<speed>[\d.]+)x",
    re.DOTALL,
)
_DROP_RE = re.compile(r"drop=\s*(\d+)|dup=\s*(\d+)")


@dataclass
class StreamStats:
    state: ChannelState = ChannelState.IDLE
    fps: float = 0.0
    bitrate_kbps: float = 0.0
    speed: float = 0.0
    frames: int = 0
    dropped: int = 0
    started_at: datetime | None = None
    last_update: datetime | None = None
    reconnects: int = 0
    uptime_sec: float = 0.0
    current_track: str = ""
    current_track_index: int = -1
    last_error: str = ""

    @property
    def is_active(self) -> bool:
        return self.state in {
            ChannelState.LIVE,
            ChannelState.STARTING,
            ChannelState.RECONNECTING,
            ChannelState.PAUSED,
        }


class StreamRuntime:
    """One-per-channel runtime that drives a single FFmpeg process."""

    def __init__(self, engine: StreamEngine, channel_id: int) -> None:
        self._engine = engine
        self._log = get_logger(f"stream.{channel_id}")
        self._channel_id = channel_id
        self._proc: subprocess.Popen[bytes] | None = None
        self._concat_path: Path | None = None
        self._reader_thread: threading.Thread | None = None
        self._supervisor_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._restart_requested = threading.Event()
        self._lock = threading.RLock()
        self._stats = StreamStats()
        self._cumulative_bitrate = 0.0
        self._cumulative_fps = 0.0
        self._sample_count = 0
        self._session_id: int | None = None

    # ------------------------------------------------------------------
    @property
    def channel_id(self) -> int:
        return self._channel_id

    @property
    def stats(self) -> StreamStats:
        return self._stats

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    # ------------------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self.is_running:
                return
            self._stop_event.clear()
            self._pause_event.clear()
            self._restart_requested.clear()
            self._supervisor_thread = threading.Thread(
                target=self._supervise, name=f"stream-sup-{self._channel_id}", daemon=True
            )
            self._supervisor_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            proc = self._proc
        if proc is not None and proc.poll() is None:
            self._terminate_process(proc)

    def restart(self) -> None:
        self._restart_requested.set()
        with self._lock:
            proc = self._proc
        if proc is not None and proc.poll() is None:
            self._terminate_process(proc)

    def pause(self) -> None:
        """Soft pause = stop FFmpeg without releasing the runtime."""
        if not self.is_running:
            return
        self._pause_event.set()
        with self._lock:
            proc = self._proc
        if proc is not None and proc.poll() is None:
            self._terminate_process(proc)
        self._set_state(ChannelState.PAUSED)

    def resume(self) -> None:
        self._pause_event.clear()
        self._restart_requested.set()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _supervise(self) -> None:
        channel = self._engine.channels.get(self._channel_id)
        if channel is None:
            self._set_state(ChannelState.ERROR, error=f"Channel {self._channel_id} not found")
            return
        self._stats = StreamStats(
            state=ChannelState.STARTING, started_at=datetime.utcnow()
        )
        self._publish_state(ChannelState.STARTING)
        sessions = SessionRepository(get_db())
        analytics = AnalyticsRepository(get_db())
        self._session_id = sessions.open(self._channel_id)
        analytics.add("channel.start", channel_id=self._channel_id, payload={"name": channel.name})
        backoff = 2

        try:
            while not self._stop_event.is_set():
                if self._pause_event.is_set():
                    time.sleep(0.5)
                    continue
                try:
                    self._run_once()
                    backoff = 2
                except FFmpegMissingError as exc:
                    self._set_state(ChannelState.ERROR, error=str(exc))
                    break
                except StreamError as exc:
                    self._stats.last_error = str(exc)
                    self._log.warning("Stream error: %s", exc)
                except Exception as exc:  # noqa: BLE001
                    self._stats.last_error = str(exc)
                    self._log.exception("Unexpected stream failure")
                if self._stop_event.is_set() or self._pause_event.is_set():
                    break
                channel = self._engine.channels.get(self._channel_id)
                if channel is None or not channel.auto_restart:
                    break
                self._stats.reconnects += 1
                self._set_state(ChannelState.RECONNECTING)
                event_bus.publish(
                    Topics.WATCHDOG_EVENT,
                    {"channel_id": self._channel_id, "action": "reconnect", "backoff": backoff},
                )
                for _ in range(backoff * 2):
                    if self._stop_event.is_set():
                        break
                    time.sleep(0.5)
                backoff = min(backoff * 2, 60)
        finally:
            self._cleanup_concat()
            sessions.close(
                self._session_id or 0,
                avg_bitrate=self._average_bitrate(),
                avg_fps=self._average_fps(),
                dropped=self._stats.dropped,
                reconnects=self._stats.reconnects,
                ok=self._stop_event.is_set() and not self._stats.last_error,
                error=self._stats.last_error,
            )
            analytics.add(
                "channel.stop",
                channel_id=self._channel_id,
                payload={"reconnects": self._stats.reconnects, "duration": self._stats.uptime_sec},
            )
            if not self._pause_event.is_set():
                self._set_state(ChannelState.IDLE)

    def _run_once(self) -> None:
        ffmpeg = get_ffmpeg_manager()
        if not ffmpeg.is_ready:
            ffmpeg.refresh()
        if not ffmpeg.is_ready:
            raise FFmpegMissingError("FFmpeg is not installed or unreachable.")

        channel = self._engine.channels.get(self._channel_id)
        if channel is None:
            raise ChannelError("Channel disappeared")
        crypto = get_crypto()
        stream_key = crypto.safe_decrypt(channel.stream_key_encrypted, "")
        rtmp_url = channel.rtmp_url.rstrip("/")
        if "{key}" in rtmp_url:
            target = rtmp_url.format(key=stream_key)
        elif stream_key:
            target = f"{rtmp_url}/{stream_key}"
        else:
            target = rtmp_url

        playlist_files = self._engine.playlist_files(self._channel_id)
        if not playlist_files:
            raise StreamError("Channel has no playlist items to stream.")
        concat_path = self._write_concat_list(playlist_files, channel.loop_playlist)
        self._concat_path = concat_path

        args = self._build_command(ffmpeg.info.binary, channel, concat_path, target)
        self._log.info("Launching ffmpeg: %s", " ".join(shlex.quote(a) for a in args))
        LogRepository(get_db()).add(
            f"Starting stream: {' '.join(shlex.quote(a) for a in args[:6])}…",
            level="INFO",
            source="ffmpeg",
            channel_id=self._channel_id,
        )

        creationflags = 0
        if sys.platform == "win32":  # avoid console flash on Windows
            creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

        proc = subprocess.Popen(  # noqa: S603
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            bufsize=1024 * 1024,
            creationflags=creationflags,
            close_fds=sys.platform != "win32",
        )
        with self._lock:
            self._proc = proc
        self._set_state(ChannelState.LIVE)
        self._reader_thread = threading.Thread(
            target=self._reader,
            args=(proc,),
            daemon=True,
            name=f"stream-rd-{self._channel_id}",
        )
        self._reader_thread.start()

        rc = proc.wait()
        self._log.info("ffmpeg exited (rc=%s)", rc)
        if self._restart_requested.is_set():
            self._restart_requested.clear()
            return  # supervisor will loop and restart
        if rc != 0 and not self._stop_event.is_set() and not self._pause_event.is_set():
            raise StreamError(f"FFmpeg exited with code {rc}")

    def _reader(self, proc: subprocess.Popen[bytes]) -> None:
        log_repo = LogRepository(get_db())
        for raw in iter(proc.stdout.readline, b""):  # type: ignore[union-attr]
            line = raw.decode("utf-8", errors="ignore").rstrip()
            if not line:
                continue
            self._log.debug("%s", line)
            event_bus.publish(
                Topics.STREAM_LOG,
                {"channel_id": self._channel_id, "line": line, "ts": time.time()},
            )
            # persist a sample of FFmpeg lines so the log viewer has data
            if any(tag in line for tag in ("Error", "error", "warning", "fatal")):
                log_repo.add(line, level="WARN", source="ffmpeg", channel_id=self._channel_id)
            self._parse_progress(line)
        # process ended
        try:
            proc.stdout.close()  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass

    def _parse_progress(self, line: str) -> None:
        m = _PROGRESS_RE.search(line)
        if m:
            fps = float(m.group("fps") or 0)
            bitrate = float(m.group("bitrate") or 0)
            speed = float(m.group("speed") or 0)
            frames = int(m.group("frame") or 0)
            self._stats.fps = fps
            self._stats.bitrate_kbps = bitrate
            self._stats.speed = speed
            self._stats.frames = frames
            self._stats.last_update = datetime.utcnow()
            if self._stats.started_at:
                self._stats.uptime_sec = (
                    datetime.utcnow() - self._stats.started_at
                ).total_seconds()
            if fps > 0:
                self._cumulative_fps += fps
                self._sample_count += 1
            if bitrate > 0:
                self._cumulative_bitrate += bitrate
            event_bus.publish(
                Topics.STREAM_STATS,
                {
                    "channel_id": self._channel_id,
                    "fps": fps,
                    "bitrate_kbps": bitrate,
                    "speed": speed,
                    "frames": frames,
                    "uptime_sec": self._stats.uptime_sec,
                    "reconnects": self._stats.reconnects,
                    "state": self._stats.state.value,
                    "dropped": self._stats.dropped,
                },
            )
        dm = _DROP_RE.search(line)
        if dm:
            try:
                drop_val = int(dm.group(1) or 0)
                self._stats.dropped += drop_val
            except (TypeError, ValueError):
                pass

    def _build_command(
        self, ffmpeg: str, channel, concat_path: Path, target_url: str
    ) -> list[str]:
        cfg = get_config().config.streaming
        resolution = channel.resolution or cfg.resolution
        fps = channel.fps or cfg.fps
        v_bitrate = channel.video_bitrate_kbps or cfg.video_bitrate_kbps
        a_bitrate = channel.audio_bitrate_kbps or cfg.audio_bitrate_kbps
        gop = max(1, (channel.keyframe_interval_sec or cfg.keyframe_interval_sec) * fps)
        preset = channel.preset or cfg.preset

        # Hardware-accelerated codec mapping
        hw_choice = (channel.hw_accel or cfg.hw_accel or "auto").lower()
        video_codec = channel.video_codec or cfg.video_codec
        codec_map = {
            "nvenc": "h264_nvenc",
            "qsv": "h264_qsv",
            "amf": "h264_amf",
            "videotoolbox": "h264_videotoolbox",
            "vaapi": "h264_vaapi",
        }
        if hw_choice == "auto":
            from ..utils.platform_utils import detect_gpu

            best = detect_gpu().best_encoder
            video_codec = codec_map.get(best, video_codec)
        elif hw_choice in codec_map:
            video_codec = codec_map[hw_choice]
        elif hw_choice == "none":
            video_codec = video_codec or "libx264"

        args = [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-loglevel",
            "info",
            "-re",
            "-fflags",
            "+genpts",
            "-stream_loop",
            "-1" if channel.loop_playlist else "0",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-vf",
            f"scale={resolution.replace('x', ':')}:flags=lanczos,format={cfg.pixel_format}",
            "-r",
            str(fps),
            "-g",
            str(gop),
            "-keyint_min",
            str(gop),
            "-c:v",
            video_codec,
            "-b:v",
            f"{v_bitrate}k",
            "-maxrate",
            f"{v_bitrate}k",
            "-bufsize",
            f"{v_bitrate * 2}k",
            "-preset",
            preset,
            "-c:a",
            channel.audio_codec or cfg.audio_codec,
            "-b:a",
            f"{a_bitrate}k",
            "-ar",
            str(cfg.audio_sample_rate),
            "-ac",
            "2",
        ]
        if cfg.normalize_audio:
            # Append a loudnorm filter on top of the audio stream.
            args.extend(["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"])
        # Quality knobs for libx264-style codecs
        if video_codec == "libx264":
            args.extend(["-profile:v", cfg.profile, "-tune", "zerolatency"])
        args.extend(["-f", "flv", target_url])
        return args

    def _write_concat_list(self, files: Iterable[str], loop: bool) -> Path:
        # FFmpeg's concat demuxer needs absolute paths and proper quoting.
        target = Path(tempfile.mkstemp(prefix="asmr-concat-", suffix=".txt")[1])
        with target.open("w", encoding="utf-8") as fh:
            for f in files:
                escaped = str(Path(f)).replace("'", "'\\''")
                fh.write(f"file '{escaped}'\n")
        return target

    def _cleanup_concat(self) -> None:
        if self._concat_path and self._concat_path.exists():
            try:
                self._concat_path.unlink()
            except OSError:
                pass
        self._concat_path = None

    def _set_state(self, state: ChannelState, error: str = "") -> None:
        self._stats.state = state
        if error:
            self._stats.last_error = error
        ChannelRepository(get_db()).set_state(self._channel_id, state, error)
        self._publish_state(state, error)

    def _publish_state(self, state: ChannelState, error: str = "") -> None:
        event_bus.publish(
            Topics.STREAM_STATE,
            {
                "channel_id": self._channel_id,
                "state": state.value,
                "error": error,
                "ts": time.time(),
            },
        )

    @staticmethod
    def _terminate_process(proc: subprocess.Popen[bytes]) -> None:
        try:
            if sys.platform == "win32":
                proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            else:
                proc.terminate()
            proc.wait(timeout=8)
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                pass

    def _average_bitrate(self) -> float:
        if self._sample_count == 0:
            return 0.0
        return self._cumulative_bitrate / max(self._sample_count, 1)

    def _average_fps(self) -> float:
        if self._sample_count == 0:
            return 0.0
        return self._cumulative_fps / max(self._sample_count, 1)


class StreamEngine:
    """Process-wide coordinator for all :class:`StreamRuntime` objects."""

    def __init__(self) -> None:
        self._log = get_logger("stream.engine")
        self._runtimes: dict[int, StreamRuntime] = {}
        self._lock = threading.RLock()
        self._channels = ChannelRepository(get_db())
        self._playlists = PlaylistRepository(get_db())
        self._playlist_engine: PlaylistEngine = get_playlist_engine()

    # ------------------------------------------------------------------
    @property
    def channels(self):
        """Lightweight cache wrapper around the repository."""
        class _Cache:
            def __init__(self, repo: ChannelRepository) -> None:
                self._repo = repo

            def get(self, cid):
                return self._repo.get(cid)

            def all(self):
                return self._repo.list()

        return _Cache(self._channels)

    def playlist_files(self, channel_id: int) -> list[str]:
        return self._playlist_engine.materialise_for_channel(channel_id)

    def is_running(self, channel_id: int) -> bool:
        with self._lock:
            rt = self._runtimes.get(channel_id)
        return bool(rt and rt.is_running)

    def runtime(self, channel_id: int) -> StreamRuntime:
        with self._lock:
            rt = self._runtimes.get(channel_id)
            if rt is None:
                rt = StreamRuntime(self, channel_id)
                self._runtimes[channel_id] = rt
            return rt

    def start(self, channel_id: int) -> None:
        self.runtime(channel_id).start()

    def stop(self, channel_id: int) -> None:
        with self._lock:
            rt = self._runtimes.get(channel_id)
        if rt:
            rt.stop()

    def restart(self, channel_id: int) -> None:
        self.runtime(channel_id).restart()

    def pause(self, channel_id: int) -> None:
        with self._lock:
            rt = self._runtimes.get(channel_id)
        if rt:
            rt.pause()

    def resume(self, channel_id: int) -> None:
        self.runtime(channel_id).resume()

    def start_all_enabled(self) -> int:
        count = 0
        for ch in self._channels.list():
            if ch.enabled:
                self.start(ch.id)
                count += 1
        return count

    def stop_all(self) -> None:
        with self._lock:
            runtimes = list(self._runtimes.values())
        for rt in runtimes:
            rt.stop()

    def snapshot(self) -> dict[int, StreamStats]:
        with self._lock:
            return {cid: rt.stats for cid, rt in self._runtimes.items()}


_GLOBAL: StreamEngine | None = None


def get_stream_engine() -> StreamEngine:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = StreamEngine()
    return _GLOBAL
