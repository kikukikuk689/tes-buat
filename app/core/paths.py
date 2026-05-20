"""Cross-platform application paths.

Centralises every filesystem location used by the application so that the
rest of the codebase never has to reason about the difference between a
development checkout and an installed/frozen build.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

APP_SLUG = "ASMRBroadcastStudio"


def _platform_data_root() -> Path:
    """Return the per-user writable directory for this app."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
        return Path(base) / APP_SLUG
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_SLUG
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / APP_SLUG


def _resources_root() -> Path:
    """Return the directory containing bundled resources.

    When frozen by Nuitka the resources live alongside the binary; in dev
    they live in the repo root next to ``main.py``.
    """
    if getattr(sys, "frozen", False):  # pragma: no cover - frozen build
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AppPaths:
    """Resolved set of application paths."""

    data_root: Path
    resources_root: Path

    @cached_property
    def logs_dir(self) -> Path:
        p = self.data_root / "logs"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @cached_property
    def db_path(self) -> Path:
        self.data_root.mkdir(parents=True, exist_ok=True)
        return self.data_root / "studio.db"

    @cached_property
    def backups_dir(self) -> Path:
        p = self.data_root / "backups"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @cached_property
    def cache_dir(self) -> Path:
        p = self.data_root / "cache"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @cached_property
    def ffmpeg_dir(self) -> Path:
        p = self.data_root / "ffmpeg"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @cached_property
    def thumbnails_dir(self) -> Path:
        p = self.data_root / "thumbnails"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @cached_property
    def config_file(self) -> Path:
        self.data_root.mkdir(parents=True, exist_ok=True)
        return self.data_root / "config.yaml"

    @cached_property
    def secret_key_file(self) -> Path:
        self.data_root.mkdir(parents=True, exist_ok=True)
        return self.data_root / "secret.key"

    @cached_property
    def license_file(self) -> Path:
        self.data_root.mkdir(parents=True, exist_ok=True)
        return self.data_root / "license.dat"

    @cached_property
    def youtube_token_file(self) -> Path:
        self.data_root.mkdir(parents=True, exist_ok=True)
        return self.data_root / "youtube_token.json"

    @cached_property
    def assets_dir(self) -> Path:
        return self.resources_root / "assets"

    @cached_property
    def themes_dir(self) -> Path:
        return self.assets_dir / "themes"

    @cached_property
    def icons_dir(self) -> Path:
        return self.assets_dir / "icons"

    @cached_property
    def web_dir(self) -> Path:
        return self.resources_root / "web"

    @cached_property
    def web_templates(self) -> Path:
        return self.web_dir / "templates"

    @cached_property
    def web_static(self) -> Path:
        return self.web_dir / "static"

    @cached_property
    def default_config_template(self) -> Path:
        return self.resources_root / "config" / "default.yaml"


paths = AppPaths(data_root=_platform_data_root(), resources_root=_resources_root())
