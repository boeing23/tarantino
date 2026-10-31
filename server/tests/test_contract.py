import pytest
from pydantic import ValidationError

from app.contract import AudienceIntent, Beat, Clip, Comment, Hello, Suggestion, envelope, parse


def test_beat_minimal_fields_and_defaults():
    b = Beat(beat_id="b1", text="It was a dark night.", speaker="Narrator")
    assert b.image_url is None and b.audio_url is None
    assert b.acknowledged_whispers == []
    assert b.duration_s > 0


def test_beat_tolerates_unknown_fields_for_forward_compat():
    b = Beat.model_validate({"beat_id": "b1", "text": "x", "speaker": "N", "mood": "tense"})
    assert b.model_dump()["mood"] == "tense"


def test_intent_shape():
    i = AudienceIntent(
        window_id=3,
        intent="open the door",
        confidence=0.6,
        top_suggestions=[Suggestion(text="open the door", votes=3), Suggestion(text="run", votes=2)],
    )
    d = i.model_dump()
    assert d["top_suggestions"][1] == {"text": "run", "votes": 2, "examples": []}
    assert "is_fallback" not in d


def test_comment_text_is_trimmed_and_bounded():
    assert Comment(text="  hi  ").text == "hi"
    with pytest.raises(ValidationError):
        Comment(text="   ")
    with pytest.raises(ValidationError):
        Comment(text="x" * 1000)


def test_envelope_roundtrip():
    b = Beat(beat_id="b1", text="t", speaker="s")
    msg = envelope("beat", b)
    assert msg["v"] == 1 and msg["type"] == "beat" and msg["data"]["beat_id"] == "b1"
    typ, model = parse(msg)
    assert typ == "beat" and isinstance(model, Beat)


def test_parse_rejects_unknown_type():
    with pytest.raises(ValueError):
        parse({"type": "nope", "data": {}})


def test_beat_carries_ordered_shots_with_optional_video():
    b = Beat.model_validate({
        "beat_id": "c1", "text": "t", "speaker": "narrator", "lock_lead_s": 40,
        "shots": [
            {"shot_id": "s0", "index": 0, "duration_s": 6, "video_url": "http://v/0.mp4",
             "line": {"speaker": "dev", "text": "We're pre-seed."}},
            {"shot_id": "s1", "index": 1, "duration_s": 6},
        ],
    })
    assert b.shots[0].line.speaker == "dev" and b.shots[1].video_url is None
    assert b.lock_lead_s == 40 and b.ending_id is None


def test_clip_and_hello_parse():
    typ, clip = parse({"type": "clip", "data": {"beat_id": "c1", "shot_id": "s1", "video_url": "http://v/1.mp4"}})
    assert typ == "clip" and isinstance(clip, Clip)
    typ, hello = parse({"type": "hello", "data": {"moods": ["hype", "chaotic"], "lock_lead_s": 40}})
    assert typ == "hello" and isinstance(hello, Hello) and hello.moods == ["hype", "chaotic"]
