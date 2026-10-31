# Tarantino server

FastAPI WebSocket hub (`app/`) and story engine (`engine/`): audience comments → windowed aggregation → intent to the engine → beats to the screen. Both read `story/bible.json`.

See the root `README.md` to run it.

## Contract v1 (`app/contract.py`)

Every message: `{"v": 1, "type": ..., "data": {...}}`. Add fields, never rename.

| Socket | Sends | Receives |
|---|---|---|
| `/ws/audience` (any browser) | `comment {text, mood?}`, `mood {mood}` | `ack`, `error`, `beat`, `window`, `whisper`, `intent`, `reset` |
| `/ws/screen` | — | `beat`, `window`, `whisper`, `intent`, `reset` |
| `/ws/engine` | `beat {beat_id, text, speaker, lines[{speaker,text}], video_urls[], image_url?, audio_url?, acknowledged_whispers[], duration_s, mood?, bible_beat_id?, ending_id?, is_ending}` | `intent {window_id, intent?, confidence, top_suggestions[], mood?, mood_votes{}, comment_count}`, `window` |

Moods must be one of the bible's `moods`. Late joiners get the current beat, window, last intent and recent whispers on connect.

Engine loop: on connect you get `intent` with `window_id: 0, intent: "start"`. Reply with a `beat`. Each beat plays for `duration_s`; the window locks `LOCK_LEAD_S` before it ends and you get the next `intent` — generate and send the next beat before the current one finishes. Beats sent early are queued. If nobody commented, `intent` is `null` and `top_suggestions` is empty.

## Event log

One line per event, `event key=value ...` (`make logs`):

| Event | When |
|---|---|
| `server.start` / `server.stop` | Process lifecycle |
| `ws.connect` / `ws.disconnect` | Socket attach/detach, with role, id, peer, reason and live counts per role |
| `ws.rejected` | Unknown role path |
| `ws.send_failed` | Dead socket dropped during broadcast |
| `msg.invalid` | Bad JSON, wrong type for role, or failed validation |
| `comment.accepted` / `comment.rejected` | Audience comment in/out of the window |
| `intent.sent` | Intent delivered to engines (start, or after a window lock) |
| `beat.received` | Engine beat arrived, with latency since the last intent |
| `beat.play` | Beat goes on screen |
| `window.open` / `window.lock` | Comment window lifecycle |

## Story engine (`engine/`)

`python -m engine` connects to `/ws/engine`, loads the bible and drives the show:

- `Story` (`engine/story.py`) holds what comes next and the live state: opening → `beats` in order → ending. It tallies `mood_votes` across windows and picks the ending with the highest tally whose `required_flags` are true. Set flags in `story.state["flags"]` as beats land.
- A **generator** turns `(story, intent)` into a `Beat`. The default `engine.generate:scripted` builds beats straight from the bible (lines from shots, must_hit + the room's intent).
- Swap in the LLM/render pipeline without touching anything else:

```python
async def generate(story: Story, intent: AudienceIntent) -> Beat:
    story.kind        # "opening" | "beat" | "ending"
    story.spec        # the bible entry for this step
    story.state       # state_seed, mutated as the show goes
    story.history     # every AudienceIntent so far
    return Beat(beat_id=..., text=..., speaker=..., lines=[...], video_urls=[...], duration_s=story.beat_seconds)
```

```bash
ENGINE_GENERATOR=mypackage.llm:generate make demo
```

Generation starts the moment the window locks (`lock_seconds_before_end` before the beat ends), so that is the time budget for beat N+1. A generator that raises is logged as `engine.generate_failed` and the show waits for the next window.

`POST /admin/reset` (`make reset`) restarts the show from the opening; set `ADMIN_TOKEN` and pass `?token=` when hosted.
