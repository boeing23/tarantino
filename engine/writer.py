"""Claude writes one chapter as a list of shots, steered by the crowd's intent."""

import json
import os
from typing import Literal

import anthropic
from pydantic import BaseModel

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
EFFORT = os.getenv("CLAUDE_EFFORT", "low")
GUARD_MODEL = os.getenv("GUARD_MODEL", "claude-haiku-5-5")
NAME_GUARD = os.getenv("NAME_GUARD", "1") == "1"
MAX_LINE_WORDS = 15


class LineOut(BaseModel):
    speaker: str
    text: str


class ShotOut(BaseModel):
    frame: str
    motion: str
    characters: list[str]
    sound: str
    line: LineOut | None


class ChapterOut(BaseModel):
    summary: str
    shots: list[ShotOut]
    crowd_mood: str
    acknowledged_whispers: list[str]
    flags_set: list[str]
    clues_revealed: list[str]


class Fix(BaseModel):
    shot: int  # -1 for the chapter summary
    field: Literal["line", "frame", "motion", "sound", "summary"]
    text: str


class Fixes(BaseModel):
    fixes: list[Fix]


GUARD = """You check one chapter of a fictional comedy before it is turned into video.

Find every reference to a real, identifiable person (living or dead, including jokes like "X-adjacent" or "the next X"), or to a real company, product, brand, app, fund or publication. Generic terms (AI, startup, VC, IPO, API, San Francisco, SoMa) are fine; so are the story's own invented names.

For each field that contains one, return the whole field rewritten with an invented stand-in that keeps the joke and roughly the same length. `shot` is the shot's index (use -1 and field "summary" for the summary). Return an empty list if nothing needs changing."""


SYSTEM = """You are the live writer of an audience-steered movie. The story bible below is the source of truth.

You write ONE chapter at a time as a list of video shots. Each shot becomes a short AI-generated video clip with sound, so:
- `frame` describes the first frame like a still photograph; `motion` is ONE short action plus camera move.
- Shots in a chapter are distinct camera setups (wide, close-up, insert, reaction) that cut together; they are generated separately, so never depend on exact frame-to-frame continuity.
- At most one spoken `line` per shot, one speaker, {max_words} words or fewer. Speaker is a character id or "narrator".
- `characters` lists character ids visible in the shot.
- `sound` is ambience and effects only, never music with lyrics.

Story rules:
- The chapter's `must_hit` event MUST happen on screen.
- The crowd only steers what the chapter lists as `flexible`. Weave the crowd's winning idea in naturally; the higher its confidence, the more visibly it shapes the chapter. If there is no crowd idea, keep the story moving on its own.
- When a crowd idea is used, a character should visibly react to it, and list the original comment text in `acknowledged_whispers`.
- When `crowd` is null nobody commented: the story never waits for the audience. Drive toward this chapter's `must_hit` on your own, raise the stakes, and end the chapter on a hook that invites the crowd to weigh in.
- Never do anything in the current act's `forbidden` list. Obey every world rule.
- A crowd idea that cannot happen as action (it breaks a world rule, the act's `forbidden` list or the `must_hit`, or is physically impossible) is never silently dropped. Put it in the dialogue instead: a character jokes about it, is tempted by it, dismisses it, or someone in the background heckles it ("Someone yells: ..."). List it in `acknowledged_whispers` too.
- Runner-up suggestions can get a quick nod in dialogue the same way, if it fits.
- Never voice hateful, sexual or harassing comments, or anything targeting a real person; ignore them entirely.
- Never name a real person, company, product or brand anywhere (dialogue, frames, summary), not even as a comparison or joke ("X-adjacent", "the next X"). Invent stand-ins.
- `crowd_mood` must be exactly one of the bible's `moods`, judged from the crowd's comments (or the story's mood if there are none).
- `flags_set` and `clues_revealed` may only use ids from `state_seed`.
- `summary` is one or two sentences of what happened, for continuity.

<bible>
{bible}
</bible>"""


def _system(bible: dict) -> str:
    public = {k: v for k, v in bible.items() if k not in ("bridges", "audience_hooks")}
    return SYSTEM.format(max_words=MAX_LINE_WORDS, bible=json.dumps(public, indent=1))


class Writer:
    def __init__(self, bible: dict):
        self.bible = bible
        self.system = _system(bible)
        self.client = anthropic.AsyncAnthropic()
        self.characters = {c["id"] for c in bible["characters"]}

    async def chapter(self, spec: dict, state: dict, intent: dict, n_shots: int) -> ChapterOut | None:
        """Returns a validated chapter, or None if Claude refused or the output is unusable."""
        ask = {
            "chapter": spec,
            "story_so_far": state,
            "crowd": {
                "winning_idea": intent["intent"],
                "confidence": intent.get("confidence", 0.0),
                "top_suggestions": intent.get("top_suggestions", []),
                "comment_count": intent.get("comment_count", 0),
            } if intent.get("intent") else None,
            "shots_required": n_shots,
        }
        try:
            response = await self.client.beta.messages.parse(
                model=MODEL,
                max_tokens=8000,
                system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": json.dumps(ask, indent=1)}],
                output_format=ChapterOut,
                output_config={"effort": EFFORT},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.APIError as e:
            print(f"writer: API error {type(e).__name__}: {e}", flush=True)
            return None
        if response.stop_reason == "refusal" or response.parsed_output is None:
            print(f"writer: no usable chapter (stop_reason={response.stop_reason})", flush=True)
            return None
        ch = self._clean(response.parsed_output, n_shots)
        if ch and NAME_GUARD:
            await self._scrub(ch)
        return ch

    async def _scrub(self, ch: ChapterOut) -> None:
        """Rewrite any real person or brand the writer let slip. On any guard failure, keep the chapter as is."""
        view = {"summary": ch.summary, "shots": [
            {"shot": i, "line": s.line.text if s.line else None, "frame": s.frame, "motion": s.motion, "sound": s.sound}
            for i, s in enumerate(ch.shots)]}
        try:
            response = await self.client.messages.parse(
                model=GUARD_MODEL,
                max_tokens=4000,
                system=GUARD,
                messages=[{"role": "user", "content": json.dumps(view, indent=1)}],
                output_format=Fixes,
                output_config={"effort": "low"},
            )
        except anthropic.APIError as e:
            print(f"guard: API error {type(e).__name__}: {e}", flush=True)
            return
        fixes = response.parsed_output.fixes if response.parsed_output else []
        for f in fixes:
            if f.field == "summary":
                ch.summary = f.text
            elif 0 <= f.shot < len(ch.shots):
                shot = ch.shots[f.shot]
                if f.field == "line" and shot.line:
                    shot.line.text = " ".join(f.text.split()[:MAX_LINE_WORDS])
                elif f.field in ("frame", "motion", "sound"):
                    setattr(shot, f.field, f.text)
            print(f"guard: rewrote shot {f.shot} {f.field}: {f.text}", flush=True)

    def _clean(self, ch: ChapterOut, n_shots: int) -> ChapterOut | None:
        """Guardrails that need no model: shot count, known speakers and characters, line length, mood vocabulary."""
        if not ch.shots:
            return None
        ch.shots = ch.shots[:n_shots]
        speakers = self.characters | {"narrator"}
        for s in ch.shots:
            s.characters = [c for c in s.characters if c in self.characters]
            if s.line and s.line.speaker not in speakers:
                s.line = None
            if s.line:
                s.line.text = " ".join(s.line.text.split()[:MAX_LINE_WORDS])
        if ch.crowd_mood not in self.bible["moods"]:
            ch.crowd_mood = ""
        return ch
