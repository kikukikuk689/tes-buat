"""Application configuration.

Loaded from ``config.yaml`` in the user data directory; falls back to the
bundled default template on first launch.  All settings are typed via
Pydantic to guarantee shape and validation.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .exceptions import ConfigError
from .paths import paths


class GeneralSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    app_name: str = "ASMR Broadcast Studio"
    language: str = "en"
    auto_launch: bool = False
    minimize_to_tray: bool = True
    close_to_tray: bool = True
    enable_notifications: bool = True
    sound_alerts: bool = False
    check_updates: bool = True


class StreamingDefaults(BaseModel):
    model_config = ConfigDict(extra="ignore")
    resolution: str = "1920x1080"
    fps: int = Field(default=30, ge=15, le=60)
    video_bitrate_kbps: int = Field(default=4500, ge=500, le=50_000)
    audio_bitrate_kbps: int = Field(default=160, ge=64, le=512)
    audio_sample_rate: int = 44_100
    keyframe_interval_sec: int = 2
    preset: str = "veryfast"
    profile: str = "high"
    pixel_format: str = "yuv420p"
    audio_codec: str = "aac"
    video_codec: str = "libx264"
    hw_accel: str = "auto"  # auto|none|nvenc|qsv|amf|videotoolbox
    loop_playlist: bool = True
    shuffle: bool = False
    crossfade_ms: int = 0
    normalize_audio: bool = True


class PerformanceSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    max_parallel_streams: int = 16
    enable_smart_cache: bool = True
    monitor_interval_ms: int = 1500
    watchdog_interval_ms: int = 3000
    network_check_interval_ms: int = 5000
    network_check_url: str = "https://www.google.com/generate_204"
    log_keep_lines: int = 5000


class RemoteSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 8765
    auth_token: str = ""  # encrypted via CredentialStore when set


class YouTubeSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    enabled: bool = False
    client_secret_path: str = ""
    default_privacy: str = "unlisted"
    default_category_id: str = "22"
    enable_dvr: bool = True
    latency_preference: str = "low"  # normal|low|ultraLow


class AISettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    enabled: bool = False
    provider: str = "openai"   # openai|local
    api_base: str = "https://api.openai.com/v1"
    api_key_encrypted: str = ""
    model: str = "gpt-4o-mini"
    default_language: str = "en"


class BackupSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    auto_backup: bool = True
    interval_hours: int = 12
    keep_last: int = 14


class ThemeSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    active: str = "cyberpunk"
    accent: str = "#9D4DFF"
    enable_animations: bool = True
    enable_blur: bool = True


class LicenseSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    activation_url: str = ""
    require_online_activation: bool = False
    trial_days: int = 14


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    general: GeneralSettings = Field(default_factory=GeneralSettings)
    streaming: StreamingDefaults = Field(default_factory=StreamingDefaults)
    performance: PerformanceSettings = Field(default_factory=PerformanceSettings)
    remote: RemoteSettings = Field(default_factory=RemoteSettings)
    youtube: YouTubeSettings = Field(default_factory=YouTubeSettings)
    ai: AISettings = Field(default_factory=AISettings)
    backup: BackupSettings = Field(default_factory=BackupSettings)
    theme: ThemeSettings = Field(default_factory=ThemeSettings)
    licensing: LicenseSettings = Field(default_factory=LicenseSettings)


class ConfigManager:
    """Loads, mutates and persists :class:`AppConfig` atomically."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or paths.config_file
        self._lock = threading.RLock()
        self._config = self._load_or_create()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def config(self) -> AppConfig:
        return self._config

    def reload(self) -> AppConfig:
        with self._lock:
            self._config = self._load_or_create()
            return self._config

    def update(self, **kwargs: Any) -> AppConfig:
        """Apply a dict-style update (section: value-dict) and persist."""
        with self._lock:
            data = self._config.model_dump()
            for section, value in kwargs.items():
                if section not in data:
                    raise ConfigError(f"Unknown section: {section}")
                if isinstance(value, dict):
                    data[section].update(value)
                else:
                    data[section] = value
            self._config = AppConfig.model_validate(data)
            self.save()
            return self._config

    def replace(self, config: AppConfig) -> None:
        with self._lock:
            self._config = config
            self.save()

    def save(self) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".yaml.tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                yaml.safe_dump(self._config.model_dump(), fh, sort_keys=False)
            tmp.replace(self._path)

    # ------------------------------------------------------------------
    def _load_or_create(self) -> AppConfig:
        if not self._path.exists():
            default_template = paths.default_config_template
            if default_template.exists():
                try:
                    raw = yaml.safe_load(default_template.read_text(encoding="utf-8")) or {}
                    cfg = AppConfig.model_validate(raw)
                except Exception as exc:  # noqa: BLE001
                    raise ConfigError(f"Default config invalid: {exc}") from exc
            else:
                cfg = AppConfig()
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                yaml.safe_dump(cfg.model_dump(), sort_keys=False), encoding="utf-8"
            )
            return cfg
        try:
            raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
            return AppConfig.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(f"Failed to load config {self._path}: {exc}") from exc


_GLOBAL: ConfigManager | None = None


def get_config(reload: bool = False) -> ConfigManager:
    """Return the process-wide :class:`ConfigManager`."""
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = ConfigManager()
    elif reload:
        _GLOBAL.reload()
    return _GLOBAL
