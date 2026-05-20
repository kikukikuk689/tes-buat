"""Application bootstrap.

Wires together: configuration, logging, database, services, UI.  Called
from :mod:`main`.  All long-lived background services are owned here and
shut down cleanly on exit.
"""
from __future__ import annotations

import logging
import signal
from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from .core.config import get_config
from .core.logger import setup_logging
from .core.paths import paths
from .db.base import get_db
from .security import get_license_manager
from .services import (
    SystemTrayService,
    get_backup,
    get_ffmpeg_manager,
    get_monitor,
    get_network_monitor,
    get_notifier,
    get_remote_server,
    get_scheduler,
    get_stream_engine,
    get_watchdog,
)
from .ui.main_window import MainWindow
from .ui.theme import ThemeManager

_log: logging.Logger | None = None


def _shutdown_services() -> None:
    """Best-effort teardown of every long-lived service."""
    actions = [
        ("stream engine", lambda: get_stream_engine().stop_all()),
        ("watchdog", lambda: get_watchdog().stop()),
        ("scheduler", lambda: get_scheduler().stop()),
        ("backup", lambda: get_backup().stop_auto()),
        ("network", lambda: get_network_monitor().stop()),
        ("monitor", lambda: get_monitor().stop()),
        ("remote", lambda: get_remote_server().stop()),
    ]
    for name, fn in actions:
        try:
            fn()
        except Exception:  # noqa: BLE001
            if _log:
                _log.exception("Error stopping %s", name)


def _install_signal_handlers(app: QApplication) -> None:
    def _sig(*_):  # noqa: ANN001
        app.quit()

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(s, _sig)
        except (ValueError, OSError):  # SIGTERM may not be available on Windows non-main threads
            continue


def run(argv: Sequence[str]) -> int:
    setup_logging(paths.logs_dir)
    global _log
    _log = logging.getLogger("app")
    _log.info("Starting ASMR Broadcast Studio")

    # Initialise config + database early so the rest of the wiring can rely on them
    config_manager = get_config()
    _log.info("Config loaded from %s", config_manager.path)
    get_db().init()
    get_license_manager()  # boots trial timer

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(list(argv))
    app.setApplicationName("ASMR Broadcast Studio")
    app.setOrganizationName("ASMR Broadcast Studio")
    app.setQuitOnLastWindowClosed(False)  # tray keeps app alive
    icon_path = paths.icons_dir / "studio.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    theme_manager = ThemeManager()
    theme_manager.apply(app)

    window = MainWindow(theme_manager)

    # Start background services (after window exists so they can publish events)
    get_ffmpeg_manager().refresh()
    get_monitor().start()
    get_network_monitor().start()
    get_scheduler().start()
    get_watchdog().start()
    if get_config().config.remote.enabled:
        try:
            get_remote_server().start()
        except Exception:  # noqa: BLE001
            _log.exception("Failed to start remote control")
    if get_config().config.backup.auto_backup:
        try:
            get_backup().start_auto()
        except Exception:  # noqa: BLE001
            _log.exception("Auto-backup failed")

    # Tray
    tray: SystemTrayService | None = None
    if SystemTrayService.is_available():
        try:
            tray = SystemTrayService(
                icon_path=str(icon_path),
                on_show=window.showNormal,
                on_quit=app.quit,
                on_start_all=lambda: get_stream_engine().start_all_enabled(),
                on_stop_all=lambda: get_stream_engine().stop_all(),
            )
            window.attach_tray(tray)
        except Exception:  # noqa: BLE001
            _log.exception("Failed to install system tray")

    window.show()

    # FFmpeg first-run nudge
    ff = get_ffmpeg_manager().info
    if ff.state.value != "ready":
        get_notifier().notify(
            "FFmpeg not detected",
            "Open the FFmpeg Manager page to download and install FFmpeg.",
            "warning",
            duration_ms=8000,
        )

    _install_signal_handlers(app)

    try:
        exit_code = app.exec()
    finally:
        _shutdown_services()
        if tray is not None:
            tray.shutdown()
    return int(exit_code)
