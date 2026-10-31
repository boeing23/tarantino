import asyncio
from pathlib import Path

from dotenv import load_dotenv

from app.contract import AudienceIntent, Beat
from engine.generate import scripted
from engine.render import FalRenderer
from engine.story import Story


class VideoGenerator:
    def __init__(self, renderer: FalRenderer | None = None):
        self.renderer = renderer
        self.static: dict[str, asyncio.Task] = {}

    def _renderer(self, story: Story) -> FalRenderer:
        if self.renderer is None:
            self.renderer = FalRenderer(story.bible)
        return self.renderer

    async def prepare(self, story: Story) -> None:
        r = self._renderer(story)
        self.static["opening"] = asyncio.create_task(r.render(story.bible["opening"]["shots"]))
        for e in story.bible["endings"]:
            self.static[e["id"]] = asyncio.create_task(r.render(e["shots"]))

    async def __call__(self, story: Story, intent: AudienceIntent) -> Beat:
        beat = await scripted(story, intent)
        key = "opening" if story.kind == "opening" else story.spec.get("id")
        task = self.static.get(key) if story.kind != "beat" else None
        if task:
            try:
                beat.video_urls = await task
                return beat
            except Exception:
                self.static.pop(key, None)
        beat.video_urls = await self._renderer(story).render(story.spec["shots"])
        return beat


load_dotenv(Path(__file__).resolve().parents[2] / ".env")
generate = VideoGenerator()
