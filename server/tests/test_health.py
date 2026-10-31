from fastapi.testclient import TestClient

from app.main import create_app


def test_healthz_ok():
    with TestClient(create_app()) as c:
        r = c.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_healthz_reports_boot_version_that_changes_per_process():
    with TestClient(create_app()) as a, TestClient(create_app()) as b:
        va, vb = a.get("/healthz").json()["version"], b.get("/healthz").json()["version"]
    assert va and vb and va != vb


def test_pages_reload_when_server_version_changes():
    with TestClient(create_app()) as c:
        js = c.get("/static/live.js").text
    assert "/healthz" in js and "location.reload()" in js
