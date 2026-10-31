from tests.conftest import recv_until


def beat(beat_id, duration_s=0.15, **kw):
    return {"type": "beat", "data": {"beat_id": beat_id, "text": f"text {beat_id}", "speaker": "Narrator", "duration_s": duration_s, **kw}}


def comment(text):
    return {"type": "comment", "data": {"text": text}}


def test_engine_gets_start_intent_on_connect(client):
    with client.websocket_connect("/ws/engine") as engine:
        i = recv_until(engine, "intent")["data"]
        assert i["window_id"] == 0 and i["intent"] == "start"


def test_beat_is_played_to_screens_and_opens_window(client):
    with client.websocket_connect("/ws/screen") as screen, client.websocket_connect("/ws/engine") as engine:
        recv_until(engine, "intent")
        engine.send_json(beat("b1", image_url="http://img/1.png"))
        b = recv_until(screen, "beat")["data"]
        assert b["beat_id"] == "b1" and b["image_url"] == "http://img/1.png"
        w = recv_until(screen, "window")["data"]
        assert w["window_id"] == 1 and w["state"] == "open" and w["locks_in_s"] > 0


def test_window_locks_before_beat_ends_and_engine_gets_winning_intent(client):
    with (
        client.websocket_connect("/ws/screen") as screen,
        client.websocket_connect("/ws/engine") as engine,
        client.websocket_connect("/ws/audience") as phone,
    ):
        recv_until(engine, "intent")
        engine.send_json(beat("b1", duration_s=1.0))
        recv_until(screen, "beat")
        for t in ["open the door", "Open the door!", "run"]:
            phone.send_json(comment(t))
            recv_until(phone, "ack")
        i = recv_until(engine, "intent")["data"]
        assert i["window_id"] == 1 and i["intent"] == "open the door" and i["comment_count"] == 3
        assert recv_until(screen, "intent")["data"]["top_suggestions"][1]["text"] == "run"


def test_silent_audience_sends_empty_intent(client):
    with client.websocket_connect("/ws/engine") as engine:
        recv_until(engine, "intent")
        engine.send_json(beat("b1"))
        i = recv_until(engine, "intent")["data"]
        assert i["window_id"] == 1 and i["intent"] is None and i["comment_count"] == 0


def test_queued_beats_play_in_order(client):
    with client.websocket_connect("/ws/screen") as screen, client.websocket_connect("/ws/engine") as engine:
        recv_until(engine, "intent")
        engine.send_json(beat("b1"))
        engine.send_json(beat("b2"))
        assert recv_until(screen, "beat")["data"]["beat_id"] == "b1"
        assert recv_until(screen, "beat")["data"]["beat_id"] == "b2"


def test_ending_beat_opens_no_window(client):
    with client.websocket_connect("/ws/screen") as screen, client.websocket_connect("/ws/engine") as engine:
        recv_until(engine, "intent")
        engine.send_json(beat("end", is_ending=True))
        engine.send_json(beat("after"))
        assert screen.receive_json()["data"]["beat_id"] == "end"
        assert screen.receive_json()["data"]["beat_id"] == "after"


def test_audience_sees_what_the_room_chose(client):
    with client.websocket_connect("/ws/engine") as engine, client.websocket_connect("/ws/audience") as phone:
        recv_until(engine, "intent")
        phone.send_json(comment("open the door"))
        recv_until(phone, "ack")
        engine.send_json(beat("b1"))
        assert recv_until(phone, "intent")["data"]["intent"] == "open the door"


def test_late_joiner_gets_current_state(client):
    with client.websocket_connect("/ws/engine") as engine, client.websocket_connect("/ws/audience") as phone:
        recv_until(engine, "intent")
        phone.send_json(comment("open the door"))
        recv_until(phone, "ack")
        engine.send_json(beat("b1", duration_s=0.2))
        recv_until(engine, "intent")
        engine.send_json(beat("b2", duration_s=5))
        recv_until(phone, "beat")
        recv_until(phone, "beat")
        with client.websocket_connect("/ws/screen") as screen:
            got = {m["type"]: m["data"] for m in (screen.receive_json() for _ in range(3))}
    assert got["beat"]["beat_id"] == "b2"
    assert got["window"]["state"] == "open" and 0 < got["window"]["locks_in_s"] <= 5
    assert got["intent"]["intent"] == "open the door"


def test_fresh_joiner_gets_nothing_before_show_starts(client):
    with client.websocket_connect("/ws/screen") as screen, client.websocket_connect("/ws/audience") as phone:
        phone.send_json(comment("hi"))
        assert recv_until(screen, "whisper", limit=1)
