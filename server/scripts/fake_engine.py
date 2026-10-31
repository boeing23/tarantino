import asyncio
import json
import os

import websockets

URL = os.getenv("ENGINE_URL", "ws://localhost:8000/ws/engine")
DURATION = float(os.getenv("BEAT_DURATION_S", "20"))


async def serve(ws):
    n = 0
    async for raw in ws:
        msg = json.loads(raw)
        if msg["type"] != "intent":
            continue
        n += 1
        intent = msg["data"]["intent"]
        print(f"intent w{msg['data']['window_id']}: {intent!r} -> beat {n}", flush=True)
        text = f"Beat {n}: the audience chose to {intent}." if intent else f"Beat {n}: the story moves on."
        beat = {"beat_id": f"b{n}", "speaker": "Narrator", "duration_s": DURATION, "text": text}
        await asyncio.sleep(1)
        await ws.send(json.dumps({"type": "beat", "data": beat}))


async def main():
    while True:
        try:
            async with websockets.connect(URL) as ws:
                print(f"connected to {URL}", flush=True)
                await serve(ws)
        except (OSError, websockets.ConnectionClosed):
            await asyncio.sleep(1)


asyncio.run(main())
