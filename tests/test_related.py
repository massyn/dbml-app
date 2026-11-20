import re

import pytest

MODEL = """
Table owner {
  id integer [pk]
  name varchar [unique, not null]
}
Table pet {
  id integer [pk]
  name varchar [not null]
  owner_id integer [not null, ref: > owner.id]
  carer_id integer [ref: > owner.id]
}
Table tag {
  id integer [pk]
  name varchar
}
Ref: owner.id <> tag.id
"""


def _create(client, table: str, **data):
    body = client.post(f"/t/{table}/new?modal=1", data=data).get_json()
    assert body["ok"], body
    return body["id"]


@pytest.fixture
def client(make_app):
    client = make_app(MODEL).test_client()
    ann = _create(client, "owner", name="Ann")
    bob = _create(client, "owner", name="Bob")
    _create(client, "pet", name="Rex", owner_id=ann)
    _create(client, "pet", name="Tom", owner_id=ann, carer_id=bob)
    _create(client, "pet", name="Kit", owner_id=bob)
    client.ids = {"ann": ann, "bob": bob}
    return client


def test_edit_page_has_a_panel_per_foreign_key(client):
    page = client.get(f"/t/owner/{client.ids['ann']}/edit").get_data(as_text=True)
    panels = re.findall(r'data-embed data-url="([^"]+)"', page)
    assert panels == [
        f"/t/pet?embed=1&amp;f.owner_id={client.ids['ann']}",
        f"/t/pet?embed=1&amp;f.carer_id={client.ids['ann']}",
    ]
    # Two refs from the same table are told apart by column; the m2m link is not a panel.
    assert "Pet (Owner ID)" in page and "Pet (Carer ID)" in page
    assert "/t/tag?embed" not in page


def test_new_page_has_no_panels(client):
    assert "data-embed" not in client.get("/t/owner/new").get_data(as_text=True)


def test_embedded_list_shows_only_the_children(client):
    html = client.get(f"/t/pet?embed=1&f.owner_id={client.ids['ann']}").get_data(
        as_text=True
    )
    assert "Rex" in html and "Tom" in html and "Kit" not in html
    assert "2 records" in html
    # The filtered column is the same on every row, so it is not a column.
    assert "Owner ID" not in html and "Carer ID" in html
    # Rows open in the modal; New prefills the link; navigation stays embedded.
    assert 'data-modal-push data-url="/t/pet/' in html
    assert f"/t/pet/new?modal=1&amp;f.owner_id={client.ids['ann']}" in html
    assert "data-embed-link" in html and "data-embed-search" in html
    assert f'name="f.owner_id" value="{client.ids["ann"]}"' in html


def test_filter_combines_with_search(client):
    html = client.get(f"/t/pet?embed=1&f.owner_id={client.ids['ann']}&q=Tom").get_data(
        as_text=True
    )
    assert "Tom" in html and "Rex" not in html and "1 record<" in html


def test_new_form_is_prefilled_from_filter(client):
    html = client.get(f"/t/pet/new?modal=1&f.owner_id={client.ids['bob']}").get_data(
        as_text=True
    )
    assert f'name="owner_id" value="{client.ids["bob"]}"' in html
    assert 'value="Bob"' in html  # the picker shows the parent's label


@pytest.mark.parametrize(
    "query", ["f.nope=1", "f.owner_id=abc"], ids=["unknown column", "bad value"]
)
def test_bad_filters_are_refused(client, query):
    assert client.get(f"/t/pet?embed=1&{query}").status_code == 400


def test_page_list_also_filters(client):
    html = client.get(f"/t/pet?f.carer_id={client.ids['bob']}").get_data(as_text=True)
    assert "Tom" in html and "Rex" not in html
