import re

import pytest

TOKEN = re.compile(r'name="csrf_token" value="([^"]+)"')


@pytest.fixture
def csrf_client(make_app):
    return make_app(csrf=True).test_client()


def _token(client, url: str) -> str:
    match = TOKEN.search(client.get(url).get_data(as_text=True))
    assert match, f"no csrf_token on {url}"
    return match.group(1)


def test_modal_post_without_token_is_refused(csrf_client):
    response = csrf_client.post("/t/metric/new?modal=1", data={"name": "MFA"})
    assert response.status_code == 400
    assert response.get_json() == {
        "ok": False,
        "error": "This form has expired. Please try again.",
    }
    assert csrf_client.get("/t/metric").get_data(as_text=True).count("MFA") == 0


def test_page_post_without_token_redirects_back_with_message(csrf_client):
    response = csrf_client.post(
        "/t/metric/new",
        data={"name": "MFA"},
        headers={"Referer": "http://localhost/t/metric/new"},
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/t/metric/new"
    page = csrf_client.get("/t/metric/new").get_data(as_text=True)
    assert "This form has expired" in page


def test_foreign_referrer_is_not_followed(csrf_client):
    response = csrf_client.post(
        "/t/metric/new", data={}, headers={"Referer": "https://evil.example/x"}
    )
    assert response.headers["Location"] == "/"


def test_post_with_token_from_form_succeeds(csrf_client):
    token = _token(csrf_client, "/t/metric/new?modal=1")
    body = csrf_client.post(
        "/t/metric/new?modal=1", data={"name": "MFA", "csrf_token": token}
    ).get_json()
    assert body["ok"], body


def test_delete_forms_carry_token(csrf_client):
    token = _token(csrf_client, "/t/metric/new?modal=1")
    pk = csrf_client.post(
        "/t/metric/new?modal=1", data={"name": "MFA", "csrf_token": token}
    ).get_json()["id"]
    page = csrf_client.get(f"/t/metric/{pk}/edit").get_data(as_text=True)
    modal = csrf_client.get(f"/t/metric/{pk}/edit?modal=1").get_data(as_text=True)
    # Page: save form and delete-confirm form; modal: save form and inline delete form.
    assert len(TOKEN.findall(page)) == 2
    assert len(TOKEN.findall(modal)) == 2
    body = csrf_client.post(
        f"/t/metric/{pk}/delete?modal=1", data={"csrf_token": token}
    ).get_json()
    assert body == {"ok": True}
