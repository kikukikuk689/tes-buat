"""Main application window: frameless + sidebar + page stack."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.config import get_config
from ..core.events import Topics, event_bus
from ..core.paths import paths
from ..services import (
    SystemTrayService,
    get_notifier,
    get_stream_engine,
)
from .pages import (
    AnalyticsPage,
    ApiManagerPage,
    BackupPage,
    DashboardPage,
    EncoderPage,
    FFmpegPage,
    LicensePage,
    LiveManagerPage,
    LogsPage,
    MultiChannelPage,
    PlaylistManagerPage,
    RemotePage,
    SchedulerPage,
    SettingsPage,
    ThemePage,
)
from .sidebar import NavItem, Sidebar
from .theme import ThemeManager
from .title_bar import TitleBar
from .widgets import ToastStack

NAV: list[NavItem] = [
    NavItem("dashboard", "Dashboard", "■"),
    NavItem("live", "Live Manager", "▶"),
    NavItem("channels", "Multi Channel", "⌥"),
    NavItem("playlists", "Playlists", "♬"),
    NavItem("scheduler", "Scheduler", "⏱"),
    NavItem("ffmpeg", "FFmpeg", "⚙"),
    NavItem("encoder", "Encoder", "↯"),
    NavItem("logs", "Logs", "≡"),
    NavItem("analytics", "Analytics", "▦"),
    NavItem("settings", "Settings", "✦"),
    NavItem("api", "API Manager", "✺"),
    NavItem("backup", "Backup", "⎘"),
    NavItem("license", "License", "♦"),
    NavItem("remote", "Remote Control", "☰"),
    NavItem("theme", "Themes", "✷"),
]


class MainWindow(QMainWindow):
    def __init__(self, theme_manager: ThemeManager) -> None:
        super().__init__()
        self.setObjectName("rootWindow")
        self.setWindowTitle("ASMR Broadcast Studio")
        self.resize(1320, 820)
        self.setMinimumSize(1100, 720)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        icon_path = str(paths.icons_dir / "studio.svg")
        self.setWindowIcon(QIcon(icon_path))
        self._theme = theme_manager
        self._tray: SystemTrayService | None = None
        self._maximised_geometry = None

        central = QFrame()
        central.setObjectName("centralWrap")
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.title_bar = TitleBar(self, "ASMR Broadcast Studio", "Premium 24/7 broadcasting engine")
        layout.addWidget(self.title_bar)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.sidebar = Sidebar(NAV)
        body.addWidget(self.sidebar)

        self.pages = QStackedWidget()
        self.pages.setObjectName("pageStack")
        self._page_keys: dict[str, QWidget] = {}
        self._build_pages()
        body.addWidget(self.pages, 1)
        layout.addLayout(body)
        self.setCentralWidget(central)

        self.toast_stack = ToastStack(self)

        # Wire
        self.sidebar.pageChanged.connect(self.show_page)
        self.title_bar.minimizeClicked.connect(self.showMinimized)
        self.title_bar.maximizeClicked.connect(self.toggle_maximised)
        self.title_bar.closeClicked.connect(self.close)
        event_bus.subscribe(
            Topics.NOTIFICATION,
            lambda p: QTimer.singleShot(0, lambda: self._on_notification(p)),
        )
        event_bus.subscribe(
            Topics.STREAM_STATE,
            lambda p: QTimer.singleShot(0, lambda: self._refresh_status_bar()),
        )
        event_bus.subscribe(
            Topics.NETWORK_STATE,
            lambda p: QTimer.singleShot(0, lambda: self._refresh_status_bar(p)),
        )

        # initial state
        self.sidebar.select("dashboard")
        self.show_page("dashboard")
        self._refresh_status_bar()

    # ------------------------------------------------------------------
    def attach_tray(self, tray: SystemTrayService) -> None:
        self._tray = tray

    def show_page(self, key: str) -> None:
        widget = self._page_keys.get(key)
        if widget is None:
            return
        for k, w in self._page_keys.items():
            if hasattr(w, "on_hide") and k != key:
                w.on_hide()
        self.pages.setCurrentWidget(widget)
        if hasattr(widget, "on_show"):
            widget.on_show()

    def toggle_maximised(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def show_toast(self, title: str, message: str, severity: str = "info", duration_ms: int = 4500) -> None:
        self.toast_stack.show_toast(title, message, severity, duration_ms)

    # ------------------------------------------------------------------
    def _build_pages(self) -> None:
        self.dashboard = DashboardPage()
        self.live_manager = LiveManagerPage()
        self.multi_channel = MultiChannelPage()
        self.playlists = PlaylistManagerPage()
        self.scheduler = SchedulerPage()
        self.ffmpeg = FFmpegPage()
        self.encoder = EncoderPage()
        self.logs = LogsPage()
        self.analytics = AnalyticsPage()
        self.settings = SettingsPage()
        self.api = ApiManagerPage()
        self.backup = BackupPage()
        self.license = LicensePage()
        self.remote = RemotePage()
        self.theme_page = ThemePage(self._theme)
        mapping = {
            "dashboard": self.dashboard,
            "live": self.live_manager,
            "channels": self.multi_channel,
            "playlists": self.playlists,
            "scheduler": self.scheduler,
            "ffmpeg": self.ffmpeg,
            "encoder": self.encoder,
            "logs": self.logs,
            "analytics": self.analytics,
            "settings": self.settings,
            "api": self.api,
            "backup": self.backup,
            "license": self.license,
            "remote": self.remote,
            "theme": self.theme_page,
        }
        for key, widget in mapping.items():
            self.pages.addWidget(widget)
            self._page_keys[key] = widget

    def _on_notification(self, payload: dict) -> None:
        self.show_toast(
            payload.get("title", ""),
            payload.get("message", ""),
            payload.get("severity", "info"),
            int(payload.get("duration_ms", 4500)),
        )
        if self._tray is not None:
            self._tray.notify(
                payload.get("title", ""),
                payload.get("message", ""),
                payload.get("severity", "info"),
            )

    def _refresh_status_bar(self, network_payload: dict | None = None) -> None:
        engine = get_stream_engine()
        snap = engine.snapshot()
        active = sum(1 for s in snap.values() if s.is_active)
        if active == 0:
            self.title_bar.set_status("System idle", "idle")
        else:
            self.title_bar.set_status(f"{active} channel(s) live", "live")
        if network_payload and not network_payload.get("silent"):
            if not network_payload.get("online"):
                self.title_bar.set_status("Internet offline", "error")

    # ------------------------------------------------------------------
    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        cfg = get_config().config.general
        if cfg.close_to_tray and self._tray is not None:
            event.ignore()
            self.hide()
            get_notifier().notify(
                "ASMR Studio",
                "Application still running in the system tray.",
                "info",
            )
            return
        super().closeEvent(event)
