import asyncio
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from app import events
from app.bible import load_bible
from engine.render import FalRenderer

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
events.setup()
if not os.getenv("FAL_KEY"):
    sys.exit("FAL_KEY missing: add it to .env in the repo root")

bible = load_bible()
shot = bible["opening"]["shots"][0]
t0 = time.monotonic()
url = asyncio.run(FalRenderer(bible).render_shot(shot))
print(f"OK {time.monotonic() - t0:.1f}s {url}")
