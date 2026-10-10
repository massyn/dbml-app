"""Turn DBML `records` into seed rows for a table in the app's model."""

import uuid
from datetime import UTC, datetime

from .dbml import Expression, Records
from .model import Column, Table

_NOW = {"now()", "current_timestamp", "current_timestamp()", "getdate()", "sysdate()"}
_NEW_UUID = {"gen_random_uuid()", "uuid_generate_v4()", "uuid()", "newid()"}
_TRUE = {True, "y", "yes", "true", "t", "1"}
_FALSE = {False, "n", "no", "false", "f", "0"}


def _seed_value(column: Column, value: object, problems: list[str]) -> object:
    """Convert one parsed value for its column; unsupported values become None."""
    if isinstance(value, Expression):
        expr = value.text.lower()
        if expr in _NOW:
            return datetime.now(UTC).isoformat(timespec="seconds")
        if expr in _NEW_UUID:
            return str(uuid.uuid4())
        problems.append(f"expression `{value.text}` in {column.name} is not supported")
        return None
    if column.kind == "boolean" and value is not None:
        key = value.lower() if isinstance(value, str) else value
        if key in _TRUE:
            return 1
        if key in _FALSE:
            return 0
        problems.append(f"'{value}' is not a boolean for {column.name}")
        return None
    return value


def seed_rows(records: Records, table: Table) -> tuple[list[dict], list[str]]:
    """Rows of a records block as {column: value}, plus any problems to warn about."""
    problems: list[str] = []
    names = records.columns or [c.name for c in table.columns]
    known = {c.name: c for c in table.columns}
    unknown = [n for n in names if n not in known]
    if unknown:
        return [], [f"unknown column(s) {', '.join(unknown)}"]
    rows = []
    for number, row in enumerate(records.rows, 1):
        while len(row) > len(names) and row[-1] is None:  # trailing comma
            row = row[:-1]
        if len(row) > len(names):
            problems.append(f"row {number} has more values than columns; skipped")
            continue
        row = row + [None] * (len(names) - len(row))
        rows.append(
            {
                n: _seed_value(known[n], v, problems)
                for n, v in zip(names, row, strict=True)
            }
        )
    return rows, problems
