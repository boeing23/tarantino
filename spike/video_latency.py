"""Time image-to-video models (with native audio) on fal.ai, N clips at once.

Usage:
  .venv/bin/python spike/video_latency.py --smoke                 # 1 clip per model
  .venv/bin/python spike/video_latency.py --rounds 3 --parallel 4 --yes
  .venv/bin/python spike/video_latency.py --models ltx2_fast --smoke

Needs FAL_KEY in .env. Clips land in spike/out/<model>/, timings in spike/out/results.json.
"""

import argparse
import json
import os
import statistics
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import fal_client
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "spike" / "out"
KEYFRAME = ROOT / "spike" / "keyframe.png"
KEYFRAME_MODEL = "fal-ai/flux/schnell"

# Endpoint ids and argument names differ per model; fix them here if the smoke test reports errors.
MODELS = {
    "veo31_fast": {
        "endpoint": "fal-ai/veo3.1/fast/image-to-video",
        "args": {"duration": "8s", "resolution": "720p", "generate_audio": True},
    },
    "ltx23_fast": {
        "endpoint": "fal-ai/ltx-2.3/image-to-video/fast",
        "args": {"duration": 6, "resolution": "1080p", "aspect_ratio": "16:9", "generate_audio": True},
    },
    "seedance2_fast": {
        "endpoint": "bytedance/seedance-2.0/fast/image-to-video",
        "args": {"duration": "5", "resolution": "720p", "aspect_ratio": "16:9", "generate_audio": True},
    },
    # 283 s for one 5 s clip in the first smoke test: too slow for live, kept only for reference.
    "kling3_pro": {
        "endpoint": "fal-ai/kling-video/v3/pro/image-to-video",
        "args": {"duration": "5", "generate_audio": True},
        "default": False,
    },
}

# Two shots with the same speaker, so we can hear whether the voice stays consistent across clips.
SHOTS = [
    {
        "frame": "Mara standing in a narrow sleeper car corridor, snow-covered windows behind her",
        "motion": "Slow push-in as she turns to face the others",
        "speaker": "mara",
        "line": "Or perhaps one of us should start talking.",
    },
    {
        "frame": "Mara by a frosted train window, cabin light flickering",
        "motion": "She looks up sharply, camera holds on her face",
        "speaker": "mara",
        "line": "I saw who carried that case aboard.",
    },
]


def load_bible():
    return json.loads((ROOT / "story" / "bible.json").read_text())


def build_prompt(bible, shot):
    style = bible["style"]
    voice = next(c["voice"]["description"] for c in bible["characters"] if c["id"] == shot["speaker"])
    return (
        f"{style['visual_prompt']}. {shot['frame']}. {shot['motion']}. {style['motion']}. "
        f'She says ({voice.lower()}): "{shot["line"]}" '
        f"Ambient sound: train creaking, wind outside. No music. Avoid: {style['negative_prompt']}."
    )


def ensure_keyframe(bible):
    if KEYFRAME.exists():
        return
    print(f"generating keyframe with {KEYFRAME_MODEL} ...")
    prompt = f"{bible['style']['visual_prompt']}. {SHOTS[0]['frame']}. {bible['style']['lighting']}."
    result = fal_client.subscribe(KEYFRAME_MODEL, arguments={"prompt": prompt, "image_size": "landscape_16_9"})
    urllib.request.urlretrieve(result["images"][0]["url"], KEYFRAME)


def run_job(name, cfg, image_url, prompt, tag):
    t0 = time.monotonic()
    started = {}

    def on_update(update):
        if isinstance(update, fal_client.InProgress) and "t" not in started:
            started["t"] = time.monotonic()

    rec = {"model": name, "tag": tag}
    try:
        result = fal_client.subscribe(
            cfg["endpoint"],
            arguments={"prompt": prompt, "image_url": image_url, **cfg["args"]},
            with_logs=True,
            on_queue_update=on_update,
        )
        done = time.monotonic()
        url = result["video"]["url"]
        dest = OUT / name / f"{tag}.mp4"
        dest.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, dest)
        rec.update(ok=True, total_s=round(done - t0, 1), file=str(dest.relative_to(ROOT)))
    except Exception as e:  # report every failure; one bad model should not stop the run
        done = time.monotonic()
        rec.update(ok=False, total_s=round(done - t0, 1), error=f"{type(e).__name__}: {e}"[:300])
    rec["queue_s"] = round(started["t"] - t0, 1) if "t" in started else None
    return rec


def run_round(name, cfg, image_url, prompts, round_idx):
    with ThreadPoolExecutor(max_workers=len(prompts)) as pool:
        futures = [
            pool.submit(run_job, name, cfg, image_url, p, f"r{round_idx}_c{i}_shot{i % len(SHOTS)}")
            for i, p in enumerate(prompts)
        ]
        return [f.result() for f in futures]


def pct(values, q):
    if not values:
        return None
    values = sorted(values)
    return values[min(len(values) - 1, round(q * (len(values) - 1)))]


def summarize(records):
    print(f"\n{'model':<12} {'ok':>5} {'first':>7} {'p50':>7} {'p90':>7} {'max':>7} {'queue max':>10}")
    for name in dict.fromkeys(r["model"] for r in records):
        rs = [r for r in records if r["model"] == name]
        ok = [r["total_s"] for r in rs if r["ok"]]
        queue = [r["queue_s"] for r in rs if r["queue_s"] is not None]
        first = min(ok) if ok else None
        fmt = lambda v: "-" if v is None else f"{v:.1f}"
        print(
            f"{name:<12} {len(ok):>2}/{len(rs):<2} {fmt(first):>7} {fmt(statistics.median(ok) if ok else None):>7} "
            f"{fmt(pct(ok, 0.9)):>7} {fmt(max(ok) if ok else None):>7} {fmt(max(queue) if queue else None):>10}"
        )
        for r in rs:
            if not r["ok"]:
                print(f"  {r['tag']}: {r['error']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="1 clip per model, 1 round")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--models", nargs="*", default=[m for m, cfg in MODELS.items() if cfg.get("default", True)])
    ap.add_argument("--yes", action="store_true", help="confirm a full (paid) run")
    a = ap.parse_args()

    load_dotenv(ROOT / ".env")
    if not os.environ.get("FAL_KEY"):
        sys.exit("FAL_KEY missing: add it to .env")
    unknown = set(a.models) - set(MODELS)
    if unknown:
        sys.exit(f"unknown models: {sorted(unknown)}")

    rounds, parallel = (1, 1) if a.smoke else (a.rounds, a.parallel)
    jobs = rounds * parallel * len(a.models)
    print(f"plan: {len(a.models)} model(s) x {rounds} round(s) x {parallel} clip(s) = {jobs} paid clip(s)")
    if not a.smoke and not a.yes:
        sys.exit("full run costs money: re-run with --yes")

    bible = load_bible()
    OUT.mkdir(parents=True, exist_ok=True)
    ensure_keyframe(bible)
    image_url = fal_client.upload_file(KEYFRAME)
    prompts = [build_prompt(bible, SHOTS[i % len(SHOTS)]) for i in range(parallel)]

    records = []
    for name in a.models:
        for r in range(rounds):
            print(f"{name}: round {r + 1}/{rounds}, {parallel} clip(s) at once ...")
            records += run_round(name, MODELS[name], image_url, prompts, r)

    results = OUT / "results.json"
    previous = json.loads(results.read_text()) if results.exists() else []
    results.write_text(json.dumps(previous + [{"at": time.strftime("%Y-%m-%d %H:%M:%S"), "smoke": a.smoke, "records": records}], indent=2))
    summarize(records)
    print(f"\nclips in {OUT.relative_to(ROOT)}/, timings appended to {results.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
