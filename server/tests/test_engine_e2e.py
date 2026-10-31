import asyncio
import json
import socket
import threading
import time

import uvicorn
import websockets

from app.bible import load_bible
from app.config import Settings
from app.main import create_app
from engine.generate import scripted
from engine.runner import run
from engine.story import Story


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(settings):
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(settings), port=port, log_level="warning", ws_ping_interval=None))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.01)
    return server, port


def test_engine_drives_full_show_from_bible(settings):
    bible = load_bible()
    server, port = serve(settings)
    expected = ["opening"] + [b["id"] for b in bible["beats"]]

    async def scenario():
        engine = asyncio.create_task(run(f"ws://127.0.0.1:{port}/ws/engine", Story(bible, beat_seconds=0.3), scripted))
        seen = []
        async with websockets.connect(f"ws://127.0.0.1:{port}/ws/screen") as screen:
            while True:
                msg = json.loads(await asyncio.wait_for(screen.recv(), 5))
                if msg["type"] == "beat":
                    seen.append(msg["data"])
                    if msg["data"]["is_ending"]:
                        break
        engine.cancel()
        return seen

    try:
        beats = asyncio.run(scenario())
    finally:
        server.should_exit = True
    assert [b["bible_beat_id"] for b in beats[:-1]] == expected
    assert beats[-1]["ending_id"] in {e["id"] for e in bible["endings"]}
