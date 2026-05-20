"""Application-specific exception hierarchy."""
from __future__ import annotations


class StudioError(Exception):
    """Base class for all custom exceptions raised by the application."""


class ConfigError(StudioError):
    pass


class DatabaseError(StudioError):
    pass


class FFmpegError(StudioError):
    pass


class FFmpegMissingError(FFmpegError):
    pass


class StreamError(StudioError):
    pass


class ChannelError(StudioError):
    pass


class PlaylistError(StudioError):
    pass


class SecurityError(StudioError):
    pass


class LicenseError(StudioError):
    pass


class NetworkError(StudioError):
    pass


class RemoteControlError(StudioError):
    pass
