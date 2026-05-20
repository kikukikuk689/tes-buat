"""Backup / restore service.

Stores zipped snapshots of the user data directory in
``data_root/backups``.  Snapshots include the SQLite database, the
config file, the license file (signed) and any encrypted credentials —
but never the plain secret key, so a leaked backup cannot decrypt
secrets without the matching ``secret.key`` from the source machine.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..core.config import get_config
from ..core.logger import get_logger
from ..core.paths import paths


@dataclass
class BackupRecord:
    name: str
    path: Path
    size_bytes: int
    created_at: datetime


class BackupService:
    def __init__(self) -> None:
        self._log = get_logger("backup")
        self._lock = threading.RLock()
        self._cfg = get_config().config.backup
        self._auto_thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------
    def list_backups(self) -> list[BackupRecord]:
        records: list[BackupRecord] = []
        for p in sorted(paths.backups_dir.glob("backup-*.zip"), reverse=True):
            stat = p.stat()
            records.append(
                BackupRecord(
                    name=p.name,
                    path=p,
                    size_bytes=stat.st_size,
                    created_at=datetime.fromtimestamp(stat.st_mtime),
                )
            )
        return records

    def create(self, label: str = "") -> BackupRecord:
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        safe_label = (
            "".join(c for c in label if c.isalnum() or c in "-_")
            if label
            else ""
        )
        suffix = f"-{safe_label}" if safe_label else ""
        target = paths.backups_dir / f"backup-{ts}{suffix}.zip"
        with self._lock, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            self._add_if_exists(zf, paths.db_path)
            self._add_if_exists(zf, paths.config_file)
            self._add_if_exists(zf, paths.license_file)
            self._add_if_exists(zf, paths.data_root / ".first_run")
            manifest = {
                "created_at": ts,
                "label": label,
                "files": [n for n in zf.namelist()],
                "version": 1,
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        self._prune_old()
        stat = target.stat()
        return BackupRecord(
            name=target.name,
            path=target,
            size_bytes=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_mtime),
        )

    def restore(self, backup_path: Path) -> None:
        if not backup_path.exists():
            raise FileNotFoundError(backup_path)
        with self._lock, zipfile.ZipFile(backup_path) as zf:
            for member in zf.namelist():
                if member == "manifest.json":
                    continue
                target = paths.data_root / Path(member).name
                with zf.open(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        self._log.info("Restore complete from %s", backup_path)

    def export_config(self, target: Path) -> None:
        shutil.copy2(paths.config_file, target)

    def import_config(self, source: Path) -> None:
        shutil.copy2(source, paths.config_file)

    # ------------------------------------------------------------------
    # Auto backup loop
    # ------------------------------------------------------------------
    def start_auto(self) -> None:
        if not self._cfg.auto_backup:
            return
        if self._auto_thread and self._auto_thread.is_alive():
            return
        self._stop.clear()
        self._auto_thread = threading.Thread(
            target=self._auto_loop, name="backup-auto", daemon=True
        )
        self._auto_thread.start()

    def stop_auto(self) -> None:
        self._stop.set()
        if self._auto_thread:
            self._auto_thread.join(timeout=2)

    def _auto_loop(self) -> None:
        interval = max(60, self._cfg.interval_hours * 3600)
        while not self._stop.is_set():
            if self._stop.wait(interval):
                return
            try:
                rec = self.create("auto")
                self._log.info("Auto backup created: %s", rec.name)
            except Exception:  # noqa: BLE001
                self._log.exception("Auto backup failed")

    # ------------------------------------------------------------------
    def _prune_old(self) -> None:
        records = self.list_backups()
        keep = self._cfg.keep_last
        for old in records[keep:]:
            try:
                os.remove(old.path)
            except OSError:  # noqa: BLE001
                pass

    @staticmethod
    def _add_if_exists(zf: zipfile.ZipFile, file: Path) -> None:
        if file.exists():
            zf.write(file, arcname=file.name)


_GLOBAL: BackupService | None = None


def get_backup() -> BackupService:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = BackupService()
    return _GLOBAL
