import asyncio
import os
import time

import fal_client

from app.events import emit


def _characters(bible: dict) -> dict:
    return {c["id"]: c for c in bible["characters"]}


def keyframe_prompt(bible: dict, shot: dict) -> str:
    style, chars = bible["style"], _characters(bible)
    people = "; ".join(f"{chars[c]['name']}: {chars[c]['portrait_prompt']}" for c in shot.get("characters", []))
    parts = [shot["frame"], people, style["visual_prompt"], style["lighting"], style["camera"]]
    return ". ".join(p for p in parts if p) + "."


def shot_prompt(bible: dict, shot: dict) -> str:
    style, chars = bible["style"], _characters(bible)
    parts = [shot["frame"], shot["motion"], style["visual_prompt"], style["motion"]]
    line = shot.get("line")
    if line:
        speaker = chars.get(line["speaker"])
        if speaker:
            parts.append(f'{speaker["name"]} says ({speaker["voice"]["description"].lower()}): "{line["text"]}"')
        else:
            parts.append(f'A narrator\'s voice-over says: "{line["text"]}"')
    parts.append(f"Sound: {shot['sound']}" if shot.get("sound") else "No music")
    parts.append(f"Avoid: {style['negative_prompt']}")
    return ". ".join(parts) + "."


class FalRenderer:
    IMAGE_ENDPOINT = os.getenv("IMAGE_ENDPOINT", "fal-ai/flux/schnell")
    VIDEO_ENDPOINT = os.getenv("VIDEO_ENDPOINT", "fal-ai/ltx-2.3/image-to-video/fast")

    def __init__(self, bible: dict, subscribe=fal_client.subscribe_async, timeout_s: float = 180):
        self.bible = bible
        self.subscribe = subscribe
        self.timeout_s = timeout_s
        style = bible["style"]
        self.video_args = {
            "duration": style["clip_seconds"],
            "resolution": os.getenv("VIDEO_RESOLUTION", "1080p"),
            "aspect_ratio": style["aspect_ratio"],
            "generate_audio": True,
        }

    async def _call(self, endpoint: str, arguments: dict) -> dict:
        return await self.subscribe(endpoint, arguments, client_timeout=self.timeout_s)

    async def render_shot(self, shot: dict) -> str:
        t0 = time.monotonic()
        frame = await self._call(self.IMAGE_ENDPOINT, {"prompt": keyframe_prompt(self.bible, shot), "image_size": "landscape_16_9"})
        video = await self._call(self.VIDEO_ENDPOINT, {
            "prompt": shot_prompt(self.bible, shot),
            "image_url": frame["images"][0]["url"],
            **self.video_args,
        })
        emit("render.shot_done", seconds=time.monotonic() - t0, frame=shot["frame"][:60])
        return video["video"]["url"]

    async def render(self, shots: list[dict]) -> list[str]:
        results = await asyncio.gather(*(self.render_shot(s) for s in shots), return_exceptions=True)
        urls = []
        for shot, r in zip(shots, results):
            if isinstance(r, BaseException):
                emit("render.shot_failed", frame=shot["frame"][:60], error=repr(r)[:200])
            else:
                urls.append(r)
        if shots and not urls:
            raise RuntimeError(f"all {len(shots)} shots failed to render")
        return urls
