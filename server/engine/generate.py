import importlib
from typing import Awaitable, Callable

from app.contract import AudienceIntent, Beat, Line
from engine.story import Story

Generator = Callable[[Story, AudienceIntent], Awaitable[Beat]]


def _shot_lines(shots: list[dict]) -> list[Line]:
    return [Line(**s["line"]) for s in shots if s.get("line")]


async def scripted(story: Story, intent: AudienceIntent) -> Beat:
    spec, n = story.spec, story.position
    common = {
        "beat_id": f"{story.kind}-{n}",
        "duration_s": story.beat_seconds,
        "mood": story.state["mood"],
        "acknowledged_whispers": [s.text for s in intent.top_suggestions],
    }
    if story.kind == "opening":
        lines = [Line(**l) for l in spec["lines"]]
        return Beat(**common, text=spec["narration"], speaker="narrator", lines=lines, bible_beat_id="opening")
    lines = _shot_lines(spec["shots"])
    speaker = lines[0].speaker if lines else "narrator"
    if story.kind == "ending":
        return Beat(**common, text=spec["summary"], speaker=speaker, lines=lines, is_ending=True, ending_id=spec["id"])
    text = spec["must_hit"] + "." + (f" The room wanted: {intent.intent}." if intent.intent else "")
    return Beat(**common, text=text, speaker=speaker, lines=lines, bible_beat_id=spec["id"])


def choose_generator(env) -> str:
    if env.get("ENGINE_GENERATOR"):
        return env["ENGINE_GENERATOR"]
    return "engine.video:generate" if env.get("FAL_KEY") else "engine.generate:scripted"


def load_generator(path: str) -> Generator:
    module, _, attr = path.partition(":")
    return getattr(importlib.import_module(module), attr)
