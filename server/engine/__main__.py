import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from app import events
from app.bible import load_bible
from engine.generate import choose_generator, load_generator
from engine.runner import run
from engine.story import Story

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
events.setup()
beat_seconds = os.getenv("BEAT_SECONDS")
story = Story(load_bible(), beat_seconds=float(beat_seconds) if beat_seconds else None)
generator = choose_generator(os.environ)
events.emit("engine.start", generator=generator)
generate = load_generator(generator)
asyncio.run(run(os.getenv("ENGINE_URL", "ws://localhost:8000/ws/engine"), story, generate))
