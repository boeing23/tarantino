import asyncio
import time
from collections import deque

from app.aggregate import Aggregator
from app.contract import AudienceIntent, Beat, Clip, Hello, Whisper, WindowState, envelope
from app.events import emit
from app.hub import ROLES, Hub
from app.metrics import Metrics
from app.window import CommentWindow

START = AudienceIntent(window_id=0, intent="start")


class Show:
    def __init__(self, hub: Hub, window: CommentWindow, aggregate: Aggregator, lock_lead_s: float, metrics: Metrics):
        self.hub = hub
        self.window = window
        self.aggregate = aggregate
        self.lock_lead_s = lock_lead_s
        self.metrics = metrics
        self.intent_sent_at: float | None = None
        self.queue: asyncio.Queue[Beat] = asyncio.Queue()
        self.current: Beat | None = None
        self.last_intent: AudienceIntent | None = None
        self.window_state: WindowState | None = None
        self.lock_at = 0.0
        self.recent: deque[Whisper] = deque(maxlen=30)
        self.started = False
        self.greeting: Hello | None = None
        # clips that arrive before their beat plays, keyed beat_id -> shot_id -> url
        self.clips: dict[str, dict[str, str]] = {}

    async def hello(self, h: Hello) -> None:
        self.greeting = h
        if h.lock_lead_s is not None:
            self.lock_lead_s = h.lock_lead_s
        await self.hub.send(("screen", "audience"), envelope("hello", h))
        emit("engine.hello", moods=",".join(h.moods) or "-", lock_lead_s=self.lock_lead_s)

    async def clip(self, c: Clip) -> None:
        self.clips.setdefault(c.beat_id, {})[c.shot_id] = c.video_url
        playing = self.current is not None and self.current.beat_id == c.beat_id
        if playing:
            self.current = self._with_clips(self.current)
            await self.hub.send(("screen",), envelope("clip", c))
        emit("clip.received", beat_id=c.beat_id, shot_id=c.shot_id, playing=playing)

    def _with_clips(self, beat: Beat) -> Beat:
        known = self.clips.get(beat.beat_id)
        if not known:
            return beat
        shots = [s.model_copy(update={"video_url": known.get(s.shot_id, s.video_url)}) for s in beat.shots]
        return beat.model_copy(update={"shots": shots})

    async def whisper(self, w: Whisper) -> None:
        self.recent.append(w)
        await self.hub.send(("screen", "audience"), envelope("whisper", w))

    def snapshot(self) -> list[dict]:
        msgs = []
        if self.greeting:
            msgs.append(envelope("hello", self.greeting))
        if self.current:
            msgs.append(envelope("beat", self.current))
        if self.window_state:
            w = self.window_state
            if w.state == "open":
                w = w.model_copy(update={"locks_in_s": max(0.0, self.lock_at - time.monotonic())})
            msgs.append(envelope("window", w))
        if self.last_intent:
            msgs.append(envelope("intent", self.last_intent))
        msgs.extend(envelope("whisper", w) for w in self.recent)
        return msgs

    async def on_engine_connect(self, ws) -> None:
        if not self.started:
            await ws.send_json(envelope("intent", START))
            self.intent_sent_at = time.monotonic()
            emit("intent.sent", window_id=0, intent="start")

    async def enqueue(self, beat: Beat) -> None:
        self.started = True
        latency = None
        if self.intent_sent_at is not None and not beat.is_bridge:
            latency = time.monotonic() - self.intent_sent_at
            self.metrics.engine_latency_s.observe(latency)
            self.intent_sent_at = None
        await self.queue.put(beat)
        emit("beat.received", beat_id=beat.beat_id, latency_s=latency, queued=self.queue.qsize())

    async def run(self) -> None:
        while True:
            await self.play(await self.queue.get())

    async def play(self, beat: Beat) -> None:
        beat = self._with_clips(beat)
        if self.current:
            self.clips.pop(self.current.beat_id, None)
        self.current = beat
        self.metrics.beats_total += 1
        self.metrics.current_beat_id = beat.beat_id
        await self.hub.send(("screen", "audience"), envelope("beat", beat))
        emit("beat.play", beat_id=beat.beat_id, duration_s=beat.duration_s, ending=beat.is_ending,
             bridge=beat.is_bridge, speaker=beat.speaker)
        # Endings and bridges (filler while the next chapter renders) open no window and ask for no new chapter.
        if beat.is_ending or beat.is_bridge:
            await asyncio.sleep(beat.duration_s)
            return
        lead = min(beat.lock_lead_s if beat.lock_lead_s is not None else self.lock_lead_s, beat.duration_s)
        open_for = beat.duration_s - lead
        wid = self.window.current_id
        self.window_state = WindowState(window_id=wid, state="open", locks_in_s=open_for)
        self.lock_at = time.monotonic() + open_for
        await self.hub.send(ROLES, envelope("window", self.window_state))
        emit("window.open", window_id=wid, locks_in_s=open_for)
        await asyncio.sleep(open_for)
        wid, comments = self.window.cut()
        self.metrics.windows_total += 1
        self.window_state = WindowState(window_id=wid, state="locked")
        await self.hub.send(ROLES, envelope("window", self.window_state))
        emit("window.lock", window_id=wid, comments=len(comments))
        intent = await self.aggregate(wid, comments)
        self.last_intent = intent
        await self.hub.send(ROLES, envelope("intent", intent))
        self.intent_sent_at = time.monotonic()
        emit("intent.sent", window_id=wid, intent=intent.intent, confidence=intent.confidence,
             comments=intent.comment_count, engines=self.hub.counts()["engine"])
        await asyncio.sleep(lead)
