"""Encrypted credential vault layered over the settings table."""
from __future__ import annotations

from ..db.base import get_db
from ..db.repository import SettingsRepository
from .crypto import get_crypto


class CredentialStore:
    """Stores secrets encrypted in the ``settings`` SQLite table."""

    def __init__(self) -> None:
        self._repo = SettingsRepository(get_db())
        self._crypto = get_crypto()

    def set(self, key: str, value: str) -> None:
        self._repo.set(f"secret:{key}", self._crypto.encrypt(value))

    def get(self, key: str, default: str = "") -> str:
        raw = self._repo.get(f"secret:{key}", "")
        if not raw:
            return default
        return self._crypto.safe_decrypt(raw, default)

    def delete(self, key: str) -> None:
        self._repo.set(f"secret:{key}", "")

    def list_keys(self) -> list[str]:
        return [k.split(":", 1)[1] for k in self._repo.all() if k.startswith("secret:")]


_GLOBAL: CredentialStore | None = None


def get_credentials() -> CredentialStore:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = CredentialStore()
    return _GLOBAL
