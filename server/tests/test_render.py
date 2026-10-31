import asyncio
import time

import pytest

from app.bible import load_bible
from app.contract import AudienceIntent
from engine.render import FalRenderer, keyframe_prompt, shot_prompt
from engine.story import Story
from engine.video import VideoGenerator


class FakeFal:
    def __init__(self, delay=0.0, fail_on=None):
        self.calls = []
        self.delay = delay
        self.fail_on = fail_on

    async def __call__(self, endpoint, arguments, **kw):
        self.calls.append((endpoint, arguments))
        await asyncio.sleep(self.delay)
        if self.fail_on and self.fail_on in arguments.get("prompt", ""):
            raise RuntimeError("boom")
        if "image_url" in arguments:
            return {"video": {"url": f"https://fal.media/clip-{len(self.calls)}.mp4"}}
        return {"images": [{"url": f"https://fal.media/frame-{len(self.calls)}.png"}]}


@pytest.fixture
def bible():
    return load_bible()


def opening_shots(bible):
    return bible["opening"]["shots"]


def test_shot_prompt_carries_style_action_voice_and_line(bible):
    shot = opening_shots(bible)[1]
    p = shot_prompt(bible, shot)
    mara = next(c for c in bible["characters"] if c["id"] == "mara")
    for part in (bible["style"]["visual_prompt"], shot["frame"], shot["motion"], shot["line"]["text"],
                 mara["voice"]["description"].lower(), shot["sound"], bible["style"]["negative_prompt"]):
        assert part in p


def test_narrator_line_is_voiceover(bible):
    p = shot_prompt(bible, opening_shots(bible)[0])
    assert "narrator" in p.lower() and opening_shots(bible)[0]["line"]["text"] in p


def test_keyframe_prompt_describes_characters_in_frame(bible):
    p = keyframe_prompt(bible, opening_shots(bible)[1])
    for c in bible["characters"]:
        assert c["portrait_prompt"] in p


def test_render_shot_makes_keyframe_then_video(bible):
    fal = FakeFal()
    url = asyncio.run(FalRenderer(bible, subscribe=fal).render_shot(opening_shots(bible)[0]))
    (img_ep, img_args), (vid_ep, vid_args) = fal.calls
    assert "flux" in img_ep and vid_ep == FalRenderer.VIDEO_ENDPOINT
    assert vid_args["image_url"] == "https://fal.media/frame-1.png"
    assert vid_args["duration"] == bible["style"]["clip_seconds"] and vid_args["generate_audio"] is True
    assert url == "https://fal.media/clip-2.mp4"


def test_shots_render_in_parallel_and_keep_order(bible):
    fal = FakeFal(delay=0.2)
    shots = opening_shots(bible)
    t0 = time.monotonic()
    urls = asyncio.run(FalRenderer(bible, subscribe=fal).render(shots))
    assert time.monotonic() - t0 < 0.2 * 2 * len(shots)
    assert len(urls) == len(shots) and all(u.endswith(".mp4") for u in urls)


def test_failed_shot_is_dropped_but_all_failing_raises(bible):
    shots = opening_shots(bible)
    urls = asyncio.run(FalRenderer(bible, subscribe=FakeFal(fail_on=shots[0]["frame"])).render(shots))
    assert len(urls) == len(shots) - 1
    with pytest.raises(RuntimeError):
        asyncio.run(FalRenderer(bible, subscribe=FakeFal(fail_on="Cinematic")).render(shots))


def test_video_generator_attaches_clips_and_prerenders_static_beats(bible):
    fal = FakeFal()
    gen = VideoGenerator(FalRenderer(bible, subscribe=fal))
    story = Story(bible)

    async def scenario():
        await gen.prepare(story)
        await asyncio.gather(*gen.static.values())
        prerendered = len(fal.calls)
        story.advance(AudienceIntent(window_id=0, intent="start"))
        opening = await gen(story, AudienceIntent(window_id=0, intent="start"))
        assert len(fal.calls) == prerendered
        story.advance(AudienceIntent(window_id=1, intent="run"))
        beat = await gen(story, AudienceIntent(window_id=1, intent="run"))
        assert len(fal.calls) > prerendered
        return opening, beat

    opening, beat = asyncio.run(scenario())
    assert len(opening.video_urls) == len(bible["opening"]["shots"])
    assert len(beat.video_urls) == len(bible["beats"][0]["shots"])
