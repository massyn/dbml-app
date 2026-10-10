"""Read and write rows of any DBML table. The database enforces the schema's constraints."""

import logging
import math
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any

from . import db, labels, links
from .model import Schema, Table

logger = logging.getLogger(__name__)


class RecordError(Exception):
    """A write the data model does not allow, with a user-facing message."""


@dataclass
class Page:
    rows: list[dict]
    total: int
    page: int
    pages: int
    search: str
    sort: str
    direction: str


def _fks(schema: Schema, table: Table) -> list[dict]:
    return [
        {
            "column": c.name,
            "table": c.ref.table,
            "target": c.ref.column,
            "display": schema.table(c.ref.table).display_column.name,
        }
        for c in table.columns
        if c.ref
    ]


def list_records(
    schema: Schema,
    table: Table,
    search: str = "",
    sort: str = "",
    direction: str = "asc",
    page: int = 1,
    page_size: int = 25,
) -> Page:
    fks = _fks(schema, table)
    names = [c.name for c in table.columns]
    sort = sort if sort in names else table.display_column.name
    direction = "desc" if direction == "desc" else "asc"
    # Sorting a foreign key column sorts by the label the user sees.
    sort_by = next(
        (
            (f"j{i}", fk["display"])
            for i, fk in enumerate(fks, 1)
            if fk["column"] == sort
        ),
        ("t", sort),
    )

    search = search.strip()
    search_cols = []
    if search:
        search_cols = [("t", n) for n in names] + [
            (f"j{i}", fk["display"]) for i, fk in enumerate(fks, 1)
        ]
    search_params = [f"%{search}%"] * len(search_cols)

    total = db.query_one(
        "record_count.sql", search_params, table=table, fks=fks, search=search_cols
    )["n"]
    pages = max(1, math.ceil(total / page_size))
    page = min(max(1, page), pages)
    rows = db.query(
        "record_list.sql",
        search_params + [page_size, (page - 1) * page_size],
        table=table,
        fks=fks,
        search=search_cols,
        links=links.list_specs(schema, table),
        sort=sort_by,
        direction=direction.upper(),
    )
    return Page(rows, total, page, pages, search, sort, direction)


def count(table: Table) -> int:
    return db.query_one("record_count.sql", table=table, fks=[], search=[])["n"]


def get_record(table: Table, pk: str) -> dict | None:
    return db.query_one("record_get.sql", (pk,), table=table)


def label(table: Table, pk: Any) -> str:
    row = db.query_one("record_label.sql", (pk,), table=table)
    if row is None:
        return ""
    return str(row["label"]) if row["label"] is not None else str(pk)


def fk_labels(schema: Schema, table: Table, values: dict) -> dict[str, str]:
    """Display labels for the foreign key values in a form."""
    return {
        c.name: label(schema.table(c.ref.table), values[c.name])
        for c in table.columns
        if c.ref and values.get(c.name) not in (None, "")
    }


def _integrity_message(exc: sqlite3.IntegrityError) -> str:
    text = str(exc)
    if text.startswith("UNIQUE constraint failed: "):
        cols = text.removeprefix("UNIQUE constraint failed: ")
        return f"Another record already has this value ({cols})"
    if text.startswith("FOREIGN KEY constraint failed"):
        return "A linked record does not exist"
    return text


def save_record(
    table: Table,
    values: dict,
    pk: str | None = None,
    selected_links: dict[str, list] | None = None,
) -> Any:
    """Insert (pk None) or update a record and, when given, replace its many-to-many links.

    Everything is written in one transaction. Returns the record's primary key.
    """
    try:
        with db.transaction():
            pk = _write_record(table, values, pk)
            if selected_links is not None:
                links.replace(table, pk, selected_links)
    except sqlite3.IntegrityError as exc:
        raise RecordError(_integrity_message(exc)) from exc
    return pk


def _write_record(table: Table, values: dict, pk: str | None) -> Any:
    if pk is None:
        values = dict(values)
        if table.pk.auto and table.pk.kind == "uuid":
            values[table.pk.name] = str(uuid.uuid4())
        rowid = db.execute(
            "record_insert.sql",
            list(values.values()),
            commit=False,
            table=table,
            columns=list(values),
        )
        pk = values.get(table.pk.name, rowid)
        logger.info("Inserted %s %s", table.name, pk)
    else:
        if values:
            db.execute(
                "record_update.sql",
                list(values.values()) + [pk],
                commit=False,
                table=table,
                columns=list(values),
            )
        logger.info("Updated %s %s", table.name, pk)
    return pk


def delete_record(schema: Schema, table: Table, pk: str) -> None:
    try:
        db.execute("record_delete.sql", (pk,), table=table)
    except sqlite3.IntegrityError as exc:
        blockers = []
        for src_table, src_col in table.referenced_by:
            if schema.table(src_table).column(src_col).ref.on_delete not in (
                "RESTRICT",
                "NO ACTION",
            ):
                continue
            n = db.query_one(
                "dependent_count.sql", (pk,), table=src_table, column=src_col
            )["n"]
            if n:
                blockers.append(
                    f"{n} {labels.label(src_table)} record{'s' if n != 1 else ''}"
                )
        blockers += links.blockers(table, pk)
        detail = ", ".join(blockers) or "other records"
        raise RecordError(f"Cannot delete: still linked from {detail}") from exc
    logger.info("Deleted %s %s", table.name, pk)
