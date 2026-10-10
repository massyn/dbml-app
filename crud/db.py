"""SQLite connection handling and rendering of the SQL templates in templates/sql/."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from flask import current_app, g
from jinja2 import Environment, FileSystemLoader, StrictUndefined

SQL_DIR = Path(__file__).resolve().parent.parent / "templates" / "sql"


def quote_ident(name: str) -> str:
    """Quote an identifier taken from the DBML schema (identifiers cannot be parameterised)."""
    return '"' + name.replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    """Quote a DDL literal taken from the DBML schema, e.g. enum values in a CHECK constraint."""
    return "'" + str(value).replace("'", "''") + "'"


_env = Environment(
    loader=FileSystemLoader(SQL_DIR),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)
_env.filters["ident"] = quote_ident
_env.filters["literal"] = quote_literal


def render_sql(template: str, **kwargs) -> str:
    return _env.get_template(template).render(**kwargs)


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def close_db(_exc: BaseException | None = None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def query(template: str, params: tuple | list = (), conn=None, **kwargs) -> list[dict]:
    conn = conn or get_db()
    cur = conn.execute(render_sql(template, **kwargs), params)
    return [dict(row) for row in cur.fetchall()]


def query_one(
    template: str, params: tuple | list = (), conn=None, **kwargs
) -> dict | None:
    rows = query(template, params, conn=conn, **kwargs)
    return rows[0] if rows else None


def execute(
    template: str, params: tuple | list = (), conn=None, commit: bool = True, **kwargs
) -> int:
    """Run a write and (by default) commit. Returns the last inserted rowid.

    Pass commit=False inside a transaction() block so several writes succeed or fail together.
    """
    conn = conn or get_db()
    try:
        cur = conn.execute(render_sql(template, **kwargs), params)
        if commit:
            conn.commit()
    except sqlite3.Error:
        conn.rollback()
        raise
    return cur.lastrowid


@contextmanager
def transaction() -> Iterator[None]:
    """Commit the writes made inside the block together, or roll them all back."""
    conn = get_db()
    try:
        yield
        conn.commit()
    except Exception:
        conn.rollback()
        raise
