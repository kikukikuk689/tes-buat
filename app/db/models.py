"""ORM models for channels, playlists, schedules, logs, analytics, settings."""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


def _now() -> datetime:
    return datetime.utcnow()


class ChannelState(str, enum.Enum):
    IDLE = "idle"
    STARTING = "starting"
    LIVE = "live"
    PAUSED = "paused"
    RECONNECTING = "reconnecting"
    STOPPING = "stopping"
    ERROR = "error"


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(40), default="youtube")  # youtube/twitch/facebook/tiktok/custom
    rtmp_url: Mapped[str] = mapped_column(String(512), nullable=False)
    stream_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    thumbnail_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(Text, default="")  # comma separated
    category: Mapped[str] = mapped_column(String(60), default="")
    metadata_json: Mapped[dict | None] = mapped_column(JSON, default=dict)

    # Encoder + streaming defaults overrides
    resolution: Mapped[str] = mapped_column(String(20), default="1920x1080")
    fps: Mapped[int] = mapped_column(Integer, default=30)
    video_bitrate_kbps: Mapped[int] = mapped_column(Integer, default=4500)
    audio_bitrate_kbps: Mapped[int] = mapped_column(Integer, default=160)
    preset: Mapped[str] = mapped_column(String(30), default="veryfast")
    hw_accel: Mapped[str] = mapped_column(String(20), default="auto")
    video_codec: Mapped[str] = mapped_column(String(30), default="libx264")
    audio_codec: Mapped[str] = mapped_column(String(30), default="aac")
    pixel_format: Mapped[str] = mapped_column(String(20), default="yuv420p")
    keyframe_interval_sec: Mapped[int] = mapped_column(Integer, default=2)

    # Behaviour
    auto_restart: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_reconnect: Mapped[bool] = mapped_column(Boolean, default=True)
    loop_playlist: Mapped[bool] = mapped_column(Boolean, default=True)
    shuffle: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Linked playlist
    playlist_id: Mapped[int | None] = mapped_column(
        ForeignKey("playlists.id", ondelete="SET NULL"), nullable=True
    )
    playlist: Mapped[Playlist | None] = relationship(back_populates="channels")

    # Schedule slots
    schedules: Mapped[list[Schedule]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )

    last_state: Mapped[ChannelState] = mapped_column(
        Enum(ChannelState, native_enum=False), default=ChannelState.IDLE
    )
    last_error: Mapped[str] = mapped_column(Text, default="")
    total_seconds: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Playlist(Base):
    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    shuffle: Mapped[bool] = mapped_column(Boolean, default=False)
    loop: Mapped[bool] = mapped_column(Boolean, default=True)
    crossfade_ms: Mapped[int] = mapped_column(Integer, default=0)
    normalize_audio: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    items: Mapped[list[PlaylistItem]] = relationship(
        back_populates="playlist", cascade="all, delete-orphan", order_by="PlaylistItem.position"
    )
    channels: Mapped[list[Channel]] = relationship(back_populates="playlist")


class PlaylistItem(Base):
    __tablename__ = "playlist_items"
    __table_args__ = (UniqueConstraint("playlist_id", "path", name="uq_playlist_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    playlist_id: Mapped[int] = mapped_column(
        ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="")
    duration_sec: Mapped[float] = mapped_column(Float, default=0.0)
    position: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    playlist: Mapped[Playlist] = relationship(back_populates="items")


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(120), default="")
    # Either a one-shot UTC datetime or a cron-style trigger.
    start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stop_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cron_start: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cron_stop: Mapped[str | None] = mapped_column(String(120), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_fire_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    channel: Mapped[Channel] = relationship(back_populates="schedules")


class StreamSession(Base):
    __tablename__ = "stream_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_sec: Mapped[float] = mapped_column(Float, default=0.0)
    average_bitrate_kbps: Mapped[float] = mapped_column(Float, default=0.0)
    average_fps: Mapped[float] = mapped_column(Float, default=0.0)
    dropped_frames: Mapped[int] = mapped_column(Integer, default=0)
    reconnects: Mapped[int] = mapped_column(Integer, default=0)
    finished_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str] = mapped_column(Text, default="")


class LogEntry(Base):
    __tablename__ = "log_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    level: Mapped[str] = mapped_column(String(16), default="INFO", index=True)
    source: Mapped[str] = mapped_column(String(64), default="app", index=True)
    channel_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    event: Mapped[str] = mapped_column(String(80), index=True)
    channel_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, default=dict)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
