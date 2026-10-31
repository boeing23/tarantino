import json
import os
from functools import cache
from pathlib import Path

BIBLE_PATH = Path(os.getenv("BIBLE_PATH") or Path(__file__).resolve().parents[2] / "story" / "bible.json")


@cache
def load_bible(path: Path = BIBLE_PATH) -> dict:
    return json.loads(Path(path).read_text())


def public_info(bible: dict) -> dict:
    return {
        "title": bible["meta"]["title"],
        "logline": bible["meta"]["logline"],
        "moods": bible["moods"],
        "phone_prompt": bible["audience_hooks"]["phone_prompt"],
        "seed_suggestions": bible["audience_hooks"]["seed_suggestions"],
        "characters": {"narrator": "Narrator", **{c["id"]: c["name"] for c in bible["characters"]}},
    }
