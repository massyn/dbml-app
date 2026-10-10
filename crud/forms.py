"""Turn submitted form data into typed column values, validated against the DBML schema."""

import uuid
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from werkzeug.datastructures import MultiDict

from .model import Column, Schema, Table


def _convert(column: Column, raw: str) -> Any:
    """Convert one non-empty raw value. Raises ValueError with a user-facing message."""
    match column.kind:
        case "integer":
            try:
                return int(raw)
            except ValueError:
                raise ValueError("Must be a whole number") from None
        case "real":
            try:
                return float(raw)
            except ValueError:
                raise ValueError("Must be a number") from None
        case "enum":
            if raw not in column.enum_values:
                raise ValueError(f"Must be one of: {', '.join(column.enum_values)}")
            return raw
        case "date":
            try:
                return date.fromisoformat(raw).isoformat()
            except ValueError:
                raise ValueError("Must be a date (YYYY-MM-DD)") from None
        case "datetime":
            try:
                return datetime.fromisoformat(raw).isoformat()
            except ValueError:
                raise ValueError("Must be a date and time") from None
        case "uuid":
            try:
                return str(uuid.UUID(raw))
            except ValueError:
                raise ValueError("Must be a UUID") from None
        case _:
            # SQLite ignores varchar(n), so the declared length is enforced here.
            if column.max_length is not None and len(raw) > column.max_length:
                raise ValueError(f"Maximum {column.max_length} characters")
            return raw


def editable_columns(table: Table, creating: bool) -> list[Column]:
    """Columns the user supplies: generated keys never, other primary keys only on create."""
    return [c for c in table.columns if not c.auto and (creating or not c.pk)]


def parse_form(
    table: Table, form: Mapping[str, str], creating: bool
) -> tuple[dict[str, Any], dict[str, str]]:
    """Return (values, errors). errors maps column name to message and is empty when valid."""
    values: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for column in editable_columns(table, creating):
        if column.kind == "boolean":
            values[column.name] = 1 if form.get(column.name) else 0
            continue
        raw = (form.get(column.name) or "").strip()
        if raw == "":
            if column.required:
                errors[column.name] = "Required"
            else:
                values[column.name] = None
            continue
        try:
            values[column.name] = _convert(column, raw)
        except ValueError as exc:
            errors[column.name] = str(exc)
    return values, errors


def parse_links(
    schema: Schema, table: Table, form: MultiDict
) -> tuple[dict[str, list], dict[str, str]]:
    """Return ({link field: [other ids]}, errors) for the table's many-to-many fields."""
    selected: dict[str, list] = {}
    errors: dict[str, str] = {}
    for link in table.links:
        target = schema.table(link.other_table).pk
        ids = []
        for raw in form.getlist(link.field):
            if not raw.strip():
                continue
            try:
                ids.append(_convert(target, raw.strip()))
            except ValueError as exc:
                errors[link.field] = str(exc)
                break
        selected[link.field] = list(dict.fromkeys(ids))  # drop duplicates, keep order
    return selected, errors
