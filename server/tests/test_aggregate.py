import asyncio

from app.aggregate import naive_aggregate


def run(comments, window_id=1):
    return asyncio.run(naive_aggregate(window_id, comments))


def test_empty_window_has_no_intent():
    i = run([])
    assert i.intent is None and i.top_suggestions == [] and i.confidence == 0
    assert i.window_id == 1 and i.comment_count == 0
    assert "is_fallback" not in i.model_dump()


def test_majority_wins_with_normalisation():
    i = run(["Open the door!", "open door", "OPEN THE DOOR", "run away", "run away!!", "sing"])
    assert i.intent == "Open the door!"
    assert i.confidence == 0.5
    assert [(s.text, s.votes) for s in i.top_suggestions] == [
        ("Open the door!", 3), ("run away", 2), ("sing", 1)
    ]
    assert i.comment_count == 6


def test_top_suggestions_capped_at_three_with_examples():
    i = run(["a1", "b2", "c3", "d4", "a1"])
    assert len(i.top_suggestions) == 3
    assert i.top_suggestions[0].examples == ["a1", "a1"]
