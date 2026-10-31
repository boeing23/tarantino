from fastapi.testclient import TestClient

from app.main import create_app


def test_healthz_ok():
    with TestClient(create_app()) as c:
        r = c.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True
