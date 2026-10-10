import pytest

# One-to-many coverage: test.dbml now only has a many-to-many ref.
ONE_TO_MANY = """
Table owner {
  id uuid [pk]
  name varchar [unique]
}
Table pet {
  id uuid [pk]
  name varchar [not null]
  owner_id uuid [not null, ref: > owner.id]
}
"""


def _create(client, table: str, **data) -> str:
    response = client.post(f"/t/{table}/new?modal=1", data=data)
    body = response.get_json()
    assert body["ok"], body
    return body["id"]


@pytest.fixture
def fk_client(make_app):
    return make_app(ONE_TO_MANY).test_client()


def test_pages_render(client):
    for url in [
        "/",
        "/t/metric",
        "/t/metric/new",
        "/t/control/new",
        "/t/control?modal=1",
    ]:
        assert client.get(url).status_code == 200, url
    assert client.get("/t/nope").status_code == 404
    assert client.get("/t/metric_control").status_code == 404  # join table has no views


def test_create_generates_uuid_and_returns_label(client):
    response = client.post("/t/metric/new?modal=1", data={"name": "MFA coverage"})
    body = response.get_json()
    assert body["ok"] and len(body["id"]) == 36
    assert body["label"] == "MFA coverage"


def test_unique_and_required_are_enforced(client):
    _create(client, "metric", name="dup")
    body = client.post("/t/metric/new?modal=1", data={"name": "dup"}).get_json()
    assert not body["ok"] and "already has this value" in body["html"]

    body = client.post("/t/control/new?modal=1", data={"name": ""}).get_json()
    assert not body["ok"] and "Required" in body["html"]


def test_composite_unique_index_is_enforced(client):
    _create(client, "control", name="c", domain="daily")
    _create(client, "control", name="c", domain="weekly")
    body = client.post(
        "/t/control/new?modal=1", data={"name": "c", "domain": "daily"}
    ).get_json()
    assert not body["ok"] and "control.name, control.domain" in body["html"]


def test_enum_rejects_unknown_value(client):
    body = client.post(
        "/t/control/new?modal=1", data={"name": "c", "domain": "hourly"}
    ).get_json()
    assert not body["ok"] and "Must be one of" in body["html"]


# Tables with only multi-line text (doc) and with a single-line column (tag).
TEXT_ONLY = """
Table doc {
  id uuid [pk]
  body text
}
Table tag {
  id uuid [pk]
  label varchar
}
"""


def test_edit_updates_record(make_app):
    client = make_app(TEXT_ONLY).test_client()
    doc = _create(client, "doc", body="old")
    response = client.post(f"/t/doc/{doc}/edit", data={"body": "new"})
    assert response.status_code == 302
    form = client.get(f"/t/doc/{doc}/edit").get_data(as_text=True)
    assert ">new</textarea>" in form


def test_generated_id_is_shown_read_only(make_app):
    client = make_app(TEXT_ONLY).test_client()
    doc = _create(client, "doc", body="b")
    form = client.get(f"/t/doc/{doc}/edit").get_data(as_text=True)
    assert f'<div class="id-value">{doc}</div>' in form
    assert f'name="id" value="{doc}"' not in form  # not an editable field
    assert "Assigned automatically when saved" in client.get("/t/doc/new").get_data(
        as_text=True
    )
    # doc has only multi-line text, so its list falls back to the key
    listing = client.get("/t/doc").get_data(as_text=True)
    assert f'<td class="cell-id" title="{doc}">' in listing
    # tag has a single-line label to show, so its key stays off the list
    tag = _create(client, "tag", label="t")
    listing = client.get("/t/tag").get_data(as_text=True)
    assert "cell-id" not in listing and f">{tag}<" not in listing


def test_multiline_text_is_left_out_of_lists_but_still_searchable(client):
    _create(client, "metric", name="Patch latency", description="Long\nstory")
    listing = client.get("/t/metric?q=story").get_data(as_text=True)
    assert "1 record" in listing  # matched on the hidden description
    assert "DESCRIPTION" not in listing.upper().split("<TBODY>")[0].split("<THEAD>")[1]


# --- many-to-many (metric <> control) ---


def test_links_saved_from_either_side(client):
    metric = _create(client, "metric", name="Patch latency")
    c1 = _create(client, "control", name="Vuln mgmt")
    c2 = _create(client, "control", name="Asset inventory")

    client.post(
        f"/t/metric/{metric}/edit",
        data={"name": "Patch latency", "__link_control": [c1, c2, c1]},
    )
    edit = client.get(f"/t/metric/{metric}/edit").get_data(as_text=True)
    assert "Vuln mgmt" in edit and "Asset inventory" in edit

    # The control side sees the same link, and the list shows linked labels.
    assert "Patch latency" in client.get(f"/t/control/{c1}/edit").get_data(as_text=True)
    listing = client.get("/t/metric").get_data(as_text=True)
    assert "Vuln mgmt" in listing and "Asset inventory" in listing

    # Submitting without the field clears the links.
    client.post(f"/t/metric/{metric}/edit", data={"name": "Patch latency"})
    assert "Vuln mgmt" not in client.get(f"/t/metric/{metric}/edit").get_data(
        as_text=True
    )


def test_link_to_missing_record_rolls_back_the_save(client):
    body = client.post(
        "/t/metric/new?modal=1",
        data={"name": "m", "__link_control": "00000000-0000-0000-0000-000000000000"},
    ).get_json()
    assert not body["ok"] and "linked record does not exist" in body["html"]
    assert "No records" in client.get("/t/metric").get_data(as_text=True)


def test_deleting_a_record_removes_only_its_links(client):
    metric = _create(client, "metric", name="m")
    control = _create(client, "control", name="c")
    client.post(
        f"/t/metric/{metric}/edit", data={"name": "m", "__link_control": control}
    )

    assert client.post(f"/t/metric/{metric}/delete?modal=1").get_json()["ok"]
    assert "No records" not in client.get("/t/control").get_data(as_text=True)


# --- one-to-many ---


def test_cannot_delete_linked_record(fk_client):
    owner = _create(fk_client, "owner", name="Sam")
    pet = _create(fk_client, "pet", name="Rex", owner_id=owner)

    body = fk_client.post(f"/t/owner/{owner}/delete?modal=1").get_json()
    assert not body["ok"] and "1 Pet record" in body["error"]

    assert fk_client.post(f"/t/pet/{pet}/delete?modal=1").get_json()["ok"]
    assert fk_client.post(f"/t/owner/{owner}/delete?modal=1").get_json()["ok"]


def test_fk_to_missing_record_is_rejected(fk_client):
    body = fk_client.post(
        "/t/pet/new?modal=1",
        data={"name": "Rex", "owner_id": "00000000-0000-0000-0000-000000000000"},
    ).get_json()
    assert not body["ok"] and "linked record does not exist" in body["html"]


def test_list_shows_fk_labels_and_searches_them(fk_client):
    owner = _create(fk_client, "owner", name="Sam")
    _create(fk_client, "pet", name="Rex", owner_id=owner)

    html = fk_client.get("/t/pet?q=sam").get_data(as_text=True)
    assert "Sam" in html and "Rex" in html and "1 record" in html
    assert "No records" in fk_client.get("/t/pet?q=zzz").get_data(as_text=True)


def test_names_with_spaces_and_capitals_work_end_to_end(make_app):
    client = make_app(
        'Table "Order Items" {\n'
        "  ID int [pk]\n"
        '  "Unit Price" decimal [not null]\n'
        "}\n"
    ).test_client()
    assert client.get("/t/Order Items/new").status_code == 200
    item = _create(client, "Order Items", **{"Unit Price": "9.5"})
    html = client.get("/t/Order Items").get_data(as_text=True)
    assert "Unit Price" in html and "9.5" in html
    assert client.post(f"/t/Order Items/{item}/delete?modal=1").get_json()["ok"]


def test_text_is_a_text_area_and_varchar_a_single_line(make_app):
    client = make_app(
        "Table note {\n id int [pk]\n title varchar(5) [not null]\n body text\n}\n"
    ).test_client()
    form = client.get("/t/note/new").get_data(as_text=True)
    assert '<textarea class="form-control" id="f-body" name="body"' in form
    assert (
        'id="f-title" name="title" value="" placeholder="Enter Title" maxlength="5"'
        in form
    )

    body = client.post(
        "/t/note/new?modal=1", data={"title": "too long", "body": "line 1\nline 2"}
    ).get_json()
    assert not body["ok"] and "Maximum 5 characters" in body["html"]
    assert "line 1\nline 2</textarea>" in body["html"]  # submitted text kept on error
