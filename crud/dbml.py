"""A self-contained DBML parser (https://dbml.dbdiagram.io/docs/).

Standard library only, and no imports from the rest of this app, so the file can be
copied into any project:

    from dbml import DBML, DBMLError

    db = DBML(source_text)
    for table in db.tables:
        print(table.name, [c.name for c in table.columns])

`DBML` holds everything the source describes: the project, tables (with their columns,
indexes, checks and notes), enums, refs, table groups, sticky notes and records.
TablePartial injection (`~partial`) is applied while parsing, and refs, table groups and
records always name the real table, never an alias. Anything malformed raises
`DBMLError` with the line and column.
"""

import re
import textwrap
from dataclasses import dataclass, field

# --- What a parsed DBML file contains -------------------------------------------------


@dataclass
class Expression:
    """A backtick expression, e.g. `now()`, kept as written."""

    text: str


Value = str | int | float | bool | Expression | None


@dataclass
class Column:
    name: str
    type: (
        str  # as written, e.g. "varchar(255)", "double precision", "int[]", "v2.status"
    )
    pk: bool = False
    not_null: bool | None = None  # None: neither `null` nor `not null` was given
    unique: bool = False
    increment: bool = False
    default: Value = None
    note: str = ""
    check: Expression | None = None
    settings: dict[str, Value] = field(default_factory=dict)  # custom properties


@dataclass
class Index:
    columns: list[str | Expression]
    pk: bool = False
    unique: bool = False
    name: str | None = None
    type: str | None = None  # btree / hash
    note: str = ""


@dataclass
class Check:
    expression: Expression
    name: str | None = None


@dataclass
class Table:
    name: str
    schema: str | None = None
    alias: str | None = None
    columns: list[Column] = field(default_factory=list)
    indexes: list[Index] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    note: str = ""
    header_color: str | None = None
    settings: dict[str, Value] = field(default_factory=dict)  # custom properties

    def column(self, name: str) -> Column:
        for c in self.columns:
            if c.name == name:
                return c
        raise KeyError(name)


@dataclass
class EnumValue:
    name: str
    note: str = ""


@dataclass
class Enum:
    name: str
    schema: str | None = None
    values: list[EnumValue] = field(default_factory=list)


@dataclass
class RefEnd:
    table: str  # the real table name (aliases are resolved)
    columns: list[str]
    schema: str | None = None


@dataclass
class Ref:
    """`left op right`. op is '<', '>', '-' or '<>'; `>` reads "left many-to-one right"."""

    left: RefEnd
    op: str
    right: RefEnd
    name: str | None = None
    left_optional: bool = False  # `?` written on the left of the operator
    right_optional: bool = False  # `?` written on the right of the operator
    on_delete: str | None = (
        None  # cascade / restrict / set null / set default / no action
    )
    on_update: str | None = None
    color: str | None = None
    inline: bool = False  # written as a column setting `[ref: > t.c]`


@dataclass
class TableGroup:
    name: str
    tables: list[str] = field(default_factory=list)  # real table names
    note: str = ""
    color: str | None = None


@dataclass
class StickyNote:
    name: str
    text: str


@dataclass
class Project:
    name: str | None
    note: str = ""
    settings: dict[str, Value] = field(default_factory=dict)  # e.g. database_type


@dataclass
class Records:
    """Sample data. `columns` is None when the block names none (all columns, in order)."""

    table: str  # the real table name
    columns: list[str] | None
    rows: list[list[Value]] = field(default_factory=list)


class DBMLError(Exception):
    """The source is not valid DBML; the message gives the line and column."""


# --- Tokens --------------------------------------------------------------------------

_TOKENS = re.compile(
    r"""
    (?P<space>[ \t\r\f]+)
  | (?P<newline>\n)
  | (?P<comment>//[^\n]*|/\*.*?\*/)
  | (?P<triple>'''.*?(?<!\\)''')
  | (?P<string>'(?:\\.|[^'\\\n])*')
  | (?P<quoted>"(?:\\.|[^"\\\n])*")
  | (?P<expr>`[^`]*`)
  | (?P<color>\#[0-9A-Fa-f]+\b)
  | (?P<number>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?(?![A-Za-z_]))
  | (?P<word>\d*[A-Za-z_]\w*)
  | (?P<punct><>|[{}\[\]():,.<>\-~?;*])
    """,
    re.VERBOSE | re.DOTALL,
)


@dataclass
class _Token:
    kind: str  # newline, triple, string, quoted, expr, color, number, word, punct, end
    text: str
    start: int
    end: int
    line: int
    col: int


def _tokenise(source: str) -> list[_Token]:
    tokens, pos, line, line_start = [], 0, 1, 0
    while pos < len(source):
        match = _TOKENS.match(source, pos)
        if not match:
            raise DBMLError(
                f"line {line}, col {pos - line_start + 1}: unexpected {source[pos]!r}"
            )
        kind, text = match.lastgroup, match.group()
        if kind not in ("space", "comment"):
            tokens.append(
                _Token(kind, text, pos, match.end(), line, pos - line_start + 1)
            )
        newlines = text.count("\n")
        if newlines:
            line += newlines
            line_start = pos + text.rfind("\n") + 1
        pos = match.end()
    tokens.append(_Token("end", "", pos, pos, line, pos - line_start + 1))
    return tokens


def _unescape(text: str) -> str:
    return re.sub(r"\\(.)", r"\1", text)


def _string_value(token: _Token) -> str:
    if token.kind == "triple":
        body = textwrap.dedent(token.text[3:-3].removeprefix("\r\n").removeprefix("\n"))
        body = re.sub(r"\\\r?\n", "", body)  # a trailing backslash joins lines
        return _unescape(body).strip()
    return _unescape(token.text[1:-1])


# --- Parser ----------------------------------------------------------------------------


class DBML:
    """Parse DBML source; the result is in the attributes below."""

    def __init__(self, source: str) -> None:
        self.project: Project | None = None
        self.tables: list[Table] = []
        self.enums: list[Enum] = []
        self.refs: list[Ref] = []
        self.table_groups: list[TableGroup] = []
        self.sticky_notes: list[StickyNote] = []
        self.records: list[Records] = []

        self._tokens = _tokenise(source)
        self._pos = 0
        self._partials: dict[str, Table] = {}
        # id(table) -> its body in order: columns and (partial name, token) injections
        self._layouts: dict[int, list[Column | tuple[str, _Token]]] = {}
        self._pending_refs: list[tuple[Ref, _Token]] = []
        self._pending_indexes: list[tuple[Table, Index, _Token]] = []
        self._pending_groups: list[
            tuple[TableGroup, list[tuple[str | None, str, _Token]]]
        ] = []
        self._pending_records: list[tuple[Records, str | None, _Token]] = []

        self._parse_file()
        self._apply_partials()
        self._resolve_names()

    def table(self, name: str) -> Table:
        for t in self.tables:
            if t.name == name:
                return t
        raise KeyError(name)

    # -- token helpers --

    def _peek(self, skip_newlines: bool = True, ahead: int = 0) -> _Token:
        i, seen = self._pos, 0
        while True:
            token = self._tokens[i]
            if token.kind == "newline" and skip_newlines:
                i += 1
                continue
            if seen == ahead or token.kind == "end":
                return token
            seen += 1
            i += 1

    def _next(self, skip_newlines: bool = True) -> _Token:
        while skip_newlines and self._tokens[self._pos].kind == "newline":
            self._pos += 1
        token = self._tokens[self._pos]
        if token.kind != "end":
            self._pos += 1
        return token

    def _error(self, token: _Token, message: str) -> DBMLError:
        shown = "end of file" if token.kind == "end" else repr(token.text)
        return DBMLError(
            f"line {token.line}, col {token.col}: {message} (found {shown})"
        )

    def _is(self, token: _Token, *texts: str) -> bool:
        if token.kind == "word":
            return token.text.lower() in texts
        return token.kind == "punct" and token.text in texts

    def _expect(self, *texts: str, skip_newlines: bool = True) -> _Token:
        token = self._next(skip_newlines)
        if not self._is(token, *texts):
            raise self._error(token, f"expected {' or '.join(repr(t) for t in texts)}")
        return token

    def _accept(self, *texts: str, skip_newlines: bool = True) -> bool:
        if self._is(self._peek(skip_newlines), *texts):
            self._next(skip_newlines)
            return True
        return False

    def _name(self) -> str:
        token = self._next()
        if token.kind == "word":
            return token.text
        if token.kind == "quoted":
            return _string_value(token)
        raise self._error(token, "expected a name")

    def _dotted(self) -> list[str]:
        parts = [self._name()]
        while self._is(self._peek(False), "."):
            self._next(False)
            parts.append(self._name())
        return parts

    def _end_of_line(self) -> None:
        token = self._peek(False)
        if token.kind not in ("newline", "end") and not self._is(token, "}"):
            raise self._error(token, "expected the end of the line")

    # -- values, notes and settings --

    def _value(self) -> Value:
        token = self._next()
        if token.kind in ("string", "triple", "quoted"):
            return _string_value(token)
        if token.kind == "expr":
            return Expression(token.text[1:-1].strip())
        if token.kind in ("number", "color"):
            return _number(token.text) if token.kind == "number" else token.text
        if self._is(token, "-", "+") and self._peek(False).kind == "number":
            number = _number(self._next(False).text)
            return -number if token.text == "-" else number
        if token.kind == "word":
            words = [token.text]
            while self._peek(False).kind == "word":  # e.g. `set null`, `no action`
                words.append(self._next(False).text)
            text = " ".join(words)
            lowered = text.lower()
            if lowered in ("true", "false"):
                return lowered == "true"
            if lowered == "null":
                return None
            return text
        raise self._error(token, "expected a value")

    def _note_body(self) -> str:
        """After the word `note`: either `: 'text'` or `{ 'text' }`."""
        if self._accept(":", skip_newlines=False):
            token = self._next()
        else:
            self._expect("{")
            token = self._next()
            self._expect("}")
        if token.kind not in ("string", "triple"):
            raise self._error(token, "expected a note string")
        return _string_value(token)

    def _settings(self) -> list[tuple[str, object]]:
        """`[key, key: value, ...]` as (lower-case key, value) pairs, in order."""
        self._expect("[", skip_newlines=False)
        items: list[tuple[str, object]] = []
        if self._accept("]"):
            return items
        while True:
            words = [self._name()]
            while self._peek().kind == "word" and not self._is(self._peek(), ":"):
                words.append(self._name())  # `primary key`, `not null`
            key = " ".join(words).lower()
            if self._accept(":"):
                if key == "ref":
                    value = self._ref_target()
                elif key in ("headercolor", "color"):
                    token = self._next()
                    if token.kind != "color":
                        raise self._error(
                            token, "expected a hex colour such as #3498DB"
                        )
                    value = token.text
                else:
                    value = self._value()
            else:
                value = True
            items.append((key, value))
            if self._accept("]"):
                return items
            self._expect(",")

    # -- top level --

    def _parse_file(self) -> None:
        while True:
            token = self._peek()
            if token.kind == "end":
                return
            if token.kind != "word":
                raise self._error(
                    token,
                    "expected Project, Table, Enum, Ref, TableGroup, Note or records",
                )
            keyword = token.text.lower()
            handler = {
                "project": self._project,
                "table": self._table,
                "tablepartial": self._partial,
                "enum": self._enum,
                "ref": self._ref,
                "tablegroup": self._table_group,
                "note": self._sticky_note,
                "records": self._top_records,
            }.get(keyword)
            if handler is None:
                raise self._error(
                    token,
                    "expected Project, Table, Enum, Ref, TableGroup, Note or records",
                )
            handler()

    def _project(self) -> None:
        self._next()
        name = None if self._is(self._peek(), "{") else self._name()
        project = Project(name=name)
        self._expect("{")
        while not self._accept("}"):
            if self._is(self._peek(), "note") and self._is(
                self._peek(ahead=1), ":", "{"
            ):
                self._next()
                project.note = self._note_body()
                continue
            key = self._name()
            self._expect(":")
            project.settings[key] = self._value()
            self._end_of_line()
        self.project = project

    # -- tables and partials --

    def _table(self) -> None:
        self._next()
        parts = self._dotted()
        table = Table(name=parts[-1], schema=".".join(parts[:-1]) or None)
        if self._accept("as", skip_newlines=False):
            table.alias = self._name()
        if self._is(self._peek(False), "["):
            self._table_settings(table, self._settings())
        self._table_body(table, partial=False)
        self.tables.append(table)

    def _partial(self) -> None:
        self._next()
        partial = Table(name=self._name())
        if self._is(self._peek(False), "["):
            self._table_settings(partial, self._settings())
        self._table_body(partial, partial=True)
        self._partials[partial.name] = partial

    def _table_settings(self, table: Table, settings: list[tuple[str, object]]) -> None:
        for key, value in settings:
            if key == "headercolor":
                table.header_color = str(value)
            elif key == "note":
                table.note = str(value)
            else:
                table.settings[key] = value

    def _table_body(self, table: Table, partial: bool) -> None:
        layout = self._layouts.setdefault(id(table), [])
        self._expect("{")
        while True:
            token = self._peek()
            if self._is(token, "}"):
                self._next()
                return
            nxt = self._peek(ahead=1)
            if self._is(token, "~") and not partial:
                self._next()
                name_token = self._peek()
                layout.append((self._name(), name_token))
            elif self._is(token, "indexes") and self._is(nxt, "{"):
                self._next()
                self._indexes(table)
            elif self._is(token, "checks") and self._is(nxt, "{"):
                self._next()
                self._checks(table)
            elif (
                self._is(token, "records")
                and self._is(nxt, "(", "[", "{")
                and not partial
            ):
                self._next()
                self._records(table.name, None, token)
            elif self._is(token, "note") and self._is(nxt, ":", "{"):
                self._next()
                table.note = self._note_body()
            else:
                column = self._column(table)
                layout.append(column)
                if partial:
                    table.columns.append(column)

    def _column_type(self) -> str:
        start = self._peek()
        if start.kind not in ("word", "quoted"):
            raise self._error(start, "expected a column type")
        text = ".".join(self._dotted())
        if self._is(self._peek(False), "("):
            opening = self._next(False)
            depth = 1
            while depth:
                token = self._next()
                if token.kind == "end":
                    raise self._error(opening, "unclosed '(' in column type")
                depth += self._is(token, "(") - self._is(token, ")")
            text += self._source_between(opening, token)
        if self._is(self._peek(False), "[") and self._is(self._peek(False, 1), "]"):
            self._next(False)
            self._next(False)
            text += "[]"
        return text

    def _source_between(self, first: _Token, last: _Token) -> str:
        return "".join(
            t.text
            for t in self._tokens[
                self._tokens.index(first) : self._tokens.index(last) + 1
            ]
            if t.kind != "newline"
        )

    def _column(self, table: Table) -> Column:
        column = Column(name=self._name(), type=self._column_type())
        if self._is(self._peek(False), "["):
            for key, value in self._settings():
                if key in ("pk", "primary key"):
                    column.pk = True
                elif key == "not null":
                    column.not_null = True
                elif key == "null":
                    column.not_null = False
                elif key == "unique":
                    column.unique = True
                elif key == "increment":
                    column.increment = True
                elif key == "default":
                    column.default = value
                elif key == "note":
                    column.note = str(value)
                elif key == "check":
                    column.check = (
                        value
                        if isinstance(value, Expression)
                        else Expression(str(value))
                    )
                elif key == "ref":
                    op, left_opt, right_opt, target, token = value
                    ref = Ref(
                        left=RefEnd(
                            table=table.name, columns=[column.name], schema=table.schema
                        ),
                        op=op,
                        right=target,
                        left_optional=left_opt,
                        right_optional=right_opt,
                        inline=True,
                    )
                    self._pending_refs.append((ref, token))
                else:
                    column.settings[key] = value
        self._end_of_line()
        return column

    def _indexes(self, table: Table) -> None:
        self._expect("{")
        while not self._accept("}"):
            token = self._peek()
            columns: list[str | Expression] = []
            if self._accept("("):
                while True:
                    columns.append(self._index_part())
                    if self._accept(")"):
                        break
                    self._expect(",")
            else:
                columns.append(self._index_part())
            index = Index(columns=columns)
            if self._is(self._peek(False), "["):
                for key, value in self._settings():
                    if key in ("pk", "primary key"):
                        index.pk = True
                    elif key == "unique":
                        index.unique = True
                    elif key == "name":
                        index.name = str(value)
                    elif key == "type":
                        index.type = str(value)
                    elif key == "note":
                        index.note = str(value)
            self._end_of_line()
            table.indexes.append(index)
            self._pending_indexes.append((table, index, token))

    def _index_part(self) -> str | Expression:
        token = self._peek()
        if token.kind == "expr":
            self._next()
            return Expression(token.text[1:-1].strip())
        return self._name()

    def _checks(self, table: Table) -> None:
        self._expect("{")
        while not self._accept("}"):
            token = self._next()
            if token.kind != "expr":
                raise self._error(token, "expected a check expression in backticks")
            check = Check(expression=Expression(token.text[1:-1].strip()))
            if self._is(self._peek(False), "["):
                for key, value in self._settings():
                    if key == "name":
                        check.name = str(value)
            self._end_of_line()
            table.checks.append(check)

    # -- enums --

    def _enum(self) -> None:
        self._next()
        parts = self._dotted()
        enum = Enum(name=parts[-1], schema=".".join(parts[:-1]) or None)
        self._expect("{")
        while not self._accept("}"):
            if self._is(self._peek(), "note") and self._is(
                self._peek(ahead=1), ":", "{"
            ):
                raise self._error(
                    self._peek(),
                    "a Note can only appear inside a Table, TableGroup, TablePartial or Project",
                )
            value = EnumValue(name=self._name())
            if self._is(self._peek(False), "["):
                for key, setting in self._settings():
                    if key == "note":
                        value.note = str(setting)
            self._end_of_line()
            enum.values.append(value)
        self.enums.append(enum)

    # -- refs --

    def _ref_end(self) -> tuple[list[str], list[str]]:
        """`[schema.]table.column` or `[schema.]table.(a, b)`: (table path, columns)."""
        parts = [self._name()]
        while self._accept(".", skip_newlines=False):
            if self._accept("(", skip_newlines=False):
                columns = []
                while True:
                    columns.append(self._name())
                    if self._accept(")"):
                        return parts, columns
                    self._expect(",")
            parts.append(self._name())
        if len(parts) < 2:
            raise self._error(self._peek(), "expected table.column")
        return parts[:-1], [parts[-1]]

    def _operator(self) -> tuple[str, bool, bool]:
        left_optional = self._accept("?", skip_newlines=False)
        token = self._next()
        if not self._is(token, "<", ">", "-", "<>"):
            raise self._error(token, "expected a relationship operator (<, >, -, <>)")
        right_optional = self._accept("?", skip_newlines=False)
        return token.text, left_optional, right_optional

    def _ref_target(self):
        """The value of an inline `ref:` setting: operator and the referenced end."""
        token = self._peek()
        op, left_optional, right_optional = self._operator()
        path, columns = self._ref_end()
        end = RefEnd(
            table=path[-1], columns=columns, schema=".".join(path[:-1]) or None
        )
        return op, left_optional, right_optional, end, token

    def _ref(self) -> None:
        self._next()
        name = None
        if not self._is(self._peek(False), ":", "{"):
            name = self._name()
        if self._accept(":", skip_newlines=False):
            self._ref_line(name)
            return
        self._expect("{")
        self._ref_line(name)
        if not self._accept("}"):
            raise self._error(
                self._peek(), "a Ref block can only contain one relationship"
            )

    def _ref_line(self, name: str | None) -> None:
        token = self._peek()
        left_path, left_columns = self._ref_end()
        op, left_optional, right_optional = self._operator()
        right_path, right_columns = self._ref_end()
        ref = Ref(
            left=RefEnd(
                table=left_path[-1],
                columns=left_columns,
                schema=".".join(left_path[:-1]) or None,
            ),
            op=op,
            right=RefEnd(
                table=right_path[-1],
                columns=right_columns,
                schema=".".join(right_path[:-1]) or None,
            ),
            name=name,
            left_optional=left_optional,
            right_optional=right_optional,
        )
        if self._is(self._peek(False), "["):
            for key, value in self._settings():
                if key == "delete":
                    ref.on_delete = str(value).lower()
                elif key == "update":
                    ref.on_update = str(value).lower()
                elif key == "color":
                    ref.color = str(value)
        self._end_of_line()
        self._pending_refs.append((ref, token))

    # -- groups and sticky notes --

    def _table_group(self) -> None:
        self._next()
        group = TableGroup(name=self._name())
        if self._is(self._peek(False), "["):
            for key, value in self._settings():
                if key == "note":
                    group.note = str(value)
                elif key == "color":
                    group.color = str(value)
        members = []
        self._expect("{")
        while not self._accept("}"):
            if self._is(self._peek(), "note") and self._is(
                self._peek(ahead=1), ":", "{"
            ):
                self._next()
                group.note = self._note_body()
                continue
            token = self._peek()
            parts = self._dotted()
            members.append((".".join(parts[:-1]) or None, parts[-1], token))
            self._end_of_line()
        self._pending_groups.append((group, members))
        self.table_groups.append(group)

    def _sticky_note(self) -> None:
        self._next()
        name = self._name()
        self.sticky_notes.append(StickyNote(name=name, text=self._note_body()))

    # -- records --

    def _top_records(self) -> None:
        token = self._next()
        parts = self._dotted()
        self._records(parts[-1], ".".join(parts[:-1]) or None, token)

    def _records(self, table: str, schema: str | None, token: _Token) -> None:
        columns = None
        if self._accept("(", skip_newlines=False):
            columns = []
            while not self._accept(")"):
                columns.append(self._name())
                self._accept(",")
        records = Records(table=table, columns=columns)
        if self._is(self._peek(False), "["):
            raise self._error(self._peek(False), "records cannot have a settings list")
        self._expect("{")
        while not self._accept("}"):
            while self._peek(False).kind == "newline":
                self._next(False)
            records.rows.append(self._record_row())
        self._pending_records.append((records, schema, token))

    def _record_row(self) -> list[Value]:
        row: list[Value] = []
        expecting_value = True
        while True:
            token = self._peek(False)
            if token.kind in ("newline", "end") or self._is(token, "}"):
                if expecting_value and row:
                    row.append(None)  # trailing comma: an empty last field
                return row
            if self._is(token, ","):
                self._next(False)
                if expecting_value:
                    row.append(None)  # empty field between commas
                expecting_value = True
                continue
            if token.kind == "word" and self._is(self._peek(False, 1), "."):
                row.append(
                    self._dotted()[-1]
                )  # enum constant: status.active -> 'active'
            else:
                row.append(self._value())
            expecting_value = False

    # -- after parsing --

    def _apply_partials(self) -> None:
        """Expand `~partial` where it appears. The table's own columns win over a partial's,
        and a later partial wins over an earlier one."""
        for table in self.tables:
            layout = self._layouts.get(id(table), [])
            local = {item.name for item in layout if isinstance(item, Column)}
            columns: list[Column] = []
            from_partial: dict[str, int] = {}  # column name -> its index in `columns`
            for item in layout:
                if isinstance(item, Column):
                    columns.append(item)
                    continue
                name, token = item
                partial = self._partials.get(name)
                if partial is None:
                    raise self._error(token, f"unknown TablePartial '{name}'")
                for column in partial.columns:
                    if column.name in local:
                        continue
                    if column.name in from_partial:
                        columns[from_partial[column.name]] = column
                    else:
                        from_partial[column.name] = len(columns)
                        columns.append(column)
                table.indexes.extend(partial.indexes)
                table.checks.extend(partial.checks)
                table.note = table.note or partial.note
                table.header_color = table.header_color or partial.header_color
                for key, value in partial.settings.items():
                    table.settings.setdefault(key, value)
            table.columns = columns

    def _find(self, schema: str | None, name: str, token: _Token) -> Table:
        matches = [
            t
            for t in self.tables
            if (t.name == name or t.alias == name)
            and (schema is None or (t.schema or "public") == schema)
        ]
        if not matches:
            raise self._error(token, f"unknown table '{name}'")
        return matches[0]

    def _resolve_names(self) -> None:
        seen = set()
        for table in self.tables:
            key = (table.schema or "public", table.name)
            if key in seen:
                raise DBMLError(f"table '{table.name}' is defined more than once")
            seen.add(key)
        for ref, token in self._pending_refs:
            for end in (ref.left, ref.right):
                table = self._find(end.schema, end.table, token)
                end.table, end.schema = table.name, table.schema
                for column in end.columns:
                    try:
                        table.column(column)
                    except KeyError:
                        raise self._error(
                            token, f"unknown column '{table.name}.{column}'"
                        ) from None
            self.refs.append(ref)
        for table, index, token in self._pending_indexes:
            # an index on a partial is checked against each table it is injected into
            owners = (
                [table]
                if table in self.tables
                else [t for t in self.tables if any(i is index for i in t.indexes)]
            )
            for owner in owners:
                for column in index.columns:
                    if isinstance(column, str) and column not in {
                        c.name for c in owner.columns
                    }:
                        raise self._error(
                            token, f"unknown column '{owner.name}.{column}' in index"
                        )
        for group, members in self._pending_groups:
            group.tables = [
                self._find(schema, name, token).name for schema, name, token in members
            ]
        for records, schema, token in self._pending_records:
            table = self._find(schema, records.table, token)
            records.table = table.name
            for column in records.columns or []:
                try:
                    table.column(column)
                except KeyError:
                    raise self._error(
                        token, f"unknown column '{table.name}.{column}' in records"
                    ) from None
            self.records.append(records)


def _number(text: str) -> int | float:
    return int(text) if re.fullmatch(r"\d+", text) else float(text)
