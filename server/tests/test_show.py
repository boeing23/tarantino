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


def shots(*urls):
    return [{"shot_id": f"s{i}", "index": i, "duration_s": 0.1, "video_url": u} for i, u in enumerate(urls)]


def clip(beat_id, shot_id, url):
    return {"type": "clip", "data": {"beat_id": beat_id, "shot_id": shot_id, "video_url": url}}


def test_clip_for_playing_beat_is_forwarded_to_screens(client):
    with client.websocket_connect("/ws/screen") as screen, client.websocket_connect("/ws/engine") as engine:
        recv_until(engine, "intent")
        engine.send_json(beat("c1", duration_s=2, shots=shots("http://v/0.mp4", None)))
        recv_until(screen, "beat")
        engine.send_json(clip("c1", "s1", "http://v/1.mp4"))
        c = recv_until(screen, "clip")["data"]
        assert c["beat_id"] == "c1" and c["shot_id"] == "s1"


def test_clip_that_arrives_before_its_beat_plays_is_merged_in(client):
    with client.websocket_connect("/ws/screen") as screen, client.websocket_connect("/ws/engine") as engine:
        recv_until(engine, "intent")
        engine.send_json(beat("c1", duration_s=0.3))
        engine.send_json(beat("c2", shots=shots("http://v/0.mp4", None)))
        engine.send_json(clip("c2", "s1", "http://v/1.mp4"))
        assert recv_until(screen, "beat")["data"]["beat_id"] == "c1"
        b = recv_until(screen, "beat")["data"]
        assert b["beat_id"] == "c2" and b["shots"][1]["video_url"] == "http://v/1.mp4"


def test_late_screen_gets_clips_already_received(client):
    with client.websocket_connect("/ws/engine") as engine:
        recv_until(engine, "intent")
        engine.send_json(beat("c1", duration_s=5, shots=shots("http://v/0.mp4", None)))
        engine.send_json(clip("c1", "s1", "http://v/1.mp4"))
        engine.send_json({"type": "hello", "data": {"moods": ["hype"]}})
        with client.websocket_connect("/ws/screen") as screen:
            got = {m["type"]: m["data"] for m in (screen.receive_json() for _ in range(3))}
    assert got["hello"]["moods"] == ["hype"]
    assert got["beat"]["shots"][1]["video_url"] == "http://v/1.mp4"


def test_hello_reaches_phones_and_sets_lock_lead(client):
    with client.websocket_connect("/ws/engine") as engine, client.websocket_connect("/ws/audience") as phone:
        recv_until(engine, "intent")
        engine.send_json({"type": "hello", "data": {"phone_prompt": "What should Dev do?", "lock_lead_s": 0.5}})
        assert recv_until(phone, "hello")["data"]["phone_prompt"] == "What should Dev do?"
        engine.send_json(beat("c1", duration_s=2))
        w = recv_until(phone, "window")["data"]
        assert w["state"] == "open" and w["locks_in_s"] <= 1.5


def test_beat_lock_lead_overrides_default(client):
    with client.websocket_connect("/ws/screen") as screen, client.websocket_connect("/ws/engine") as engine:
        recv_until(engine, "intent")
        engine.send_json(beat("c1", duration_s=2, lock_lead_s=1.5))
        w = recv_until(screen, "window")["data"]
        assert w["locks_in_s"] <= 0.5


def test_bridge_plays_without_window_or_intent_and_chapter_follows(client):
    with client.websocket_connect("/ws/screen") as screen, client.websocket_connect("/ws/engine") as engine:
        recv_until(engine, "intent")
        engine.send_json(beat("bridge1", duration_s=0.2, is_bridge=True))
        engine.send_json(beat("c1", duration_s=5))
        first = screen.receive_json()
        assert first["type"] == "beat" and first["data"]["beat_id"] == "bridge1" and first["data"]["is_bridge"]
        nxt = screen.receive_json()
        assert nxt["type"] == "beat" and nxt["data"]["beat_id"] == "c1"


def test_bridge_does_not_count_as_engine_latency(client):
    with client.websocket_connect("/ws/engine") as engine:
        recv_until(engine, "intent")
        engine.send_json(beat("bridge1", duration_s=0.1, is_bridge=True))
        engine.send_json(beat("c1", duration_s=5))
        recv_until(engine, "window")
    assert client.get("/metrics").json()["engine_latency_s"]["count"] == 1
