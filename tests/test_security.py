from __future__ import annotations

from pathlib import Path

from app.security.crypto import CryptoBox as CryptoService
from app.security.license import LicenseManager, LicenseStatus


def test_crypto_roundtrip(tmp_path: Path) -> None:
    key = tmp_path / "secret.key"
    cs = CryptoService(key)
    blob = cs.encrypt("super secret stream key")
    assert blob and blob != "super secret stream key"
    assert cs.decrypt(blob) == "super secret stream key"


def test_license_offline_issue_and_install(tmp_path_factory) -> None:
    tmp_path = tmp_path_factory.mktemp("lic")
    mgr = LicenseManager(tmp_path / "license.dat")
    blob = mgr.issue_offline_license(
        key="TEST-KEY",
        email="qa@example.com",
        plan="pro",
        days_valid=30,
        bind_device=True,
    )
    info = mgr.install_license_text(blob)
    assert info.status == LicenseStatus.ACTIVE
    assert info.plan == "pro"
    assert info.days_remaining >= 29
