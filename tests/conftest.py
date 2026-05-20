"""Shared pytest fixtures.

The tests run against a throwaway data directory to keep them isolated
from any real user installation.  We patch ``app.core.paths.paths`` (and
therefore everything that reads from it) to point inside ``tmp_path``.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture()
def tmp_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the app data directory to a per-test temp folder."""
    from app.core import paths as paths_mod

    new = paths_mod.AppPaths(data_root=tmp_path, resources_root=paths_mod.paths.resources_root)
    monkeypatch.setattr(paths_mod, "paths", new)
    # Also patch the symbol re-exported by config (it imports `paths` by name).
    import app.core.config as config_mod

    monkeypatch.setattr(config_mod, "paths", new)
    # Reset config singleton so a fresh manager picks up the patched paths.
    monkeypatch.setattr(config_mod, "_GLOBAL", None, raising=False)
    return tmp_path
