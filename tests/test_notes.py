NOTED = """
Project inventory {
  database_type: 'SQLite'
  Note: '''
  Tracks the kit we own.
  Second line.
  '''
}

Table item {
  id int [pk]
  name varchar [note: 'What the item is called']
  Note: 'Things we own'
}
"""

PLAIN = """
Table item {
  id int [pk]
  name text
}
"""


def test_project_name_and_note_on_home_page(make_app):
    html = make_app(NOTED).test_client().get("/").get_data(as_text=True)
    assert "<title>Inventory</title>" in html
    assert "Tracks the kit we own.<br />\nSecond line." in html  # line breaks kept
    assert "Things we own" in html  # table note on the card


def test_table_and_column_notes_on_list_and_form(make_app):
    client = make_app(NOTED).test_client()
    listing = client.get("/t/item").get_data(as_text=True)
    assert "Things we own" in listing
    assert 'title="What the item is called"' in listing  # column header tooltip

    form = client.get("/t/item/new").get_data(as_text=True)
    assert "Things we own" in form
    assert '<div class="form-text md"><p>What the item is called</p>' in form


def test_notes_render_markdown_safely(make_app):
    html = (
        make_app(
            "Table item {\n"
            "  id int [pk]\n"
            "  Note: '''\n"
            "  **Bold** and `code`\n"
            "  <script>alert(1)</script>\n"
            "  [bad](javascript:alert(1)) [good](https://example.com)\n"
            "  '''\n"
            "}\n"
        )
        .test_client()
        .get("/t/item")
        .get_data(as_text=True)
    )
    assert "<strong>Bold</strong>" in html and "<code>code</code>" in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert 'href="javascript:' not in html
    assert '<a href="https://example.com">good</a>' in html


def test_without_project_falls_back_to_default_title(make_app):
    html = make_app(PLAIN).test_client().get("/").get_data(as_text=True)
    assert "<title>DBML CRUD</title>" in html
