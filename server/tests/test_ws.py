import pytest
from starlette.websockets import WebSocketDisconnect

from tests.conftest import recv_until


def comment(text):
    return {"type": "comment", "data": {"text": text}}


def test_comment_is_acked_and_whispered_to_screens(client):
    with client.websocket_connect("/ws/screen") as screen, client.websocket_connect("/ws/audience") as phone:
        phone.send_json(comment("open the door"))
        ack = recv_until(phone, "ack")
        assert ack["data"]["window_id"] == 1
        w = recv_until(screen, "whisper")
        assert w["data"] == {"window_id": 1, "text": "open the door"}


def test_bad_message_returns_error_and_keeps_socket_open(client):
    with client.websocket_connect("/ws/audience") as phone:
        phone.send_json({"type": "comment", "data": {"text": ""}})
        assert recv_until(phone, "error")["data"]["message"]
        phone.send_text("not json")
        assert recv_until(phone, "error")
        phone.send_json(comment("still here"))
        assert recv_until(phone, "ack")


def test_audience_cannot_send_beats(client):
    with client.websocket_connect("/ws/audience") as phone:
        phone.send_json({"type": "beat", "data": {"beat_id": "x", "text": "t", "speaker": "s"}})
        assert recv_until(phone, "error")


def test_blocked_words_are_not_whispered(client, settings):
    settings.blocklist = {"badword"}
    with client.websocket_connect("/ws/screen") as screen, client.websocket_connect("/ws/audience") as phone:
        phone.send_json(comment("BadWord here"))
        assert recv_until(phone, "error")
        phone.send_json(comment("fine"))
        assert recv_until(screen, "whisper")["data"]["text"] == "fine"


def test_unknown_role_rejected(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/hacker") as ws:
            ws.receive_json()
