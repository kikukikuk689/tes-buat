"""Symmetric encryption helper.

Provides a :class:`CryptoBox` that wraps a Fernet key persisted in the
user data directory.  All sensitive values (stream keys, API tokens,
OAuth refresh tokens) are encrypted with this key before being written
to disk or the database.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from ..core.exceptions import SecurityError
from ..core.paths import paths


class CryptoBox:
    """Fernet-based encrypt / decrypt façade."""

    def __init__(self, key_path: Path | None = None) -> None:
        self._key_path = key_path or paths.secret_key_file
        self._fernet = Fernet(self._load_or_create_key())

    def _load_or_create_key(self) -> bytes:
        if self._key_path.exists():
            data = self._key_path.read_bytes().strip()
            if not data:
                raise SecurityError("Empty secret key file")
            return data
        key = Fernet.generate_key()
        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        self._key_path.write_bytes(key)
        try:
            os.chmod(self._key_path, 0o600)
        except OSError:  # pragma: no cover - platform dependent
            pass
        return key

    def encrypt(self, plaintext: str) -> str:
        if plaintext is None:
            return ""
        token = self._fernet.encrypt(plaintext.encode("utf-8"))
        return token.decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext:
            return ""
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError) as exc:
            raise SecurityError("Invalid or corrupted encrypted value") from exc

    def safe_decrypt(self, ciphertext: str, default: str = "") -> str:
        try:
            return self.decrypt(ciphertext)
        except SecurityError:
            return default

    def fingerprint(self) -> str:
        """A short fingerprint of the active key (for display only)."""
        return base64.urlsafe_b64encode(self._fernet._signing_key).decode()[:8]  # type: ignore[attr-defined]


_GLOBAL: CryptoBox | None = None


def get_crypto() -> CryptoBox:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = CryptoBox()
    return _GLOBAL
