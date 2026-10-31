from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import recv_until
from tests.test_show import beat


def test_reset_restarts_show_and_clears_state(client):
    with client.websocket_connect("/ws/engine") as engine, client.websocket_connect("/ws/screen") as screen:
        recv_until(engine, "intent")
        engine.send_json(beat("b1", duration_s=5))
        recv_until(screen, "beat")
        assert client.post("/admin/reset").status_code == 200
        assert recv_until(screen, "reset")
        i = recv_until(engine, "intent")["data"]
        assert i["window_id"] == 0 and i["intent"] == "start"
        with client.websocket_connect("/ws/screen") as late:
            engine.send_json(beat("opening", duration_s=5))
            assert recv_until(late, "beat")["data"]["beat_id"] == "opening"


def test_reset_requires_token_when_configured(settings):
    settings.admin_token = "s3cret"
    with TestClient(create_app(settings)) as c:
        assert c.post("/admin/reset").status_code == 403
        assert c.post("/admin/reset?token=nope").status_code == 403
        assert c.post("/admin/reset?token=s3cret").status_code == 200
