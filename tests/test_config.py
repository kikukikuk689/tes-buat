from __future__ import annotations

from pathlib import Path

from app.core.config import ConfigManager


def test_config_create_and_persist(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yaml"
    mgr = ConfigManager(cfg_path)
    assert cfg_path.exists()
    assert mgr.config.general.app_name == "ASMR Broadcast Studio"

    mgr.update(general={"language": "id"})
    assert mgr.config.general.language == "id"

    reloaded = ConfigManager(cfg_path)
    assert reloaded.config.general.language == "id"


def test_config_rejects_unknown_section(tmp_path: Path) -> None:
    mgr = ConfigManager(tmp_path / "config.yaml")
    import pytest

    from app.core.exceptions import ConfigError

    with pytest.raises(ConfigError):
        mgr.update(does_not_exist={"x": 1})
