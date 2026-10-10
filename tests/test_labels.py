from crud.labels import label


def test_label_turns_names_into_display_text():
    assert label("order_number") == "Order Number"
    assert label("metric") == "Metric"
    assert label("framework_reference") == "Framework Reference"
    assert label("MFA_status") == "MFA Status"  # rest of each word untouched
    assert label("Order Items") == "Order Items"  # already a label
    assert label("__odd__name_") == "Odd Name"  # stray underscores collapse


def test_labels_on_screen_but_raw_names_in_urls_and_fields(make_app):
    client = make_app(
        "Table order_line {\n  id int [pk]\n  order_number varchar\n}\n"
    ).test_client()
    form = client.get("/t/order_line/new").get_data(as_text=True)
    assert "<h1>New Order Line</h1>" in form
    assert 'for="f-order_number">Order Number</label>' in form
    assert 'name="order_number"' in form  # the form field keeps the column name
    listing = client.get("/t/order_line").get_data(as_text=True)
    assert "Order Number" in listing and "/t/order_line/new" in listing
