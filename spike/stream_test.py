"""Does streaming hold at full chapter size? Write one chapter, render every shot at once, check each clip beats its slot.

Usage:
  .venv/bin/python spike/stream_test.py --shots 20 --seconds 6 --yes

Shot i plays at (first clip ready) + i * seconds. A clip is late if it is ready after its slot.
Writes spike/out/stream/<timestamp>.json with per-shot timings.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from engine.render import Renderer  # noqa: E402
from engine.state import StoryState  # noqa: E402
from engine.writer import Writer  # noqa: E402

PRICE_PER_SECOND = 0.04  # LTX-2.3 Fast, 1080p


async def timed(renderer: Renderer, shot: dict, t0: float) -> tuple[float | None, str | None, str | None]:
    try:
        url = await renderer.render(shot)
        return time.monotonic() - t0, url, None
    except Exception as e:  # one failed clip must not hide the others' timings
        return None, None, f"{type(e).__name__}: {e}"[:200]


async def main(a) -> None:
    bible = json.loads((ROOT / "story" / "bible.json").read_text())
    writer, renderer = Writer(bible), Renderer(bible, a.seconds)

    t_intent = time.monotonic()
    ch = await writer.chapter(bible["beats"][0], StoryState.from_bible(bible).summary(), {"intent": None}, a.shots)
    if ch is None:
        sys.exit("writer returned no chapter")
    write_s = time.monotonic() - t_intent
    shots = [s.model_dump() for s in ch.shots]
    print(f"writer: {len(shots)} shots in {write_s:.1f}s")
    if len(shots) < a.shots:
        print(f"warning: asked for {a.shots} shots, got {len(shots)}")

    t0 = time.monotonic()
    results = await asyncio.gather(*(timed(renderer, s, t0) for s in shots))

    first = results[0][0]
    rows, late = [], 0
    for i, (ready, url, err) in enumerate(results):
        slot = None if first is None else first + i * a.seconds
        slack = None if ready is None or slot is None else slot - ready
        late += slack is not None and slack < 0
        rows.append({"shot": i, "ready_s": ready, "slot_s": slot, "slack_s": slack, "url": url, "error": err,
                     "line": (shots[i].get("line") or {}).get("text")})

    print(f"\n{'shot':>4} {'ready':>7} {'slot':>7} {'slack':>7}")
    for r in rows:
        f = lambda v: "-" if v is None else f"{v:.1f}"
        flag = " LATE" if r["slack_s"] is not None and r["slack_s"] < 0 else (" FAILED" if r["error"] else "")
        print(f"{r['shot']:>4} {f(r['ready_s']):>7} {f(r['slot_s']):>7} {f(r['slack_s']):>7}{flag}")

    ok = [r["ready_s"] for r in rows if r["ready_s"] is not None]
    failed = sum(1 for r in rows if r["error"])
    print(f"\nwriter {write_s:.1f}s | first clip {first and round(first, 1)}s | last clip {max(ok):.1f}s | "
          f"intent -> playback {write_s + (first or 0):.1f}s | late {late} | failed {failed}")
    for r in rows:
        if r["error"]:
            print(f"  shot {r['shot']}: {r['error']}")

    out = ROOT / "spike" / "out" / "stream"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{time.strftime('%Y%m%d-%H%M%S')}-{a.shots}x{a.seconds}.json"
    path.write_text(json.dumps({"shots": a.shots, "seconds": a.seconds, "write_s": write_s, "rows": rows}, indent=2))
    print(f"saved {path.relative_to(ROOT)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", type=int, default=20)
    ap.add_argument("--seconds", type=int, default=6)
    ap.add_argument("--yes", action="store_true", help="confirm the paid run")
    a = ap.parse_args()
    cost = a.shots * a.seconds * PRICE_PER_SECOND
    print(f"plan: {a.shots} clips x {a.seconds}s at once, about ${cost:.2f} of video")
    if not a.yes:
        sys.exit("paid run: re-run with --yes")
    asyncio.run(main(a))
