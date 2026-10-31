# Tarantino server

FastAPI WebSocket hub: audience comments → windowed aggregation → intent to the story engine → beats to the screen.

See the root `README.md` to run it.

## Contract v1 (`app/contract.py`)

Every message: `{"v": 1, "type": ..., "data": {...}}`. Add fields, never rename.

| Socket | Sends | Receives |
|---|---|---|
| `/ws/audience` (any browser) | `comment {text}` | `ack`, `error`, `beat`, `window` |
| `/ws/screen` | — | `beat`, `window`, `whisper`, `intent` |
| `/ws/engine` | `beat {beat_id, text, speaker, image_url?, audio_url?, acknowledged_whispers[], duration_s, is_ending}` | `intent {window_id, intent?, confidence, top_suggestions[], mood, comment_count}`, `window` |

Engine loop: on connect you get `intent` with `window_id: 0, intent: "start"`. Reply with a `beat`. Each beat plays for `duration_s`; the window locks `LOCK_LEAD_S` before it ends and you get the next `intent` — generate and send the next beat before the current one finishes. Beats sent early are queued. If nobody commented, `intent` is `null` and `top_suggestions` is empty.
