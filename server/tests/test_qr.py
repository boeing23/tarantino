from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_join_url_defaults_to_request_host(client):
    assert client.get("/join").json()["url"] == "http://testserver/"


def test_join_url_uses_public_url_when_set():
    with TestClient(create_app(Settings(public_url="https://show.example.com"))) as c:
        assert c.get("/join").json()["url"] == "https://show.example.com/"


def test_qr_svg(client):
    r = client.get("/qr.svg")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in r.text


def test_screen_page_shows_qr(client):
    assert "/qr.svg" in client.get("/screen").text
