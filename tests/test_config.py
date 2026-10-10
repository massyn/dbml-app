import pytest

from config import ConfigError, resolve_settings
from tests.conftest import TEST_DBML


def test_cli_wins_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DBML", "missing.dbml")
    monkeypatch.setenv("DB", str(tmp_path / "env.db"))
    settings = resolve_settings(str(TEST_DBML), str(tmp_path / "cli.db"))
    assert settings.dbml_path == TEST_DBML
    assert settings.db_path.name == "cli.db"


def test_env_used_when_cli_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("DBML", str(TEST_DBML))
    monkeypatch.setenv("DB", str(tmp_path / "env.db"))
    assert resolve_settings(None, None).db_path.name == "env.db"


def test_missing_settings_are_reported(monkeypatch):
    monkeypatch.delenv("DBML", raising=False)
    monkeypatch.delenv("DB", raising=False)
    with pytest.raises(ConfigError, match="--dbml / DBML, --db / DB"):
        resolve_settings(None, None)
