import asyncio

import pytest

from app.bible import load_bible
from app.contract import AudienceIntent, Suggestion
from engine.generate import load_generator, scripted
from engine.story import Story


def intent(window_id, text=None, mood_votes=None):
    tops = [Suggestion(text=text, votes=2)] if text else []
    return AudienceIntent(window_id=window_id, intent=text, top_suggestions=tops, mood_votes=mood_votes or {})


@pytest.fixture
def bible():
    return load_bible()


def run_through(story, intents):
    kinds = []
    for i in intents:
        story.advance(i)
        kinds.append((story.kind, story.spec.get("id")))
    return kinds


def test_story_walks_opening_beats_then_ending(bible):
    story = Story(bible)
    kinds = run_through(story, [intent(n) for n in range(len(bible["beats"]) + 2)])
    assert kinds[0] == ("opening", None)
    assert [k for k, _ in kinds[1:-1]] == ["beat"] * len(bible["beats"])
    assert [i for _, i in kinds[1:-1]] == [b["id"] for b in bible["beats"]]
    assert kinds[-1][0] == "ending" and story.done


def test_ending_follows_mood_tally_among_eligible_endings(bible):
    story = Story(bible)
    story.state["flags"]["mara_told_truth"] = True
    run_through(story, [intent(0)] + [intent(n, mood_votes={"trusting": 3, "suspicious": 1}) for n in range(1, 7)])
    assert story.spec["id"] == "ending_justice"


def test_ending_requires_flags(bible):
    story = Story(bible)
    run_through(story, [intent(0)] + [intent(n, mood_votes={"trusting": 3}) for n in range(1, 7)])
    assert story.spec["id"] == "ending_betrayal"


def test_reset_restarts_from_opening(bible):
    story = Story(bible)
    run_through(story, [intent(0), intent(1), intent(2)])
    story.reset()
    story.advance(intent(0))
    assert story.kind == "opening" and story.mood_tally == {}


def test_scripted_opening_uses_bible_lines_and_beat_seconds(bible):
    story = Story(bible, beat_seconds=7)
    story.advance(intent(0))
    beat = asyncio.run(scripted(story, intent(0)))
    assert beat.bible_beat_id == "opening" and beat.duration_s == 7
    assert [l.text for l in beat.lines] == [l["text"] for l in bible["opening"]["lines"]]
    assert beat.text == bible["opening"]["narration"]


def test_scripted_beat_carries_audience_intent(bible):
    story = Story(bible)
    story.advance(intent(0))
    story.advance(intent(1, "Search Pell's luggage", {"suspicious": 2}))
    beat = asyncio.run(scripted(story, intent(1, "Search Pell's luggage", {"suspicious": 2})))
    assert beat.bible_beat_id == bible["beats"][0]["id"]
    assert "Search Pell's luggage" in beat.text
    assert beat.acknowledged_whispers == ["Search Pell's luggage"]
    assert beat.mood == "suspicious"


def test_scripted_ending_is_marked(bible):
    story = Story(bible)
    for n in range(len(bible["beats"]) + 2):
        story.advance(intent(n))
    beat = asyncio.run(scripted(story, intent(9)))
    assert beat.is_ending and beat.ending_id == story.spec["id"]


def test_load_generator_from_dotted_path():
    assert load_generator("engine.generate:scripted") is scripted
