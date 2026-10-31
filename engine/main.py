"""Story engine: connects to the server as /ws/engine, turns crowd intents into chapters of video shots.

Run from the repo root:
  .venv/bin/python -m engine.main --prepare   # once before the show: render + cache opening, fillers, chapter 1
  .venv/bin/python -m engine.main             # the show: starts instantly from the cache
Env: ENGINE_URL, BIBLE, SHOTS_PER_CHAPTER, SHOT_SECONDS, MAX_CHAPTERS, LOCK_LEAD_S, CLAUDE_MODEL, VIDEO_MODEL.
"""

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

import websockets
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from engine.render import VIDEO_PRESET, Renderer  # noqa: E402  (reads FAL_KEY at call time, after .env is loaded)
from engine.state import StoryState  # noqa: E402
from engine.writer import Writer  # noqa: E402

URL = os.getenv("ENGINE_URL", "ws://127.0.0.1:8000/ws/engine")
BIBLE_PATH = ROOT / os.getenv("BIBLE", "story/bible.json")
SHOTS = int(os.getenv("SHOTS_PER_CHAPTER", "3"))
SHOT_SECONDS = int(os.getenv("SHOT_SECONDS", "6"))
CACHE = ROOT / "engine" / "cache"
NO_VIDEO = os.getenv("NO_VIDEO") == "1"  # test the storyline without paying for video
WRITER_DELAY_S = float(os.getenv("WRITER_DELAY_S", "0"))  # simulate a slow chapter, to test bridges


def log(*a):
    print(*a, flush=True)


def envelope(type_: str, data: dict) -> str:
    return json.dumps({"v": 1, "type": type_, "data": data})


class Engine:
    def __init__(self, bible: dict):
        self.bible = bible
        self.state = StoryState.from_bible(bible)
        self.writer = Writer(bible)
        self.renderer = Renderer(bible, SHOT_SECONDS)
        self.max_chapters = int(os.getenv("MAX_CHAPTERS", str(len(bible["beats"]) - 1)))
        self.lock_lead = float(os.getenv("LOCK_LEAD_S", bible["meta"]["lock_seconds_before_end"]))
        self.opening: list[str | None] = []
        self.first: dict | None = None  # chapter 1, made before the show so the crowd gets a full first window
        self.bridges: list[str | None] = []
        self.ws = None
        self.lock = asyncio.Lock()  # chapters are produced strictly in order
        self.done = False
        self.n = 0
        self.n_bridges = 0
        self.playing_s = 0.0  # length of the last chapter sent; the next intent arrives lock_lead before it ends

    # ---------- opening + bridges: rendered once before the show, cached on disk ----------

    def _cache(self, name: str, *parts) -> Path:
        key = hashlib.sha256(json.dumps([*parts, self.bible["style"], SHOT_SECONDS, VIDEO_PRESET]).encode()).hexdigest()[:12]
        return CACHE / f"{name}-{key}.json"

    async def _render_all(self, name: str, shots: list[dict], have: list | None = None) -> list[str | None]:
        """Render every shot not already in `have`. A failed or timed-out clip becomes None (the screen holds a frame)."""
        have = have or [None] * len(shots)
        if NO_VIDEO:
            return have
        todo = [i for i, u in enumerate(have) if not u]
        done = len(shots) - len(todo)

        async def one(i: int) -> None:
            nonlocal done
            try:
                have[i] = await self.renderer.render(shots[i])
                done += 1
                log(f"{name}: {done}/{len(shots)} clips ready")
            except Exception as e:
                log(f"{name}: shot {i} failed ({type(e).__name__}: {str(e)[:120]})")

        await asyncio.gather(*(one(i) for i in todo))
        return have

    def _save(self, path: Path, data) -> None:
        if not NO_VIDEO:
            CACHE.mkdir(exist_ok=True)
            path.write_text(json.dumps(data))

    async def _prerender(self, name: str, shots: list[dict]) -> list[str | None]:
        path = self._cache(name, shots)
        have = json.loads(path.read_text()) if path.exists() and not NO_VIDEO else None
        if have and all(have):
            log(f"{name}: cached")
            return have
        missing = len(shots) if not have else sum(1 for u in have if not u)
        log(f"{name}: rendering {missing} of {len(shots)} shots ...")
        urls = await self._render_all(name, shots, have)
        self._save(path, urls)
        return urls

    async def _premake_first(self) -> dict:
        """Chapter 1 is written without crowd input and fully rendered before the show (cached). The crowd
        comments through the opening and chapter 1, then steers chapter 2 onward with a full window."""
        spec, _ = self._spec()
        path = self._cache("chapter1", spec, SHOTS, self.bible["characters"])
        made = json.loads(path.read_text()) if path.exists() and not NO_VIDEO else None
        if made and all(made["urls"]):
            log("chapter1: cached")
            return made
        if not made:
            made = {"chapter": await self._write(spec, {"intent": None}), "urls": None}
            self._save(path, made)  # keep the script even if rendering is interrupted
        shots = made["chapter"]["shots"]
        log(f"chapter1: rendering {sum(1 for u in (made['urls'] or [None] * len(shots)) if not u)} of {len(shots)} shots ...")
        made["urls"] = await self._render_all("chapter1", shots, made["urls"])
        self._save(path, made)
        return made

    async def prerender(self) -> None:
        self.opening, self.bridges, self.first = await asyncio.gather(
            self._prerender("opening", self.bible["opening"]["shots"]),
            self._prerender("bridges", [b["shot"] for b in self.bible["bridges"]]),
            self._premake_first(),
        )

    def bridge_beat(self) -> dict:
        """Neutral filler that plays while the next chapter is still rendering. Opens no comment window."""
        i = self.n_bridges % len(self.bible["bridges"])
        self.n_bridges += 1
        b = self.bible["bridges"][i]
        shot = self._shot(0, {"line": {"speaker": "narrator", "text": b["narration"]}}, self.bridges[i])
        return {"beat_id": f"bridge{self.n_bridges}", "text": b["narration"], "speaker": "narrator",
                "duration_s": SHOT_SECONDS, "is_bridge": True, "shots": [shot]}

    def opening_beat(self) -> dict:
        shots = self.bible["opening"]["shots"]
        return {
            "beat_id": "opening",
            "text": self.bible["opening"]["narration"],
            "speaker": "narrator",
            "duration_s": len(shots) * SHOT_SECONDS,
            "is_bridge": True,  # no comment window: chapter 1 is already made and plays right after
            "shots": [self._shot(i, s, url) for i, (s, url) in enumerate(zip(shots, self.opening))],
        }

    # ---------- live chapters ----------

    @staticmethod
    def _shot(i: int, s: dict, url: str | None = None) -> dict:
        return {"shot_id": f"s{i}", "index": i, "duration_s": SHOT_SECONDS, "line": s.get("line"), "video_url": url}

    def _spec(self) -> tuple[dict, dict | None]:
        """What the next chapter must do, and the ending if this is the last one."""
        beats = self.bible["beats"]
        if self.state.chapter >= self.max_chapters:
            ending = self.state.pick_ending(self.bible)
            final = beats[-1]
            spec = {**final, "must_hit": f"{final['must_hit']}. Land this ending: {ending['name']} - {ending['summary']}",
                    "shots": ending["shots"] + final["shots"], "is_ending": True}
            return spec, ending
        return beats[self.state.chapter], None

    def _fallback(self, spec: dict) -> dict:
        """Bible anchor shots, used when Claude is unavailable. Keeps the plot moving through must_hit."""
        anchors = spec["shots"]
        shots = [anchors[i % len(anchors)] for i in range(SHOTS)]
        return {"summary": spec["must_hit"], "shots": shots, "crowd_mood": "", "acknowledged_whispers": [],
                "flags_set": [], "clues_revealed": []}

    async def _write(self, spec: dict, intent: dict) -> dict:
        act = spec.get("act", 3)
        forbidden = next((f["actions"] for f in self.bible["forbidden"] if f["act"] == act), [])
        t0 = asyncio.get_running_loop().time()
        written = await self.writer.chapter({**spec, "forbidden": forbidden}, self.state.summary(), intent, SHOTS)
        if WRITER_DELAY_S:
            await asyncio.sleep(WRITER_DELAY_S)
        ch = written.model_dump() if written else self._fallback(spec)
        log(f"chapter {self.n + 1}: written in {asyncio.get_running_loop().time() - t0:.1f}s"
            f"{'' if written else ' (FALLBACK from bible)'}: {ch['summary']}")
        return ch

    def _beat(self, ch: dict, ending: dict | None, urls: list | None = None) -> dict:
        """Turn a written chapter into a beat and advance the story state."""
        self.n += 1
        urls = urls or [None] * len(ch["shots"])
        shots = [self._shot(i, s, u) for i, (s, u) in enumerate(zip(ch["shots"], urls))]
        self.state.apply(ch["summary"], ch["crowd_mood"], ch["flags_set"], ch["clues_revealed"])
        if ending:
            self.done = True
        return {
            "beat_id": f"c{self.n}",
            "text": ch["summary"],
            "speaker": "narrator",
            "duration_s": len(shots) * SHOT_SECONDS,
            "lock_lead_s": self.lock_lead,
            "acknowledged_whispers": ch["acknowledged_whispers"],
            "shots": shots,
            "is_ending": ending is not None,
            "ending_id": ending["id"] if ending else None,
        }

    async def next_chapter(self, intent: dict, sent: asyncio.Event) -> None:
        async with self.lock:
            if self.done:
                sent.set()
                return
            spec, ending = self._spec()
            t0 = asyncio.get_running_loop().time()
            ch = await self._write(spec, intent)
            beat = self._beat(ch, ending)
            beat_id = beat["beat_id"]

            tasks = [] if NO_VIDEO else [asyncio.create_task(self.renderer.render(s)) for s in ch["shots"]]
            # The beat goes out as soon as its first clip is ready; later clips stream in while it plays.
            if tasks:
                try:
                    beat["shots"][0]["video_url"] = await tasks[0]
                except Exception as e:
                    log(f"{beat_id}/s0: render failed: {e}")
            await self.send("beat", beat)
            sent.set()
            self.playing_s = beat["duration_s"]
            log(f"{beat_id}: sent beat ({len(beat['shots'])} shots, {beat['duration_s']}s, ending={beat['is_ending']})"
                f" {asyncio.get_running_loop().time() - t0:.1f}s after intent")
        asyncio.create_task(self._stream_clips(beat_id, tasks[1:], start=1))

    async def _stream_clips(self, beat_id: str, tasks: list, start: int) -> None:
        """Send each clip the moment it finishes, so one slow clip never holds back the ones after it."""
        async def one(i: int, task) -> None:
            try:
                url = await task
            except Exception as e:
                log(f"{beat_id}/s{i}: render failed: {e}")
                return
            await self.send("clip", {"beat_id": beat_id, "shot_id": f"s{i}", "video_url": url})
            log(f"{beat_id}/s{i}: clip sent")

        await asyncio.gather(*(one(i, t) for i, t in enumerate(tasks, start)))

    # ---------- socket ----------

    async def send(self, type_: str, data: dict) -> None:
        await self.ws.send(envelope(type_, data))

    async def on_intent(self, intent: dict) -> None:
        log(f"intent w{intent['window_id']}: {intent.get('intent')!r} conf={intent.get('confidence', 0):.2f} "
            f"comments={intent.get('comment_count', 0)}")
        if intent["window_id"] == 0 and intent.get("intent") == "start":
            await self.send("beat", self.opening_beat())
            first = self._beat(self.first["chapter"], None, self.first["urls"])
            await self.send("beat", first)
            self.playing_s = first["duration_s"]
            log("opening + chapter 1: sent")
            return
        sent = asyncio.Event()
        if not self.done:
            asyncio.create_task(self._cover_gap(sent))
        await self.next_chapter(intent, sent)

    async def _cover_gap(self, sent: asyncio.Event) -> None:
        """The playing chapter ends lock_lead after its intent. Until the next chapter is sent, fill each gap with a bridge."""
        wait = min(self.lock_lead, self.playing_s) - 2
        while True:
            try:
                await asyncio.wait_for(sent.wait(), timeout=max(wait, 0))
                return
            except asyncio.TimeoutError:
                b = self.bridge_beat()
                await self.send("beat", b)
                log(f"{b['beat_id']}: next chapter not ready, sent bridge")
                wait = SHOT_SECONDS

    async def run(self) -> None:
        await self.prerender()
        hooks = self.bible["audience_hooks"]
        while True:
            try:
                async with websockets.connect(URL) as ws:
                    self.ws = ws
                    log(f"connected to {URL}")
                    await self.send("hello", {"moods": self.bible["moods"], "lock_lead_s": self.lock_lead,
                                              "phone_prompt": hooks["phone_prompt"],
                                              "seed_suggestions": hooks["seed_suggestions"]})
                    async for raw in ws:
                        msg = json.loads(raw)
                        if msg["type"] == "intent":
                            asyncio.create_task(self.on_intent(msg["data"]))
            except (OSError, websockets.exceptions.WebSocketException) as e:  # incl. a half-started server
                log(f"disconnected ({type(e).__name__}); retrying")
                await asyncio.sleep(1)


async def prepare(engine: Engine) -> None:
    """Render and cache everything the show starts with, then exit. Re-run to retry any clip that failed."""
    await engine.prerender()
    if NO_VIDEO:
        log("ready (NO_VIDEO: nothing rendered or cached)")
        return
    missing = sum(1 for u in [*engine.opening, *engine.bridges, *engine.first["urls"]] if not u)
    log("ready: the show will start instantly" if not missing else f"{missing} clip(s) failed: run --prepare again")


if __name__ == "__main__":
    engine = Engine(json.loads(BIBLE_PATH.read_text()))
    asyncio.run(prepare(engine) if "--prepare" in sys.argv else engine.run())
