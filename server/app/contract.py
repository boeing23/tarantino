from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

VERSION = 1


class _Open(BaseModel):
  
    model_config = ConfigDict(extra="allow")


class Comment(_Open):
    text: str = Field(min_length=1, max_length=280)
    client_id: str | None = None
    mood: str | None = None

    @field_validator("text", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v


class MoodVote(_Open):
    mood: str


class Suggestion(_Open):
    text: str
    votes: int
    examples: list[str] = []


class AudienceIntent(_Open):
    window_id: int
    intent: str | None = None
    confidence: float = 0.0
    top_suggestions: list[Suggestion] = []
    mood: str | None = None
    comment_count: int = 0
    mood_votes: dict[str, int] = {}


class Line(_Open):
    speaker: str
    text: str


class Beat(_Open):
    beat_id: str
    text: str
    speaker: str
    image_url: str | None = None
    audio_url: str | None = None
    acknowledged_whispers: list[str] = []
    duration_s: float = 60.0
    is_ending: bool = False
    lines: list[Line] = []
    video_urls: list[str] = []
    mood: str | None = None
    bible_beat_id: str | None = None
    ending_id: str | None = None


class Whisper(_Open):
    window_id: int
    text: str


class WindowState(_Open):
    window_id: int
    state: str
    locks_in_s: float | None = None


class Reset(_Open):
    pass


class Ack(_Open):
    window_id: int


class Error(_Open):
    message: str


INBOUND: dict[str, type[BaseModel]] = {"comment": Comment, "mood": MoodVote, "beat": Beat}
ALL: dict[str, type[BaseModel]] = {
    **INBOUND,
    "intent": AudienceIntent,
    "whisper": Whisper,
    "window": WindowState,
    "ack": Ack,
    "reset": Reset,
    "error": Error,
}


def envelope(type_: str, model: BaseModel) -> dict:
    return {"v": VERSION, "type": type_, "data": model.model_dump()}


def parse(msg: dict) -> tuple[str, BaseModel]:
    typ = msg.get("type")
    cls = ALL.get(typ)
    if cls is None:
        raise ValueError(f"unknown message type: {typ!r}")
    return typ, cls.model_validate(msg.get("data") or {})
