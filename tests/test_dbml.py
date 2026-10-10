"""The DBML parser (crud/dbml.py) against tests/monster.dbml, one test per feature area,
plus the errors invalid DBML must raise. Keep this in step with monster.dbml."""

from pathlib import Path

import pytest

from crud.dbml import DBML, DBMLError, Expression

MONSTER = Path(__file__).resolve().parent / "monster.dbml"


@pytest.fixture(scope="module")
def db() -> DBML:
    return DBML(MONSTER.read_text(encoding="utf-8"))


def _ref(db: DBML, left_table: str, left_column: str):
    return next(
        r
        for r in db.refs
        if r.left.table == left_table and left_column in r.left.columns
    )


# --- Comments, keywords, project ------------------------------------------------------


def test_comments_are_ignored_and_keywords_are_case_insensitive(db):
    names = [t.name for t in db.tables]
    assert "nope" not in names  # only mentioned inside a block comment
    assert {"orders", "order_items"} <= set(names)  # `TABLE` and `table`
    assert any(r.name == "optional_one" for r in db.refs)  # `REF`


def test_project(db):
    assert db.project.name == "monster_project"
    assert db.project.settings == {"database_type": "SQLite", "owner": "platform team"}
    assert db.project.note == (
        "# Monster\nEvery **DBML** feature in one file.\n- second line keeps its place"
    )


# --- Enums ----------------------------------------------------------------------------


def test_enums(db):
    status, grade = db.enums
    assert (status.schema, status.name) == ("core", "job_status")
    assert [(v.name, v.note) for v in status.values] == [
        ("created", "Waiting to be processed"),
        ("running", ""),
        ("done", ""),
        ("on hold", "Quoted value with a space"),
    ]
    assert grade.schema is None
    assert [v.name for v in grade.values] == ["A+", "A-", "Not Yet Set"]


# --- Tables ---------------------------------------------------------------------------


def test_table_schema_alias_settings_and_notes(db):
    users = db.table("users")
    assert (users.schema, users.alias) == ("core", "U")
    assert users.header_color == "#3498DB"
    assert users.settings == {"owner": "identity"}  # custom table property
    assert users.note == "Note block form overrides the settings note"
    assert db.table("orders").note == "Orders are placed by users"  # `Note:` form


def test_column_types_as_written(db):
    types = {c.name: c.type for c in db.table("users").columns}
    assert types["username"] == "varchar(255)"
    assert types["balance"] == "decimal(10,2)"
    assert types["ratio"] == "double precision"  # quoted multi-word type
    assert types["code"] == "character varying(20)"
    assert types["seen_at"] == "timestamp with time zone"
    assert types["tags"] == "varchar[]"  # array
    assert types["status"] == "core.job_status"  # schema-qualified enum
    assert types["grade"] == "grade"
    assert db.table("orders").column("total").type == "decimal(12,2)"  # space in args


def test_column_settings(db):
    users = db.table("users")
    col = users.column
    assert col("id").pk and col("id").increment
    assert col("username").not_null is True and col("username").unique
    assert col("email").not_null is False  # explicit `null`
    assert col("Full Name").not_null is None  # neither given; quoted column name
    assert col("username").note == "Login name"
    assert col("bio").note == "A multi-line note\non a column"
    assert col("age").check == Expression("age >= 0")
    assert col("legacy_id").settings == {"classification": "internal"}
    assert db.table("orders").column("id").pk  # long form `primary key`


def test_default_values(db):
    defaults = {c.name: c.default for c in db.table("users").columns}
    assert defaults["age"] == 21
    assert defaults["balance"] == -1.5
    assert defaults["ratio"] == 1500.0  # 1.5e3
    assert defaults["status"] == "created"
    assert defaults["is_admin"] is False and defaults["is_active"] is True
    assert defaults["nickname"] is None
    assert defaults["motto"] == "It's fine"  # escaped quote
    assert defaults["seen_at"] == Expression("now() - interval '5 days'")


def test_columns_named_like_keywords(db):
    names = [c.name for c in db.table("users").columns]
    assert {"note", "records", "indexes"} <= set(names)


def test_indexes(db):
    indexes = db.table("users").indexes
    assert [(i.columns, i.unique, i.name, i.type, i.note) for i in indexes] == [
        (["username"], False, None, None, ""),
        (["username", "email"], True, "uq_users_login", None, ""),
        ([Expression("lower(email)")], False, "ix_email_lower", "hash", ""),
        (
            [Expression("id * 3"), "age"],
            False,
            None,
            None,
            "Mixed expression and column",
        ),
        (["email"], False, None, "btree", ""),
    ]
    (composite_pk,) = db.table("order_items").indexes
    assert composite_pk.columns == ["order_id", "product_id"] and composite_pk.pk


def test_checks(db):
    assert [(c.expression.text, c.name) for c in db.table("users").checks] == [
        ("age < 200", "chk_age_upper"),
        ("balance > -1000", None),
    ]


def test_table_partials(db):
    audited = db.table("audited")
    # injected where `~partial` appears; the table's own column wins over both partials,
    # and for a column only in partials the later partial would win
    assert [(c.name, c.type) for c in audited.columns] == [
        ("id", "int"),
        ("created_at", "timestamp"),
        ("title", "varchar"),
        ("created_by", "varchar(100)"),
        ("updated_at", "date"),
    ]
    assert audited.column("created_at").default == Expression("now()")
    assert [i.name for i in audited.indexes] == ["ix_created"]  # partial's index
    assert audited.header_color == "#111111"  # partial's settings
    assert audited.note == "Shared by every table"
    assert "base_template" not in [t.name for t in db.tables]  # partials are not tables


# --- Refs -----------------------------------------------------------------------------


def test_inline_refs_resolve_aliases_and_schemas(db):
    by_alias = _ref(db, "orders", "user_id")
    assert (by_alias.op, by_alias.right.table, by_alias.right.schema) == (
        ">",
        "users",
        "core",
    )
    assert by_alias.inline
    by_schema = _ref(db, "orders", "ship_to_user_id")
    assert (by_schema.right.table, by_schema.right.columns) == ("users", ["id"])
    one_to_one = _ref(db, "user_profiles", "user_id")
    assert one_to_one.op == "-"


def test_short_and_named_refs_with_settings(db):
    short = _ref(db, "order_items", "product_id")
    assert (short.name, short.on_delete, short.on_update) == (
        None,
        "cascade",
        "no action",
    )
    named = _ref(db, "products", "merchant_id")
    assert named.name == "fk_merchant"
    assert named.left.columns == ["merchant_id", "country_code"]  # composite
    assert named.right.columns == ["id", "country_code"]
    assert (named.on_delete, named.color) == ("set null", "#79AD51")


def test_long_form_refs(db):
    many_to_many = _ref(db, "products", "id")
    assert (many_to_many.name, many_to_many.op, many_to_many.right.table) == (
        "product_tags",
        "<>",
        "tags",
    )
    unnamed_block = _ref(db, "user_profiles", "website")
    assert (unnamed_block.name, unnamed_block.right.columns) == (None, ["label"])


def test_optional_refs(db):
    right_optional = _ref(db, "orders", "coupon_tag_id")
    assert (
        right_optional.op,
        right_optional.left_optional,
        right_optional.right_optional,
    ) == (
        ">",
        False,
        True,
    )
    left_optional = _ref(db, "tags", "label")
    assert (left_optional.op, left_optional.left_optional) == ("<", True)
    assert (left_optional.on_update, left_optional.on_delete) == (
        "restrict",
        "set default",
    )


def test_every_ref_is_found(db):
    assert len(db.refs) == 11


# --- Records --------------------------------------------------------------------------


def test_records_inside_a_table(db):
    orders = next(r for r in db.records if r.table == "orders")
    assert orders.columns == ["id", "user_id", "total", "status", "placed_at"]
    assert orders.rows == [
        [1, 1, 99.5, "done", "2024-01-15 10:30:00"],  # enum constant -> its value
        [2, 1, -3, "running", Expression("now()")],  # comment after the row is ignored
        [3, 2, 150.0, None, None],  # 1.5e2, an empty field and null
    ]


def test_records_without_columns(db):
    products = next(r for r in db.records if r.table == "products")
    assert products.columns is None
    assert products.rows == [[10, 1, "AU", "Widget, large"], [11, 1, "NZ", "Gadget"]]


def test_top_level_records(db):
    users = next(r for r in db.records if r.table == "users")
    assert users.columns[3] == "Full Name"  # quoted column name
    alice, bob, carol = users.rows
    assert alice == [
        1,
        "alice",
        "alice@example.com",
        "Alice Smith",
        True,
        False,
        "Say 'hi'",
    ]
    assert bob[3] == "Bob\n  Jones" and bob[4:] == [
        False,
        True,
        "",
    ]  # multi-line string
    assert carol[-1] is None and len(carol) == 7  # trailing comma: empty last field


def test_every_records_block_is_found(db):
    assert [r.table for r in db.records] == ["orders", "products", "users", "tags"]


# --- Groups and sticky notes ----------------------------------------------------------


def test_table_groups(db):
    commerce, reference = db.table_groups
    # members resolve `public.products` and the alias `U` to real table names
    assert commerce.tables == ["orders", "order_items", "products", "users"]
    assert commerce.note == "Note inside the group overrides the setting"
    assert commerce.color == "#E67E22"
    assert (reference.name, reference.tables) == (
        "Reference data",
        ["tags", "merchants"],
    )


def test_sticky_notes(db):
    assert [(n.name, n.text) for n in db.sticky_notes] == [
        ("sticky_one", "A single-line sticky note"),
        (
            "sticky_two",
            "A multi-line sticky note joined by a trailing backslash.\nSecond line.",
        ),
    ]


def test_table_lookup(db):
    assert db.table("tags").column("label").unique
    with pytest.raises(KeyError):
        db.table("nope")


# --- Invalid DBML ---------------------------------------------------------------------

T = "Table a {\n  id int [pk]\n  name varchar\n}\n"


@pytest.mark.parametrize(
    "source, message",
    [
        (T + "Ref: a.id > b.id\n", "line 5, col 6: unknown table 'b'"),
        (T + "Ref: a.nope > a.id\n", "line 5, col 6: unknown column 'a.nope'"),
        (
            "Table a {\n  id int [pk, ref: > a.missing]\n}\n",
            "unknown column 'a.missing'",
        ),
        (
            "Table a {\n  id int [pk]\n  indexes {\n    nope\n  }\n}\n",
            "line 4, col 5: unknown column 'a.nope' in index",
        ),
        (
            "Table a {\n  id int\n  ~nope\n}\n",
            "line 3, col 4: unknown TablePartial 'nope'",
        ),
        (T + T, "table 'a' is defined more than once"),
        (T + "records b(id) {\n  1\n}\n", "line 5, col 1: unknown table 'b'"),
        (T + "records a(nope) {\n  1\n}\n", "unknown column 'a.nope' in records"),
        (
            "Table a {\n  id int [note: 'unterminated]\n}\n",
            "line 2, col 17: unexpected",
        ),
        ("Table a {\n  id int @\n}\n", "line 2, col 10: unexpected '@'"),
        ("Table a [headercolor: 'red'] {\n  id int\n}\n", "expected a hex colour"),
        ("Table a {\n  id\n}\n", "line 3, col 1: expected a column type"),
        ("Tabel a {\n  id int\n}\n", "line 1, col 1: expected Project, Table"),
        ("Table a {\n  id int [pk]\n", "expected a name (found end of file)"),
        # rules dbdiagram.io enforces
        (
            "Enum e {\n  a\n  Note: 'x'\n}\n",
            "line 3, col 3: a Note can only appear inside a Table",
        ),
        (
            T + "Ref {\n  a.id > a.id\n  a.name > a.name\n}\n",
            "line 7, col 3: a Ref block can only contain one relationship",
        ),
        (T + "records a(id) [x] {\n  1\n}\n", "records cannot have a settings list"),
    ],
)
def test_invalid_dbml_raises_with_location(source, message):
    with pytest.raises(DBMLError, match=None) as caught:
        DBML(source)
    assert message in str(caught.value)


# --- The monster in the full app -------------------------------------------------------


def test_monster_loads_into_the_app(make_app, caplog):
    client = make_app(MONSTER.read_text(encoding="utf-8")).test_client()
    # unsupported pieces are skipped with a warning; the rest renders
    assert "Skipping table order_items: composite primary keys" in caplog.text
    assert "Skipping ref products.merchant_id, country_code" in caplog.text
    for table in ["users", "orders", "products", "user_profiles", "tags", "audited"]:
        assert client.get(f"/t/{table}").status_code == 200, table
        assert client.get(f"/t/{table}/new").status_code == 200, table
    assert "3 records" in client.get("/t/orders").get_data(as_text=True)
    assert client.get("/").status_code == 200
