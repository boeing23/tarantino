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


def test_every_audience_member_sees_all_comments(client):
    with client.websocket_connect("/ws/audience") as alice, client.websocket_connect("/ws/audience") as bob:
        alice.send_json(comment("open the door"))
        assert recv_until(bob, "whisper")["data"]["text"] == "open the door"
        assert recv_until(alice, "whisper")["data"]["text"] == "open the door"


def test_late_joiner_sees_recent_comments(client):
    with client.websocket_connect("/ws/audience") as alice:
        for t in ["one", "two", "three"]:
            alice.send_json(comment(t))
            recv_until(alice, "ack")
        with client.websocket_connect("/ws/audience") as late:
            texts = [late.receive_json()["data"]["text"] for _ in range(3)]
    assert texts == ["one", "two", "three"]


def test_comment_mood_must_be_a_bible_mood(client):
    with client.websocket_connect("/ws/audience") as phone:
        phone.send_json({"type": "comment", "data": {"text": "hmm", "mood": "furious"}})
        assert "mood" in recv_until(phone, "error")["data"]["message"]
        phone.send_json({"type": "comment", "data": {"text": "hmm", "mood": "suspicious"}})
        assert recv_until(phone, "ack")


def test_mood_only_vote_is_allowed(client):
    with client.websocket_connect("/ws/audience") as phone:
        phone.send_json({"type": "mood", "data": {"mood": "playful"}})
        assert recv_until(phone, "ack")
