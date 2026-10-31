"""Live show test: phones stream comments the whole time; a screen logs beats, clips and whether each clip beat its slot.

Start the server and engine first, then:
  .venv/bin/python spike/live_test.py --url ws://127.0.0.1:8765 --phones 5 --every 4
Ends when the ending beat finishes (or after --timeout seconds).
"""

import argparse
import asyncio
import json
import random
import time

import websockets

COMMENTS = [
    # on-story ideas
    "pitch it as AI for dogs", "AI for dogs!", "make Jun the CTO", "make Jun CTO", "bribe Theo with dumplings",
    "bribe theo with dumplings", "Rory should flirt with Nadia", "Jun should hack Theo's dashboard",
    "expose Theo's bots", "go full hype", "say the word synergy", "the fern should talk",
    # things the story can't do as action (forbidden, impossible, off-world)
    "Rory should confess everything right now", "do the demo right now", "teleport the party to Mars",
    "everyone leaves the party", "summon a dragon",
    # should be stopped by the server blocklist when BLOCKLIST=badword is set
    "badword badword",
]

T0 = time.monotonic()


def t() -> str:
    return f"{time.monotonic() - T0:6.1f}s"


async def phone(url: str, every: float, stop: asyncio.Event, sent: list) -> None:
    async with websockets.connect(f"{url}/ws/audience") as ws:
        async def drain():
            async for _ in ws:  # read everything so keepalive pings get answered
                pass
        reader = asyncio.create_task(drain())
        await asyncio.sleep(random.uniform(0, every))
        while not stop.is_set():
            text = random.choice(COMMENTS)
            await ws.send(json.dumps({"type": "comment", "data": {"text": text}}))
            sent.append(text)
            await asyncio.sleep(random.uniform(every * 0.5, every * 1.5))
        reader.cancel()


async def screen(url: str, stop: asyncio.Event) -> None:
    beat_at: dict[str, float] = {}
    shot_s: dict[str, float] = {}
    late = 0
    async with websockets.connect(f"{url}/ws/screen") as ws:
        async for raw in ws:
            m = json.loads(raw)
            d = m["data"]
            now = time.monotonic()
            if m["type"] == "beat":
                kind = "BRIDGE " if d.get("is_bridge") else ("ENDING " if d.get("is_ending") else "")
                shots = d.get("shots", [])
                ready = sum(1 for s in shots if s.get("video_url"))
                beat_at[d["beat_id"]] = now
                shot_s[d["beat_id"]] = shots[0]["duration_s"] if shots else 0
                print(f"{t()} {kind}beat {d['beat_id']} {d['duration_s']:.0f}s, {ready}/{len(shots)} clips ready"
                      f" :: {d['text'][:120]}", flush=True)
                if d.get("acknowledged_whispers"):
                    print(f"         acknowledged: {d['acknowledged_whispers']}", flush=True)
                for s in shots:
                    if s.get("line") and not d.get("is_bridge"):
                        print(f"         {s['shot_id']:>3} {s['line']['speaker']}: {s['line']['text']}", flush=True)
                if d.get("is_ending"):
                    await asyncio.sleep(d["duration_s"])
                    stop.set()
                    print(f"{t()} show over; clips late for their slot: {late}", flush=True)
                    return
            elif m["type"] == "clip":
                bid, i = d["beat_id"], int(d["shot_id"][1:])
                slack = beat_at[bid] + i * shot_s[bid] - now
                late += slack < 0
                print(f"{t()} clip {bid}/{d['shot_id']} slack {slack:+.1f}s{' LATE' if slack < 0 else ''}", flush=True)
            elif m["type"] == "intent":
                print(f"{t()} intent w{d['window_id']}: {d.get('intent')!r} conf={d.get('confidence', 0):.2f} "
                      f"({d.get('comment_count')} comments)", flush=True)
            elif m["type"] == "window":
                print(f"{t()} window {d['window_id']} {d['state']}", flush=True)


async def main(a) -> None:
    stop, sent = asyncio.Event(), []
    phones = [asyncio.create_task(phone(a.url, a.every, stop, sent)) for _ in range(a.phones)]
    try:
        await asyncio.wait_for(screen(a.url, stop), a.timeout)
    except asyncio.TimeoutError:
        print(f"{t()} TIMEOUT", flush=True)
    stop.set()
    await asyncio.gather(*phones, return_exceptions=True)
    print(f"phones sent {len(sent)} comments", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://127.0.0.1:8765")
    ap.add_argument("--phones", type=int, default=5)
    ap.add_argument("--every", type=float, default=4.0, help="average seconds between one phone's comments")
    ap.add_argument("--timeout", type=float, default=900)
    asyncio.run(main(ap.parse_args()))
