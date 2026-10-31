import logging
import time

import pytest
from starlette.websockets import WebSocketDisconnect

from tests.conftest import recv_until
from tests.test_show import beat, comment


@pytest.fixture
def events(caplog):
    caplog.set_level(logging.INFO, logger="tarantino")

    def names():
        return [r.getMessage().split(" ")[0] for r in caplog.records if r.name == "tarantino"]

    def line(name):
        return next(r.getMessage() for r in caplog.records if r.getMessage().startswith(name + " "))

    def wait(name, count=1):
        deadline = time.monotonic() + 2
        while names().count(name) < count and time.monotonic() < deadline:
            time.sleep(0.01)

    names.line = line
    names.wait = wait
    return names


def test_connect_and_disconnect_are_logged_with_counts(client, events):
    with client.websocket_connect("/ws/screen"):
        pass
    events.wait("ws.disconnect")
    assert events()[:2] == ["ws.connect", "ws.disconnect"]
    assert "role=screen" in events.line("ws.connect") and "screen=1" in events.line("ws.connect")
    assert "screen=0" in events.line("ws.disconnect")


def test_unknown_role_logged(client, events):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/nope") as ws:
            ws.receive_json()
    assert "role=nope" in events.line("ws.rejected")


def test_comments_and_invalid_messages_logged(client, settings, events):
    settings.blocklist = {"bad"}
    with client.websocket_connect("/ws/audience") as phone:
        phone.send_json(comment("open the door"))
        recv_until(phone, "ack")
        phone.send_json(comment("bad"))
        recv_until(phone, "error")
        phone.send_text("garbage")
        recv_until(phone, "error")
    events.wait("msg.invalid")
    assert 'text="open the door"' in events.line("comment.accepted")
    assert "comment.rejected" in events()
    assert "msg.invalid" in events()


def test_show_play_by_play(client, events):
    with client.websocket_connect("/ws/engine") as engine:
        recv_until(engine, "intent")
        engine.send_json(beat("b1", duration_s=0.1))
        recv_until(engine, "intent")
    events.wait("intent.sent", 2)
    seq = [e for e in events() if not e.startswith("ws.")]
    assert seq == ["intent.sent", "beat.received", "beat.play", "window.open", "window.lock", "intent.sent"]
    assert "beat_id=b1" in events.line("beat.play")
    assert "latency_s=" in events.line("beat.received")
