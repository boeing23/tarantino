import asyncio
import time

from app.aggregate import Aggregator
from app.contract import AudienceIntent, Beat, WindowState, envelope
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
        self.started = False

    async def on_engine_connect(self, ws) -> None:
        if not self.started:
            await ws.send_json(envelope("intent", START))
            self.intent_sent_at = time.monotonic()

    async def enqueue(self, beat: Beat) -> None:
        self.started = True
        if self.intent_sent_at is not None:
            self.metrics.engine_latency_s.observe(time.monotonic() - self.intent_sent_at)
            self.intent_sent_at = None
        await self.queue.put(beat)

    async def run(self) -> None:
        while True:
            await self.play(await self.queue.get())

    async def play(self, beat: Beat) -> None:
        self.current = beat
        self.metrics.beats_total += 1
        self.metrics.current_beat_id = beat.beat_id
        await self.hub.send(("screen", "audience"), envelope("beat", beat))
        if beat.is_ending:
            await asyncio.sleep(beat.duration_s)
            return
        lead = min(self.lock_lead_s, beat.duration_s)
        open_for = beat.duration_s - lead
        wid = self.window.current_id
        await self.hub.send(ROLES, envelope("window", WindowState(window_id=wid, state="open", locks_in_s=open_for)))
        await asyncio.sleep(open_for)
        wid, comments = self.window.cut()
        self.metrics.windows_total += 1
        await self.hub.send(ROLES, envelope("window", WindowState(window_id=wid, state="locked")))
        intent = await self.aggregate(wid, comments)
        await self.hub.send(("engine", "screen"), envelope("intent", intent))
        self.intent_sent_at = time.monotonic()
        await asyncio.sleep(lead)

