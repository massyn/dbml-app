"""The table model the CRUD app is generated from (built from DBML by schema.py)."""

from dataclasses import dataclass, field

# Column kind -> SQLite column type
_SQL_TYPE_BY_KIND = {
    "integer": "INTEGER",
    "real": "REAL",
    "boolean": "INTEGER",
}


@dataclass
class Ref:
    table: str
    column: str
    on_delete: str


@dataclass
class Column:
    name: str
    kind: str
    pk: bool = False
    unique: bool = False
    not_null: bool = False
    enum_values: list[str] = field(default_factory=list)
    enum_notes: dict[str, str] = field(default_factory=dict)  # value -> note
    ref: Ref | None = None
    default: str | int | float | bool | None = None
    note: str = ""
    multiline: bool = False  # text columns only
    max_length: int | None = None  # text columns only, from varchar(n) / char(n)

    @property
    def sql_type(self) -> str:
        return _SQL_TYPE_BY_KIND.get(self.kind, "TEXT")

    @property
    def auto(self) -> bool:
        """Primary key values the app generates rather than the user entering them."""
        return self.pk and self.kind in ("integer", "uuid")

    @property
    def required(self) -> bool:
        return (self.not_null or self.pk) and not self.auto


@dataclass
class Index:
    name: str
    columns: list[str]
    unique: bool


@dataclass
class Link:
    """One side of a many-to-many ref, as seen from the table whose form shows it."""

    other_table: str
    join_table: str
    self_column: str  # join table column pointing at this table
    other_column: str  # join table column pointing at the other table
    on_delete: str

    @property
    def field(self) -> str:
        """Form field name; the prefix keeps it clear of real column names."""
        return f"__link_{self.other_table}"


@dataclass
class Table:
    name: str
    columns: list[Column]
    note: str = ""
    header_color: str | None = None  # validated CSS hex colour
    referenced_by: list[tuple[str, str]] = field(default_factory=list)
    indexes: list[Index] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    composite_key: list[str] = field(default_factory=list)  # generated join tables only
    seed_rows: list[dict] = field(default_factory=list)  # from DBML records blocks

    @property
    def pk(self) -> Column:
        return next(c for c in self.columns if c.pk)

    @property
    def display_column(self) -> Column:
        """First unique text column, else first text column, else the primary key."""
        text = [c for c in self.columns if c.kind == "text" and not c.ref]
        return next((c for c in text if c.unique), None) or (
            text[0] if text else self.pk
        )

    @property
    def list_columns(self) -> list[Column]:
        """Columns shown in list tables. Multi-line text is left out (still searchable),
        and so are generated keys (they show on the form) — unless nothing else is left,
        in which case the key is shown so each row has something to identify it."""
        shown = [c for c in self.columns if not c.multiline and not c.auto]
        return shown or [self.pk]

    def column(self, name: str) -> Column:
        for c in self.columns:
            if c.name == name:
                return c
        raise KeyError(name)


@dataclass
class Project:
    name: str
    note: str = ""


@dataclass
class Group:
    """A DBML TableGroup: a heading in the navigation and on the home page."""

    name: str
    tables: list[str]
    note: str = ""


@dataclass
class StickyNote:
    name: str
    text: str


@dataclass
class Schema:
    tables: dict[str, Table]  # tables from the DBML, each with its own CRUD views
    join_tables: list[Table] = field(default_factory=list)  # generated for '<>' refs
    project: Project | None = None
    groups: list[Group] = field(default_factory=list)
    notes: list[StickyNote] = field(default_factory=list)

    def table(self, name: str) -> Table:
        return self.tables[name]

    @property
    def nav_groups(self) -> list[Group]:
        """TableGroups in DBML order, then any ungrouped tables under one heading."""
        grouped = {name for g in self.groups for name in g.tables}
        rest = [name for name in self.tables if name not in grouped]
        label = "Other tables" if self.groups else "Tables"
        return self.groups + ([Group(name=label, tables=rest)] if rest else [])
