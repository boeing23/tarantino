import asyncio
import json

import websockets

from app.contract import AudienceIntent, envelope
from app.events import emit
from engine.generate import Generator
from engine.story import Story


async def serve(ws, story: Story, generate: Generator) -> None:
    async for raw in ws:
        msg = json.loads(raw)
        if msg.get("type") != "intent":
            continue
        intent = AudienceIntent.model_validate(msg["data"])
        if intent.window_id == 0:
            story.reset()
        if story.done:
            continue
        story.advance(intent)
        try:
            beat = await generate(story, intent)
        except Exception as e:
            emit("engine.generate_failed", kind=story.kind, position=story.position, error=repr(e)[:200])
            continue
        await ws.send(json.dumps(envelope("beat", beat)))
        emit("engine.beat_sent", beat_id=beat.beat_id, kind=story.kind, bible_id=story.spec.get("id", "opening"))


async def run(url: str, story: Story, generate: Generator) -> None:
    if hasattr(generate, "prepare"):
        await generate.prepare(story)
    while True:
        try:
            async with websockets.connect(url) as ws:
                emit("engine.connected", url=url)
                await serve(ws, story, generate)
        except (OSError, websockets.ConnectionClosed) as e:
            emit("engine.disconnected", error=type(e).__name__)
        await asyncio.sleep(1)
