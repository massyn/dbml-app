"""Records in other tables that point at a record: shown as lists on its edit page."""

from dataclasses import dataclass

from .forms import FILTER_PREFIX
from .labels import label
from .model import Schema, Table


@dataclass
class Related:
    table: str  # the table holding the foreign key
    column: str  # its foreign key column
    value: object  # the parent's referenced value the child rows match
    title: str

    @property
    def args(self) -> dict[str, object]:
        """List URL arguments that select only this record's children."""
        return {FILTER_PREFIX + self.column: self.value}


def for_record(schema: Schema, table: Table, row: dict) -> list[Related]:
    """One entry per foreign key pointing at this table, in DBML order.

    When a table points here more than once (e.g. owner and reviewer), the column name
    is added to the title so the lists can be told apart.
    """
    sources = [src for src, _ in table.referenced_by]
    result = []
    for src_table, src_col in table.referenced_by:
        ref = schema.table(src_table).column(src_col).ref
        title = label(src_table)
        if sources.count(src_table) > 1:
            title += f" ({label(src_col)})"
        result.append(Related(src_table, src_col, row[ref.column], title))
    return result
