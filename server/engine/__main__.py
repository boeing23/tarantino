import asyncio
import os

from app import events
from app.bible import load_bible
from engine.generate import load_generator
from engine.runner import run
from engine.story import Story

events.setup()
beat_seconds = os.getenv("BEAT_SECONDS")
story = Story(load_bible(), beat_seconds=float(beat_seconds) if beat_seconds else None)
generate = load_generator(os.getenv("ENGINE_GENERATOR", "engine.generate:scripted"))
asyncio.run(run(os.getenv("ENGINE_URL", "ws://localhost:8000/ws/engine"), story, generate))
