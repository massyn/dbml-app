"""Resolve runtime settings from the command line, falling back to environment / .env."""

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    """A required setting is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    dbml_path: Path
    db_path: Path
    host: str
    port: int
    page_size: int
    secret_key: str
    debug: bool


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    try:
        return int(raw) if raw else default
    except ValueError:
        raise ConfigError(f"{name} must be a whole number, got '{raw}'") from None


def resolve_settings(cli_dbml: str | None, cli_db: str | None) -> Settings:
    """Command-line values win over DBML= / DB= from the environment; both are required."""
    dbml = cli_dbml or os.environ.get("DBML")
    db = cli_db or os.environ.get("DB")
    missing = [
        name
        for name, value in (("--dbml / DBML", dbml), ("--db / DB", db))
        if not value
    ]
    if missing:
        raise ConfigError(f"Missing required setting: {', '.join(missing)}")

    dbml_path = Path(dbml).resolve()
    if not dbml_path.is_file():
        raise ConfigError(f"DBML file not found: {dbml_path}")
    db_path = Path(db).resolve()
    if not db_path.parent.is_dir():
        raise ConfigError(
            f"Directory for the database does not exist: {db_path.parent}"
        )

    return Settings(
        dbml_path=dbml_path,
        db_path=db_path,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=_int_env("PORT", 5000),
        page_size=_int_env("PAGE_SIZE", 25),
        # Sessions only carry flash messages here, so a per-process key is acceptable.
        secret_key=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        debug=os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes"),
    )
