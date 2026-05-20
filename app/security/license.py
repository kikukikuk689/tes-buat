"""License management.

Implements a real local license file (HMAC-signed JSON) with optional
online activation against a user-supplied endpoint.  No fake checks: if
there is no license, the app runs in trial mode for the number of days
configured in ``licensing.trial_days``.
"""
from __future__ import annotations

import base64
import enum
import hashlib
import hmac
import json
import platform
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from ..core.config import get_config
from ..core.exceptions import LicenseError
from ..core.logger import get_logger
from ..core.paths import paths

LICENSE_SIGNING_SECRET = b"asmr-broadcast-studio:offline-license:v1"


class LicenseStatus(str, enum.Enum):
    NONE = "none"
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    INVALID = "invalid"
    BOUND_TO_OTHER_DEVICE = "bound_to_other_device"


@dataclass
class LicenseInfo:
    status: LicenseStatus
    key: str = ""
    email: str = ""
    plan: str = "trial"
    issued_at: str = ""
    expires_at: str = ""
    device_id: str = ""
    days_remaining: int = 0
    message: str = ""


def _device_id() -> str:
    """Stable per-device identifier (uuid+platform)."""
    base = f"{uuid.getnode()}|{platform.node()}|{platform.system()}"
    return hashlib.sha256(base.encode()).hexdigest()[:32]


def _sign(payload: dict) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    mac = hmac.new(LICENSE_SIGNING_SECRET, data, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def _verify(payload: dict, signature: str) -> bool:
    expected = _sign(payload)
    return hmac.compare_digest(expected, signature)


class LicenseManager:
    """Reads / writes / activates the local license file."""

    def __init__(self, license_path: Path | None = None) -> None:
        self._path = license_path or paths.license_file
        self._log = get_logger("license")
        self._cfg = get_config().config.licensing
        self._first_run_marker = paths.data_root / ".first_run"

    @property
    def device_id(self) -> str:
        return _device_id()

    def status(self) -> LicenseInfo:
        if self._path.exists():
            return self._read_license()
        return self._trial_status()

    def install_license_text(self, blob: str) -> LicenseInfo:
        """Persist a signed license blob and return its status."""
        try:
            decoded = json.loads(base64.urlsafe_b64decode(blob.encode() + b"==").decode())
        except Exception as exc:  # noqa: BLE001
            raise LicenseError(f"License is not valid base64 JSON: {exc}") from exc
        payload = decoded.get("payload") or {}
        signature = decoded.get("signature") or ""
        if not _verify(payload, signature):
            raise LicenseError("License signature does not match.")
        if payload.get("device_id") and payload["device_id"] != self.device_id:
            raise LicenseError("This license is bound to a different device.")
        self._path.write_text(json.dumps(decoded, indent=2), encoding="utf-8")
        self._log.info("License installed for %s (plan=%s)", payload.get("email"), payload.get("plan"))
        return self._read_license()

    def activate_online(self, key: str, email: str = "") -> LicenseInfo:
        """Activate against the user-provided activation URL."""
        url = self._cfg.activation_url.strip()
        if not url:
            raise LicenseError("Online activation URL is not configured.")
        try:
            resp = httpx.post(
                url,
                json={"key": key, "email": email, "device_id": self.device_id},
                timeout=15,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LicenseError(f"Activation request failed: {exc}") from exc
        body = resp.json()
        license_blob = body.get("license") or ""
        if not license_blob:
            raise LicenseError("Activation server did not return a license payload.")
        return self.install_license_text(license_blob)

    def deactivate(self) -> None:
        if self._path.exists():
            self._path.unlink()

    def issue_offline_license(
        self,
        *,
        key: str,
        email: str,
        plan: str,
        days_valid: int,
        bind_device: bool = True,
    ) -> str:
        """Convenience helper to mint a signed license blob locally.

        This is the same routine an external activation server would use:
        build a payload, sign it with the shared secret, then return the
        base64 token.  Useful for CI, tests, or self-hosted activation.
        """
        issued = datetime.utcnow()
        expires = issued + timedelta(days=days_valid)
        payload = {
            "key": key,
            "email": email,
            "plan": plan,
            "issued_at": issued.isoformat() + "Z",
            "expires_at": expires.isoformat() + "Z",
            "device_id": self.device_id if bind_device else "",
        }
        blob = {"payload": payload, "signature": _sign(payload)}
        return base64.urlsafe_b64encode(json.dumps(blob).encode()).decode().rstrip("=")

    # ------------------------------------------------------------------
    def _read_license(self) -> LicenseInfo:
        try:
            blob = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            self._log.warning("License file unreadable: %s", exc)
            return LicenseInfo(status=LicenseStatus.INVALID, message=str(exc))
        payload = blob.get("payload") or {}
        signature = blob.get("signature") or ""
        if not _verify(payload, signature):
            return LicenseInfo(status=LicenseStatus.INVALID, message="Bad signature")
        if payload.get("device_id") and payload["device_id"] != self.device_id:
            return LicenseInfo(
                status=LicenseStatus.BOUND_TO_OTHER_DEVICE,
                message="License is bound to a different device",
            )
        expires_str = payload.get("expires_at", "")
        try:
            expires = datetime.fromisoformat(expires_str.rstrip("Z"))
        except ValueError:
            expires = datetime.utcnow()
        days_remaining = max(0, (expires - datetime.utcnow()).days)
        status = LicenseStatus.ACTIVE if expires > datetime.utcnow() else LicenseStatus.EXPIRED
        return LicenseInfo(
            status=status,
            key=payload.get("key", ""),
            email=payload.get("email", ""),
            plan=payload.get("plan", ""),
            issued_at=payload.get("issued_at", ""),
            expires_at=payload.get("expires_at", ""),
            device_id=payload.get("device_id", ""),
            days_remaining=days_remaining,
            message="" if status == LicenseStatus.ACTIVE else "License has expired",
        )

    def _trial_status(self) -> LicenseInfo:
        if not self._first_run_marker.exists():
            self._first_run_marker.write_text(datetime.utcnow().isoformat(), encoding="utf-8")
            installed_at = datetime.utcnow()
        else:
            try:
                installed_at = datetime.fromisoformat(self._first_run_marker.read_text().strip())
            except Exception:  # noqa: BLE001
                installed_at = datetime.utcnow()
        expires = installed_at + timedelta(days=self._cfg.trial_days)
        days_remaining = max(0, (expires - datetime.utcnow()).days)
        status = LicenseStatus.TRIAL if days_remaining > 0 else LicenseStatus.EXPIRED
        return LicenseInfo(
            status=status,
            plan="trial",
            issued_at=installed_at.isoformat() + "Z",
            expires_at=expires.isoformat() + "Z",
            device_id=self.device_id,
            days_remaining=days_remaining,
            message="Trial period" if status == LicenseStatus.TRIAL else "Trial expired",
        )

    def as_dict(self) -> dict:
        return asdict(self.status())


_GLOBAL: LicenseManager | None = None


def get_license_manager() -> LicenseManager:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = LicenseManager()
    return _GLOBAL
