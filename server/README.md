# Tarantino server

FastAPI WebSocket hub: audience comments → windowed aggregation → intent to the story engine → beats to the screen.

See the root `README.md` to run it.

## Contract v1 (`app/contract.py`)

Every message: `{"v": 1, "type": ..., "data": {...}}`. Add fields, never rename.

| Socket | Sends | Receives |
|---|---|---|
| `/ws/audience` (any browser) | `comment {text}` | `ack`, `error`, `beat`, `window` |
| `/ws/screen` | — | `beat`, `window`, `whisper`, `intent` |
| `/ws/engine` | `hello`, `beat {beat_id, text, speaker, image_url?, audio_url?, acknowledged_whispers[], duration_s, is_ending, shots[], lock_lead_s?, ending_id?}`, `clip` | `intent {window_id, intent?, confidence, top_suggestions[], mood, comment_count}`, `window` |

### Video additions (v1, add-only)

| Message | Fields | Meaning |
|---|---|---|
| `hello` (engine → all) | `moods[], lock_lead_s?, phone_prompt?, seed_suggestions[]` | Sent by the engine on connect, from the story bible. `lock_lead_s` replaces `LOCK_LEAD_S` as the default; phones show `phone_prompt`. |
| `beat.shots[]` | `{shot_id, index, duration_s, line?: {speaker, text}, video_url?}` | A chapter is an ordered list of video clips with sound. The engine sends the beat once shot 0 has a `video_url`. |
| `beat.lock_lead_s` | seconds | Per-beat override of when the comment window locks. |
| `clip` (engine → screen) | `{beat_id, shot_id, video_url}` | A later shot finished rendering. Clips for a beat that has not started yet are held and merged in when it plays; late-joining screens get them in the snapshot. |

| `beat.is_bridge` | bool | Plays without opening a comment window or asking for a new chapter. Used for filler clips while the next chapter renders, and for the opening (chapter 1 is made ahead and follows it). |

The screen's player (`static/player.js`) plays shots gaplessly: two stacked `<video>` elements, one playing while the other preloads the next clip. A shot whose clip has not arrived holds the last frame and shows its line as a subtitle for `duration_s` (or until the clip lands), then moves on. The screen has fullscreen, a sound toggle (browsers block autoplay with sound) and a chapter progress bar.

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
