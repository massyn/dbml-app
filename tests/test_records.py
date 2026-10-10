"""DBML `records` blocks, loaded when a table is first created.

Parsing records in detail is covered by test_dbml.py; these tests cover loading them.
"""

from crud.dbml import DBML, Expression

SEEDED = r"""
Table owner {
  id int [pk]
  name varchar
  active bool
  records (id, name, active) {
    1, 'Sam', true
    2, 'O\'Brien, Pat', 'N'   // escaped quote and comma inside a string
  }
}

Table pet {
  id uuid [pk]
  name varchar
  owner_id int [ref: > owner.id]
  born timestamp
}

// Child rows before the parent's top-level block: foreign keys are checked at commit
records pet(name, owner_id, born) {
  'Rex', 1, `now()`
  'Tom', 2,
}

"""


def test_records_are_parsed_in_file_order():
    blocks = DBML(SEEDED).records
    assert [b.table for b in blocks] == ["owner", "pet"]
    assert blocks[0].rows[1] == [2, "O'Brien, Pat", "N"]
    assert isinstance(blocks[1].rows[0][2], Expression)


def test_records_are_loaded_into_new_tables(make_app):
    client = make_app(SEEDED).test_client()
    owners = client.get("/t/owner").get_data(as_text=True)
    assert "Sam" in owners and "O&#39;Brien, Pat" in owners and "2 records" in owners
    pets = client.get("/t/pet").get_data(as_text=True)
    assert "Rex" in pets and "Tom" in pets  # uuid keys generated, now() evaluated


def test_records_are_not_loaded_twice(make_app):
    make_app(SEEDED)
    client = make_app(SEEDED).test_client()  # second start: tables already exist
    assert "2 records" in client.get("/t/owner").get_data(as_text=True)


def test_bad_records_are_rolled_back_and_the_app_still_starts(make_app, caplog):
    client = make_app(
        "Table a {\n  id int [pk]\n  name varchar [not null]\n"
        "  records (id, name) {\n    1, 'ok'\n    2, null\n  }\n}\n"
    ).test_client()
    assert "Could not load the DBML records" in caplog.text
    assert "No records yet" in client.get("/t/a").get_data(as_text=True)


def test_valid_records_the_app_cannot_use_are_warned_about(make_app, caplog):
    # Unknown tables or columns are invalid DBML (a parse error, see test_dbml.py);
    # these are valid DBML the app cannot fully load.
    client = make_app(
        "Table a {\n  id int [pk]\n  at timestamp\n  flag bool\n"
        "  records (id, at, flag) {\n"
        "    1, `date_trunc('day', now())`, 'maybe'\n"
        "    2, null, true, 'one too many'\n"
        "  }\n}\n"
    ).test_client()
    assert "expression `date_trunc('day', now())` in at is not supported" in caplog.text
    assert "'maybe' is not a boolean for flag" in caplog.text
    assert "row 2 has more values than columns; skipped" in caplog.text
    assert "1 record" in client.get("/t/a").get_data(as_text=True)
