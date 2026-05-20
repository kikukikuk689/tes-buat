"""Database layer (SQLAlchemy 2.x + SQLite)."""

from .base import Database, get_db
from .models import (
    AnalyticsEvent,
    Channel,
    ChannelState,
    LogEntry,
    Playlist,
    PlaylistItem,
    Schedule,
    Setting,
    StreamSession,
)
from .repository import (
    AnalyticsRepository,
    ChannelRepository,
    LogRepository,
    PlaylistRepository,
    ScheduleRepository,
    SessionRepository,
    SettingsRepository,
)

__all__ = [
    "Database",
    "get_db",
    "AnalyticsEvent",
    "Channel",
    "ChannelState",
    "LogEntry",
    "Playlist",
    "PlaylistItem",
    "Schedule",
    "StreamSession",
    "Setting",
    "AnalyticsRepository",
    "ChannelRepository",
    "LogRepository",
    "PlaylistRepository",
    "ScheduleRepository",
    "SessionRepository",
    "SettingsRepository",
]
