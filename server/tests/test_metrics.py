from tests.conftest import recv_until
from tests.test_show import beat, comment


def test_metrics_track_connections_comments_and_show(client, settings):
    settings.blocklist = {"bad"}
    with client.websocket_connect("/ws/engine") as engine, client.websocket_connect("/ws/audience") as phone:
        recv_until(engine, "intent")
        phone.send_json(comment("hello"))
        recv_until(phone, "ack")
        phone.send_json(comment("bad"))
        recv_until(phone, "error")
        engine.send_json(beat("b1", duration_s=0.1))
        recv_until(engine, "intent")
        m = client.get("/metrics").json()
    assert m["connections"] == {"audience": 1, "screen": 0, "engine": 1}
    assert m["comments_total"] == 1 and m["comments_rejected"] == 1
    assert m["beats_total"] == 1 and m["windows_total"] == 1
    assert m["current_beat_id"] == "b1"


def test_engine_latency_measured_from_intent_to_next_beat(client):
    with client.websocket_connect("/ws/engine") as engine:
        recv_until(engine, "intent")
        engine.send_json(beat("b1", duration_s=0.1))
        recv_until(engine, "intent")
        engine.send_json(beat("b2", duration_s=0.1))
        recv_until(engine, "intent")
    m = client.get("/metrics").json()
    assert m["engine_latency_s"]["count"] == 2
    assert 0 <= m["engine_latency_s"]["last"] < 1
