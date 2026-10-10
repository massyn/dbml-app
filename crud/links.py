"""Read and replace a record's many-to-many links, stored in the generated join tables."""

from . import db
from .labels import label
from .model import Link, Schema, Table


def _target(schema: Schema, link: Link) -> dict:
    other = schema.table(link.other_table)
    return {"other_pk": other.pk.name, "display": other.display_column.name}


def list_specs(schema: Schema, table: Table) -> list[dict]:
    """What record_list.sql needs to show each link as a comma-separated column."""
    return [
        {
            "field": link.field,
            "join_table": link.join_table,
            "other_table": link.other_table,
            "self_column": link.self_column,
            "other_column": link.other_column,
            **_target(schema, link),
        }
        for link in table.links
    ]


def linked(schema: Schema, table: Table, pk: str) -> dict[str, list[dict]]:
    """The records currently linked to pk, as {field: [{id, label}]}."""
    return {
        link.field: db.query("link_list.sql", (pk,), link=link, **_target(schema, link))
        for link in table.links
    }


def labelled(
    schema: Schema, table: Table, selected: dict[str, list]
) -> dict[str, list[dict]]:
    """Labels for submitted link ids, so a form with errors re-renders what was chosen."""
    result = {}
    for link in table.links:
        other = schema.table(link.other_table)
        items = []
        for other_id in selected.get(link.field, []):
            row = db.query_one("record_label.sql", (other_id,), table=other)
            label = row["label"] if row and row["label"] is not None else other_id
            items.append({"id": other_id, "label": label})
        result[link.field] = items
    return result


def replace(table: Table, pk: object, selected: dict[str, list]) -> None:
    """Make pk's links exactly `selected`. Call inside db.transaction()."""
    for link in table.links:
        db.execute("link_clear.sql", (pk,), commit=False, link=link)
        for other_id in selected.get(link.field, []):
            db.execute("link_insert.sql", (pk, other_id), commit=False, link=link)


def blockers(table: Table, pk: str) -> list[str]:
    """Describe links that prevent deleting pk (only when the ref says RESTRICT)."""
    found = []
    for link in table.links:
        if link.on_delete not in ("RESTRICT", "NO ACTION"):
            continue
        n = db.query_one(
            "dependent_count.sql", (pk,), table=link.join_table, column=link.self_column
        )["n"]
        if n:
            found.append(f"{n} {label(link.other_table)} link{'s' if n != 1 else ''}")
    return found
