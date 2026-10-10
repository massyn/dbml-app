import pytest

from crud.sync import SchemaDriftError


def _table(*columns: str) -> str:
    return "Table item {\n" + "\n".join(columns) + "\n}\n"


V1 = _table("id int [pk]", "name text")


def test_adds_new_columns(make_app):
    make_app(V1)
    app = make_app(_table("id int [pk]", "name text", "size int"))
    response = app.test_client().post("/t/item/new", data={"name": "a", "size": "3"})
    assert response.status_code == 302


def test_removed_column_stops_startup(make_app):
    make_app(V1)
    with pytest.raises(SchemaDriftError, match="name"):
        make_app(_table("id int [pk]"))


def test_changed_type_stops_startup(make_app):
    make_app(V1)
    with pytest.raises(SchemaDriftError, match="INTEGER"):
        make_app(_table("id int [pk]", "name int"))


def test_unaddable_not_null_column_stops_startup(make_app):
    make_app(V1).test_client().post("/t/item/new", data={"name": "existing row"})
    with pytest.raises(SchemaDriftError, match="code"):
        make_app(_table("id int [pk]", "name text", "code text [not null]"))


def test_unique_index_on_duplicate_data_stops_startup(make_app):
    client = make_app(V1).test_client()
    client.post("/t/item/new", data={"name": "same"})
    client.post("/t/item/new", data={"name": "same"})
    with pytest.raises(SchemaDriftError, match="duplicate"):
        make_app(_table("id int [pk]", "name text", "indexes {", "name [unique]", "}"))
