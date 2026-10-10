import pytest

from crud.schema import SchemaError, load_schema
from tests.conftest import TEST_DBML


def _dbml(tmp_path, *blocks: str):
    path = tmp_path / "s.dbml"
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path


def _table(name: str, *columns: str) -> str:
    return f"Table {name} {{\n" + "\n".join(columns) + "\n}\n"


def test_parses_test_dbml():
    schema = load_schema(TEST_DBML)
    assert list(schema.tables) == ["metric", "control"]

    domain = schema.table("control").column("domain")
    assert domain.kind == "enum"
    assert domain.enum_values == ["daily", "weekly", "monthly", "quarterly", "yearly"]

    assert schema.table("metric").pk.auto


def test_many_to_many_generates_join_table_named_like_dbml_export():
    schema = load_schema(TEST_DBML)
    [join] = schema.join_tables
    assert join.name == "metric_control"
    assert join.composite_key == ["metric_id", "control_id"]
    ref = join.columns[1].ref
    assert (ref.table, ref.column, ref.on_delete) == ("control", "id", "CASCADE")

    [link] = schema.table("metric").links
    assert (link.other_table, link.self_column, link.other_column) == (
        "control",
        "metric_id",
        "control_id",
    )
    assert schema.table("control").links[0].other_table == "metric"


def test_indexes(tmp_path):
    table = load_schema(
        _dbml(
            tmp_path,
            _table(
                "a",
                "id int [pk]",
                "x text",
                "y text",
                "indexes {",
                "(x, y) [unique]",
                "y [name: 'by_y']",
                "`lower(x)`",
                "}",
            ),
        )
    ).table("a")
    assert [(i.name, i.columns, i.unique) for i in table.indexes] == [
        ("uq_a_x_y", ["x", "y"], True),
        ("by_y", ["y"], False),
    ]  # the expression index is skipped


def test_skips_self_referencing_many_to_many_with_warning(tmp_path, caplog):
    schema = load_schema(
        _dbml(tmp_path, _table("a", "id int [pk]"), "Ref: a.id <> a.id")
    )
    assert "a" in schema.tables and not schema.join_tables
    assert "Skipping ref a.id <> a.id: self-referencing" in caplog.text


def test_one_to_many_ref(tmp_path):
    schema = load_schema(
        _dbml(
            tmp_path,
            _table("owner", "id int [pk]"),
            _table("pet", "id int [pk]", "owner_id int [not null, ref: > owner.id]"),
        )
    )
    ref = schema.table("pet").column("owner_id").ref
    assert (ref.table, ref.column, ref.on_delete) == ("owner", "id", "RESTRICT")
    assert ("pet", "owner_id") in schema.table("owner").referenced_by


def test_display_column_rule(tmp_path):
    schema = load_schema(
        _dbml(
            tmp_path,
            _table("a", "id int [pk]", "title text", "code varchar [unique]"),
            _table("b", "id int [pk]", "title text"),
            _table("c", "id int [pk]", "n int"),
        )
    )
    assert schema.table("a").display_column.name == "code"  # first unique text
    assert schema.table("b").display_column.name == "title"  # first text
    assert schema.table("c").display_column.name == "id"  # primary key


def test_ref_direction_and_nullable_default(tmp_path):
    schema = load_schema(
        _dbml(
            tmp_path,
            _table("parent", "id int [pk]"),
            _table("child", "id int [pk]", "parent_id int"),
            "Ref: parent.id < child.parent_id\n",
        )
    )
    column = schema.table("child").column("parent_id")
    assert column.ref.table == "parent"
    assert column.ref.on_delete == "SET NULL"


def test_unsupported_table_is_skipped_and_the_rest_still_loads(tmp_path, caplog):
    schema = load_schema(
        _dbml(
            tmp_path,
            _table("keyless", "name text"),
            _table("pair", "a int", "b int", "indexes {", "(a, b) [pk]", "}"),
            _table("ok", "id int [pk]", "keyless_name text [ref: > keyless.name]"),
        )
    )
    assert list(schema.tables) == ["ok"]
    assert "Skipping table keyless: needs exactly one primary key" in caplog.text
    assert "Skipping table pair: composite primary keys" in caplog.text
    # the ref into the skipped table is dropped, the column stays as plain data
    assert "Skipping ref ok.keyless_name > keyless.name" in caplog.text
    assert schema.table("ok").column("keyless_name").ref is None


def test_unparseable_file_is_still_an_error(tmp_path):
    with pytest.raises(SchemaError, match="Could not parse"):
        load_schema(_dbml(tmp_path, "Table {"))


def test_names_are_kept_exactly_as_written(tmp_path):
    table = load_schema(
        _dbml(tmp_path, _table('"Order Items"', "ID int [pk]", '"Unit Price" decimal'))
    ).table("Order Items")
    assert [c.name for c in table.columns] == ["ID", "Unit Price"]


def test_skips_names_differing_only_by_case(tmp_path, caplog):
    schema = load_schema(
        _dbml(
            tmp_path,
            _table("a", "id int [pk]", "Name text", "name text"),
            _table("Item", "id int [pk]"),
            _table("item", "id int [pk]"),
        )
    )
    assert list(schema.tables) == ["Item"]
    assert "'Name' and 'name' differ only by case" in caplog.text
    assert "Skipping table item: differs only by case from table 'Item'" in caplog.text


def test_text_shape_follows_the_declared_type(tmp_path):
    table = load_schema(
        _dbml(
            tmp_path,
            _table(
                "a",
                "id int [pk]",
                "body text",
                "title varchar(80)",
                "code char(3)",
                "label varchar",
                "price decimal(10,2)",
            ),
        )
    ).table("a")
    shape = {c.name: (c.multiline, c.max_length) for c in table.columns}
    assert shape["body"] == (True, None)
    assert shape["title"] == (False, 80)
    assert shape["code"] == (False, 3)
    assert shape["label"] == (False, None)
    assert shape["price"] == (False, None)  # numeric sizes are not text lengths
