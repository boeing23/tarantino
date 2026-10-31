# Realtime movie gen

Run everything from this folder. Only Docker is required.

| Command | What it does |
|---|---|
| `make demo` | Server + story engine in Docker, playing `story/bible.json` with real timings |
| `make smoke` | Render one fal.ai clip to check the key (paid) |
| `make quick` | Same with 30s beats / 10s lock, for rehearsing |
| `make reset` | Restart the show from the opening |
| `make share` | Same as demo + a public https tunnel, so the QR works from any phone on any network |
| `make up` | Server only in Docker (connect your real engine to `/ws/engine`) |
| `make down` | Stop everything |
| `make logs` | Follow the play-by-play event log |
| `make dev` | Server locally with hot reload (needs `uv`) |
| `make engine` | Story engine locally against `make dev` |
| `make test` | Run the test suite |

Then open:

- Audience (any browser — phone or laptop): http://localhost:8000/ (others on your wifi: `http://<your-ip>:8000/`)
- Big screen: http://localhost:8000/screen — shows a QR code for the audience
- Metrics: http://localhost:8000/metrics

The QR on the screen picks the first of: `PUBLIC_URL` → the tunnel URL (`make share`) → the address the screen was opened on → your wifi IP.

If phones can't open the QR link, the venue wifi is probably blocking device-to-device traffic: use `make share`. When hosted, set `PUBLIC_URL=https://your-app.example.com`.

Timings come from the bible (`meta.beat_seconds`, `meta.lock_seconds_before_end`); override with `BEAT_SECONDS` / `LOCK_LEAD_S`. See `server/README.md` for the message contract and how to plug in the LLM generator, and `story/README.md` for the bible.

## Tunnel limits (`make share`)

Cloudflare quick tunnels are for testing: no uptime guarantee, max 200 concurrent requests (each open page holds one WebSocket), and a new random URL every time the tunnel restarts. The screen's QR refreshes itself within ~5s if the URL changes. For the real demo, deploy the Docker image to a host and set `PUBLIC_URL`; keep `make share` as the backup.
