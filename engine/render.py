"""Turn one shot into a video clip with sound: a keyframe image, then image-to-video on fal.ai."""

import asyncio
import os
import time

import fal_client

KEYFRAME_MODEL = os.getenv("KEYFRAME_MODEL", "fal-ai/flux/schnell")

# Each preset: fal endpoint + how to ask it for `seconds` of 16:9 video with sound.
VIDEO_PRESETS = {
    # 1080p minimum, ~$0.04 per second of video
    "ltx23_fast": ("fal-ai/ltx-2.3/image-to-video/fast", lambda seconds: {
        "duration": seconds, "resolution": "1080p", "aspect_ratio": "16:9", "generate_audio": True}),
    # Any frame size; small + low quality is enough for an animated look
    "ltx2_distilled": ("fal-ai/ltx-2-19b/distilled/image-to-video", lambda seconds: {
        "video_size": {"width": 768, "height": 432}, "num_frames": seconds * 25 + 1, "fps": 25,
        "video_quality": "low", "generate_audio": True}),
}
VIDEO_PRESET = os.getenv("VIDEO_PRESET", "ltx23_fast")
VIDEO_MODEL, VIDEO_ARGS = VIDEO_PRESETS[VIDEO_PRESET]
RENDER_CONCURRENCY = int(os.getenv("RENDER_CONCURRENCY", "4"))  # clips in flight at once; the rest wait their turn
RENDER_TIMEOUT_S = float(os.getenv("RENDER_TIMEOUT_S", "180"))


class Renderer:
    def __init__(self, bible: dict, shot_seconds: int):
        self.style = bible["style"]
        self.shot_seconds = shot_seconds
        self.chars = {c["id"]: c for c in bible["characters"]}
        self.slots = asyncio.Semaphore(RENDER_CONCURRENCY)

    def _who(self, shot: dict) -> str:
        return " ".join(f"{self.chars[c]['name']}: {self.chars[c]['portrait_prompt']}." for c in shot.get("characters", []) if c in self.chars)

    def keyframe_prompt(self, shot: dict) -> str:
        return f"{self.style['visual_prompt']}. {shot['frame']}. {self._who(shot)} {self.style['lighting']}."

    def video_prompt(self, shot: dict) -> str:
        parts = [self.style["visual_prompt"], shot["frame"], shot["motion"], self.style["motion"]]
        line = shot.get("line")
        if line and line["speaker"] in self.chars:
            c = self.chars[line["speaker"]]
            parts.append(f'{c["name"]} says ({c["voice"]["description"].lower()}): "{line["text"]}"')
        elif line:
            parts.append(f'A calm narrator voice-over says: "{line["text"]}"')
        if shot.get("sound"):
            parts.append(f"Sound: {shot['sound']}. No music")
        parts.append(f"Avoid: {self.style['negative_prompt']}")
        return ". ".join(p.rstrip(".") for p in parts) + "."

    async def render(self, shot: dict) -> str:
        """Returns the clip URL. Raises on failure or after RENDER_TIMEOUT_S. At most RENDER_CONCURRENCY run at once,
        in the order they were asked for, so a chapter's first shots finish first."""
        async with self.slots:
            return await asyncio.wait_for(self._render(shot), RENDER_TIMEOUT_S)

    async def _render(self, shot: dict) -> str:
        t0 = time.monotonic()
        kf = await fal_client.subscribe_async(
            KEYFRAME_MODEL, arguments={"prompt": self.keyframe_prompt(shot), "image_size": "landscape_16_9"}
        )
        video = await fal_client.subscribe_async(
            VIDEO_MODEL,
            arguments={
                "prompt": self.video_prompt(shot),
                "image_url": kf["images"][0]["url"],
                **VIDEO_ARGS(self.shot_seconds),
            },
        )
        print(f"render: {time.monotonic() - t0:.1f}s  {shot['frame'][:60]}", flush=True)
        return video["video"]["url"]
