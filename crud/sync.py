"""Bring the SQLite database in line with the DBML schema at start-up.

Additive changes (new tables, new columns, new indexes) are applied. Anything destructive or
ambiguous (a column removed from the DBML, a changed type, a NOT NULL column that cannot be
added, a unique index the existing data violates) stops start-up with a SchemaDriftError
rather than guessing. Indexes removed from the DBML are left in place.
"""

import logging
import sqlite3
import uuid
from pathlib import Path

from . import db
from .model import Schema, Table

logger = logging.getLogger(__name__)


class SchemaDriftError(Exception):
    """The database no longer matches the DBML in a way that cannot be applied safely."""


def _sync_columns(conn: sqlite3.Connection, table: Table) -> bool:
    """Create or extend the table. Returns True when the table was newly created."""
    existing = {
        row["name"]: row["type"].upper()
        for row in db.query("table_columns.sql", (table.name,), conn=conn)
    }
    if not existing:
        db.execute("create_table.sql", conn=conn, table=table)
        logger.info("Created table %s", table.name)
        return True

    wanted = {c.name: c for c in table.columns}
    removed = sorted(set(existing) - set(wanted))
    if removed:
        raise SchemaDriftError(
            f"Table '{table.name}' has columns no longer in the DBML: {', '.join(removed)}"
        )
    for name, column in wanted.items():
        if name not in existing:
            try:
                db.execute("add_column.sql", conn=conn, table=table, column=column)
            except sqlite3.OperationalError as exc:
                raise SchemaDriftError(
                    f"Cannot add column '{table.name}.{name}': {exc}"
                ) from exc
            logger.info("Added column %s.%s", table.name, name)
        elif existing[name] != column.sql_type:
            raise SchemaDriftError(
                f"Column '{table.name}.{name}' is {existing[name]} in the database "
                f"but {column.sql_type} in the DBML"
            )
    return False


def _seed(conn: sqlite3.Connection, tables: list[Table]) -> None:
    """Insert DBML records into newly created tables, all or nothing.

    Foreign keys are checked at commit, so records may appear in any order in the file.
    A failure is logged and the app starts with the tables empty.
    """
    seeded = [t for t in tables if t.seed_rows]
    if not seeded:
        return
    try:
        conn.execute("PRAGMA defer_foreign_keys = ON")
        for table in seeded:
            for row in table.seed_rows:
                row = dict(row)
                if (
                    table.pk.auto
                    and table.pk.kind == "uuid"
                    and row.get(table.pk.name) is None
                ):
                    row[table.pk.name] = str(uuid.uuid4())
                db.execute(
                    "record_insert.sql",
                    list(row.values()),
                    conn=conn,
                    commit=False,
                    table=table,
                    columns=list(row),
                )
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        logger.exception("Could not load the DBML records; tables left empty")
        return
    for table in seeded:
        logger.info("Loaded %d records into %s", len(table.seed_rows), table.name)


def sync_schema(schema: Schema, db_path: Path) -> None:
    conn = db.connect(db_path)
    try:
        created = []
        for table in [*schema.tables.values(), *schema.join_tables]:
            if _sync_columns(conn, table):
                created.append(table)
            for index in table.indexes:
                try:
                    db.execute("create_index.sql", conn=conn, table=table, index=index)
                except sqlite3.IntegrityError as exc:
                    raise SchemaDriftError(
                        f"Cannot create unique index '{index.name}' on '{table.name}': "
                        f"existing rows have duplicate values ({exc})"
                    ) from exc
        _seed(conn, created)
    finally:
        conn.close()
