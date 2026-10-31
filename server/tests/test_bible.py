import subprocess
import sys

from fastapi.testclient import TestClient

from app.bible import BIBLE_PATH, load_bible
from app.config import Settings
from app.main import create_app


def test_bible_passes_story_validator():
    validator = BIBLE_PATH.parent / "validate.py"
    r = subprocess.run([sys.executable, str(validator), str(BIBLE_PATH)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_show_endpoint_exposes_audience_facing_bible_fields(client):
    bible = load_bible()
    show = client.get("/show").json()
    assert show["title"] == bible["meta"]["title"]
    assert show["moods"] == bible["moods"]
    assert show["phone_prompt"] == bible["audience_hooks"]["phone_prompt"]
    assert show["seed_suggestions"] == bible["audience_hooks"]["seed_suggestions"]
    assert show["characters"] == {"narrator": "Narrator", **{c["id"]: c["name"] for c in bible["characters"]}}


def test_lock_lead_defaults_to_bible(monkeypatch):
    monkeypatch.delenv("LOCK_LEAD_S", raising=False)
    assert Settings.from_env().lock_lead_s == load_bible()["meta"]["lock_seconds_before_end"]


def test_lock_lead_env_override(monkeypatch):
    monkeypatch.setenv("LOCK_LEAD_S", "3")
    assert Settings.from_env().lock_lead_s == 3
