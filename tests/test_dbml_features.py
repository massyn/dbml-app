"""TableGroups, sticky notes, header colours, enum notes, type names and one-to-one refs."""

import pytest

from crud.schema import SchemaError, load_schema

FEATURES = """
Table metric [headercolor: #E67E22] {
  id int [pk]
  name varchar
  frequency freq
}

Table control {
  id int [pk]
  name varchar
}

Table orphan {
  id int [pk]
  name varchar
}

Enum freq {
  daily [note: 'Every working day']
  weekly
}

TableGroup measurement [note: 'What we measure'] {
  metric
  control
}

Note reminder {
  'Review the metrics quarterly'
}
"""


def test_groups_and_sticky_notes_on_home_page(make_app):
    html = make_app(FEATURES).test_client().get("/").get_data(as_text=True)
    assert html.index("measurement") < html.index("Other tables")
    assert "What we measure" in html
    assert "Review the metrics quarterly" in html


def test_sidebar_groups_tables_and_keeps_ungrouped_ones(make_app):
    from crud import get_schema

    app = make_app(FEATURES)
    groups = [(g.name, g.tables) for g in get_schema(app).nav_groups]
    assert groups == [
        ("measurement", ["metric", "control"]),
        ("Other tables", ["orphan"]),
    ]


def test_header_colour_used_as_table_accent(make_app):
    client = make_app(FEATURES).test_client()
    assert 'style="--table-accent: #E67E22"' in client.get("/t/metric").get_data(
        as_text=True
    )


def test_header_colour_must_be_a_hex_colour(tmp_path):
    # The parser rejects anything but a hex colour, so nothing else can reach the
    # inline style; schema.py re-checks the format as a second line of defence.
    path = tmp_path / "s.dbml"
    path.write_text(
        'Table a [headercolor: "red;background:url(x)"] {\n  id int [pk]\n}\n',
        encoding="utf-8",
    )
    with pytest.raises(SchemaError, match="Could not parse"):
        load_schema(path)


def test_enum_value_notes_become_hints(make_app):
    form = make_app(FEATURES).test_client().get("/t/metric/new").get_data(as_text=True)
    assert 'data-note="Every working day"' in form
    assert "data-enum-hint-text" in form


def test_type_names(tmp_path, caplog):
    path = tmp_path / "s.dbml"
    path.write_text(
        "Table a {\n"
        "  id int [pk]\n"
        '  ratio "double precision"\n'
        '  code "character varying(12)"\n'
        '  at "timestamp with time zone"\n'
        "  shape geometry\n"
        "}\n",
        encoding="utf-8",
    )
    table = load_schema(path).table("a")
    kinds = {c.name: (c.kind, c.max_length) for c in table.columns}
    assert kinds["ratio"] == ("real", None)
    assert kinds["code"] == ("text", 12)
    assert kinds["at"] == ("datetime", None)
    assert kinds["shape"] == ("text", None)
    assert "Unrecognised column type 'geometry': treated as text" in caplog.text


def test_one_to_one_allows_each_record_to_be_linked_once(make_app):
    client = make_app(
        "Table person {\n  id int [pk]\n  name varchar\n}\n"
        "Table passport {\n  id int [pk]\n  number varchar\n"
        "  person_id int [ref: - person.id]\n}\n"
    ).test_client()
    client.post("/t/person/new", data={"name": "Sam"})
    first = client.post(
        "/t/passport/new?modal=1", data={"number": "A1", "person_id": "1"}
    ).get_json()
    second = client.post(
        "/t/passport/new?modal=1", data={"number": "B2", "person_id": "1"}
    ).get_json()
    assert first["ok"]
    assert not second["ok"] and "already has this value" in second["html"]


def test_sidebar_groups_are_collapsible(make_app):
    html = make_app(FEATURES).test_client().get("/t/orphan").get_data(as_text=True)
    sidebar = html.split('<nav class="sidebar-nav">')[1].split("</nav>")[0]
    # one toggle per group, each controlling the block that holds its tables
    assert sidebar.count('data-bs-toggle="collapse"') == 2
    measurement = sidebar.split('data-nav-group="measurement">')[1].split("</div>")[0]
    assert "/t/metric" in measurement and "/t/control" in measurement
    other = sidebar.split('data-nav-group="Other tables">')[1].split("</div>")[0]
    assert "/t/orphan" in other and "sidebar-link active" in other
