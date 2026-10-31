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
