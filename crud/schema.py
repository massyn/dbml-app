"""Turn a parsed DBML file (dbml.py) into the table model (model.py) the app runs on.

Anything the app cannot render yet is skipped with a logged warning, so the rest of the
file still produces a working app. Only a file that is not valid DBML is an error.
"""

import logging
import re
from pathlib import Path

from . import dbml
from .dbml import DBML, DBMLError, Expression
from .model import (
    Column,
    Group,
    Index,
    Link,
    Project,
    Ref,
    Schema,
    StickyNote,
    Table,
)
from .seed import seed_rows

logger = logging.getLogger(__name__)

# DBML type name (lower case, size suffix stripped) -> column kind
_KIND_BY_TYPE = {
    **dict.fromkeys(
        ["int", "integer", "bigint", "smallint", "tinyint", "int2", "int4", "int8"],
        "integer",
    ),
    **dict.fromkeys(["serial", "bigserial", "smallserial"], "integer"),
    **dict.fromkeys(
        ["float", "float4", "float8", "double", "double precision", "real"], "real"
    ),
    **dict.fromkeys(["decimal", "numeric", "money"], "real"),
    **dict.fromkeys(["bool", "boolean"], "boolean"),
    "date": "date",
    **dict.fromkeys(
        [
            "datetime",
            "timestamp",
            "timestamptz",
            "timestamp with time zone",
            "timestamp without time zone",
        ],
        "datetime",
    ),
    "uuid": "uuid",
}

# Unbounded text types: rendered as a multi-line text area.
_MULTILINE_TYPES = {"text", "mediumtext", "longtext", "ntext", "clob"}
# Other recognised text types: a single-line input. Anything not recognised at all is
# also treated as single-line text, with a warning.
_LINE_TYPES = {
    "varchar",
    "char",
    "nvarchar",
    "nchar",
    "string",
    "character",
    "character varying",
    "citext",
    "tinytext",
    "json",
    "jsonb",
    "xml",
}

_HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?(?:[0-9a-fA-F]{2})?")

_DEFAULT_ON_DELETE = {True: "RESTRICT", False: "SET NULL"}  # keyed by column.not_null
# Deleting a record only removes its many-to-many links; the records on the other side stay.
_DEFAULT_LINK_ON_DELETE = "CASCADE"


class SchemaError(Exception):
    """The DBML file is not valid DBML."""


class _Unsupported(Exception):
    """Something the app cannot render yet; it is skipped with a warning."""


def _base_type(col_type: str) -> str:
    """Lower-case type name with any size suffix and array marker removed."""
    return re.sub(r"\(.*\)|\[\]", "", col_type).strip().lower()


def _max_length(col_type: str) -> int | None:
    size = re.fullmatch(r"[^(]+\(\s*(\d+)\s*\)", col_type.strip())
    return int(size.group(1)) if size else None


def _column(
    c: dbml.Column, enums: dict[str, dbml.Enum], unknown_types: set[str]
) -> Column:
    enum = enums.get(c.type) or enums.get(c.type.removeprefix("public."))
    if enum:
        kind, base = "enum", ""
    else:
        base = _base_type(c.type)
        kind = _KIND_BY_TYPE.get(base, "text")
        if kind == "text" and base not in _MULTILINE_TYPES | _LINE_TYPES:
            unknown_types.add(base)
    return Column(
        name=c.name,
        kind=kind,
        pk=c.pk,
        unique=c.unique,
        not_null=bool(c.not_null),
        enum_values=[v.name for v in enum.values] if enum else [],
        enum_notes={v.name: v.note for v in enum.values if v.note} if enum else {},
        default=None if isinstance(c.default, Expression) else c.default,
        note=c.note,
        multiline=base in _MULTILINE_TYPES,
        max_length=_max_length(c.type) if kind == "text" else None,
    )


def _indexes(t: dbml.Table) -> list[Index]:
    indexes = []
    for ix in t.indexes:
        if ix.pk:
            raise _Unsupported("composite primary keys are not supported yet")
        if any(isinstance(c, Expression) for c in ix.columns):
            logger.warning("Table %s: skipping expression index", t.name)
            continue
        columns = [str(c) for c in ix.columns]
        prefix = "uq" if ix.unique else "ix"
        name = ix.name or f"{prefix}_{t.name}_{'_'.join(columns)}"
        indexes.append(Index(name=name, columns=columns, unique=ix.unique))
    return indexes


def _case_clash(names: list[str]) -> tuple[str, str] | None:
    """Names are used exactly as written, but SQLite matches identifiers case-insensitively,
    so two names differing only by case would refer to the same object."""
    seen: dict[str, str] = {}
    for name in names:
        first = seen.setdefault(name.lower(), name)
        if first != name:
            return first, name
    return None


def _table(
    t: dbml.Table, enums: dict[str, dbml.Enum], unknown_types: set[str]
) -> Table:
    indexes = _indexes(t)  # first: reports a composite primary key precisely
    columns = [_column(c, enums, unknown_types) for c in t.columns]
    pks = [c for c in columns if c.pk]
    if len(pks) != 1:
        raise _Unsupported(f"needs exactly one primary key column (found {len(pks)})")
    if clash := _case_clash([c.name for c in columns]):
        raise _Unsupported(
            f"columns '{clash[0]}' and '{clash[1]}' differ only by case; "
            "SQLite would treat them as the same name"
        )
    colour = t.header_color
    return Table(
        name=t.name,
        columns=columns,
        note=t.note,
        header_color=colour if colour and _HEX_COLOUR.fullmatch(colour) else None,
        indexes=indexes,
    )


def _join_table(tables: dict[str, Table], taken: set[str], ref: dbml.Ref) -> Table:
    """Generate the join table for a '<>' ref, named the way DBML's own SQL export names it."""
    t1, c1 = ref.left.table, ref.left.columns[0]
    t2, c2 = ref.right.table, ref.right.columns[0]
    if t1 == t2:
        raise _Unsupported("self-referencing many-to-many is not supported yet")
    if any(link.other_table == t2 for link in tables[t1].links):
        raise _Unsupported(f"there is already a many-to-many ref between {t1} and {t2}")
    name, col1, col2 = f"{t1}_{t2}", f"{t1}_{c1}", f"{t2}_{c2}"
    if name.lower() in taken:
        raise _Unsupported(f"its join table '{name}' clashes with another table")

    on_delete = (ref.on_delete or _DEFAULT_LINK_ON_DELETE).upper()
    columns = [
        Column(
            name=col,
            kind=tables[t].column(c).kind,
            not_null=True,
            ref=Ref(table=t, column=c, on_delete=on_delete),
        )
        for col, t, c in ((col1, t1, c1), (col2, t2, c2))
    ]
    tables[t1].links.append(Link(t2, name, col1, col2, on_delete))
    tables[t2].links.append(Link(t1, name, col2, col1, on_delete))
    # The composite key indexes lookups from t1; this one serves lookups from t2.
    return Table(
        name=name,
        columns=columns,
        composite_key=[col1, col2],
        indexes=[Index(name=f"ix_{name}_{col2}", columns=[col2], unique=False)],
    )


def _apply_ref(
    tables: dict[str, Table], join_tables: list[Table], ref: dbml.Ref
) -> None:
    missing = [end.table for end in (ref.left, ref.right) if end.table not in tables]
    if missing:
        raise _Unsupported(f"table '{missing[0]}' was skipped")
    if len(ref.left.columns) != 1 or len(ref.right.columns) != 1:
        raise _Unsupported("composite foreign keys are not supported yet")

    if ref.op == "<>":
        taken = {n.lower() for n in [*tables, *(j.name for j in join_tables)]}
        join_tables.append(_join_table(tables, taken, ref))
        return

    # '>' and '-': the left side holds the foreign key. '<': the right side holds it.
    src, dst = (ref.right, ref.left) if ref.op == "<" else (ref.left, ref.right)
    source = tables[src.table]
    column = source.column(src.columns[0])
    on_delete = (ref.on_delete or _DEFAULT_ON_DELETE[column.not_null]).upper()
    column.ref = Ref(table=dst.table, column=dst.columns[0], on_delete=on_delete)
    tables[dst.table].referenced_by.append((src.table, column.name))
    # One-to-one: each record on the other side may be linked at most once.
    if ref.op == "-" and not (column.unique or column.pk):
        source.indexes.append(
            Index(
                name=f"uq_{source.name}_{column.name}",
                columns=[column.name],
                unique=True,
            )
        )


def _describe(ref: dbml.Ref) -> str:
    left = f"{ref.left.table}.{', '.join(ref.left.columns)}"
    right = f"{ref.right.table}.{', '.join(ref.right.columns)}"
    return f"{left} {ref.op} {right}"


def load_schema(path: Path) -> Schema:
    try:
        parsed = DBML(Path(path).read_text(encoding="utf-8"))
    except DBMLError as exc:
        raise SchemaError(f"Could not parse {path}: {exc}") from exc

    enums = {e.name: e for e in parsed.enums}
    enums.update({f"{e.schema}.{e.name}": e for e in parsed.enums if e.schema})
    unknown_types: set[str] = set()
    tables: dict[str, Table] = {}
    for t in parsed.tables:
        try:
            if t.name in tables:
                raise _Unsupported(
                    "another schema has a table of the same name; "
                    "schemas are not supported yet"
                )
            if clash := _case_clash([*tables, t.name]):
                raise _Unsupported(
                    f"differs only by case from table '{clash[0]}'; "
                    "SQLite would treat them as the same name"
                )
            tables[t.name] = _table(t, enums, unknown_types)
        except _Unsupported as exc:
            logger.warning("Skipping table %s: %s", t.name, exc)

    join_tables: list[Table] = []
    for ref in parsed.refs:
        try:
            _apply_ref(tables, join_tables, ref)
        except _Unsupported as exc:
            logger.warning("Skipping ref %s: %s", _describe(ref), exc)

    for records in parsed.records:
        if records.table not in tables:
            logger.warning("Skipping records for %s: table was skipped", records.table)
            continue
        rows, problems = seed_rows(records, tables[records.table])
        for problem in problems:
            logger.warning("Records for %s: %s", records.table, problem)
        tables[records.table].seed_rows.extend(rows)

    for type_name in sorted(unknown_types):
        logger.warning("Unrecognised column type '%s': treated as text", type_name)

    groups = [
        Group(name=g.name, tables=[t for t in g.tables if t in tables], note=g.note)
        for g in parsed.table_groups
    ]
    project = parsed.project
    logger.info(
        "Loaded %d tables and %d join tables from %s",
        len(tables),
        len(join_tables),
        path,
    )
    return Schema(
        tables=tables,
        join_tables=join_tables,
        project=(
            Project(name=project.name or "DBML CRUD", note=project.note)
            if project
            else None
        ),
        groups=[g for g in groups if g.tables],
        notes=[StickyNote(name=n.name, text=n.text) for n in parsed.sticky_notes],
    )
