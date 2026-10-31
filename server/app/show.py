import asyncio
import time
from collections import deque

from app.aggregate import Aggregator
from app.contract import AudienceIntent, Beat, Whisper, WindowState, envelope
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

    async def whisper(self, w: Whisper) -> None:
        self.recent.append(w)
        await self.hub.send(("screen", "audience"), envelope("whisper", w))

    def snapshot(self) -> list[dict]:
        msgs = []
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
        if self.intent_sent_at is not None:
            latency = time.monotonic() - self.intent_sent_at
            self.metrics.engine_latency_s.observe(latency)
            self.intent_sent_at = None
        await self.queue.put(beat)
        emit("beat.received", beat_id=beat.beat_id, latency_s=latency, queued=self.queue.qsize())

    async def run(self) -> None:
        while True:
            await self.play(await self.queue.get())

    async def play(self, beat: Beat) -> None:
        self.current = beat
        self.metrics.beats_total += 1
        self.metrics.current_beat_id = beat.beat_id
        await self.hub.send(("screen", "audience"), envelope("beat", beat))
        emit("beat.play", beat_id=beat.beat_id, duration_s=beat.duration_s, ending=beat.is_ending, speaker=beat.speaker)
        if beat.is_ending:
            await asyncio.sleep(beat.duration_s)
            return
        lead = min(self.lock_lead_s, beat.duration_s)
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
