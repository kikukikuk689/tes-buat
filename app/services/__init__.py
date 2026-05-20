"""Service layer."""

from .ai_service import AIService, get_ai
from .backup import BackupService, get_backup
from .ffmpeg_manager import FFmpegManager, FFmpegState, get_ffmpeg_manager
from .monitor import MonitorService, SystemStats, get_monitor
from .network import NetworkMonitor, get_network_monitor
from .notification import NotificationCenter, get_notifier
from .playlist_engine import PlaylistEngine, get_playlist_engine
from .remote import RemoteControlServer, get_remote_server
from .scheduler import SchedulerService, get_scheduler
from .stream_engine import StreamEngine, StreamRuntime, get_stream_engine
from .tray import SystemTrayService
from .watchdog_service import WatchdogService, get_watchdog
from .youtube import YouTubeService, get_youtube

__all__ = [
    "FFmpegManager",
    "FFmpegState",
    "get_ffmpeg_manager",
    "StreamEngine",
    "StreamRuntime",
    "get_stream_engine",
    "PlaylistEngine",
    "get_playlist_engine",
    "MonitorService",
    "SystemStats",
    "get_monitor",
    "WatchdogService",
    "get_watchdog",
    "NetworkMonitor",
    "get_network_monitor",
    "NotificationCenter",
    "get_notifier",
    "BackupService",
    "get_backup",
    "SchedulerService",
    "get_scheduler",
    "RemoteControlServer",
    "get_remote_server",
    "SystemTrayService",
    "YouTubeService",
    "get_youtube",
    "AIService",
    "get_ai",
]
