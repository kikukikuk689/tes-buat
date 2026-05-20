"""All application pages."""

from .analytics_page import AnalyticsPage
from .api_page import ApiManagerPage
from .backup_page import BackupPage
from .base_page import BasePage
from .dashboard import DashboardPage
from .encoder_page import EncoderPage
from .ffmpeg_page import FFmpegPage
from .license_page import LicensePage
from .live_manager_page import LiveManagerPage
from .logs_page import LogsPage
from .multi_channel_page import MultiChannelPage
from .playlist_manager_page import PlaylistManagerPage
from .remote_page import RemotePage
from .scheduler_page import SchedulerPage
from .settings_page import SettingsPage
from .theme_page import ThemePage

__all__ = [
    "AnalyticsPage",
    "ApiManagerPage",
    "BackupPage",
    "BasePage",
    "DashboardPage",
    "EncoderPage",
    "FFmpegPage",
    "LicensePage",
    "LiveManagerPage",
    "LogsPage",
    "MultiChannelPage",
    "PlaylistManagerPage",
    "RemotePage",
    "SchedulerPage",
    "SettingsPage",
    "ThemePage",
]
