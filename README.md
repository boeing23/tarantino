# Realtime movie gen

Run everything from this folder. Only Docker is required.

| Command | What it does |
|---|---|
| `make demo` | Server + fake story engine in Docker — full loop, nothing else needed |
| `make share` | Same as demo + a public https tunnel, so the QR works from any phone on any network |
| `make up` | Server only in Docker (connect your real engine to `/ws/engine`) |
| `make down` | Stop everything |
| `make logs` | Follow the play-by-play event log |
| `make dev` | Server locally with hot reload (needs `uv`) |
| `make engine` | Fake engine locally against `make dev` |
| `make test` | Run the test suite |

Then open:

- Audience (any browser — phone or laptop): http://localhost:8000/ (others on your wifi: `http://<your-ip>:8000/`)
- Big screen: http://localhost:8000/screen — shows a QR code for the audience
- Metrics: http://localhost:8000/metrics

The QR on the screen picks the first of: `PUBLIC_URL` → the tunnel URL (`make share`) → the address the screen was opened on → your wifi IP.

If phones can't open the QR link, the venue wifi is probably blocking device-to-device traffic: use `make share`. When hosted, set `PUBLIC_URL=https://your-app.example.com`.

Tune with env vars, e.g. `LOCK_LEAD_S=5 BEAT_DURATION_S=20 make demo`. See `server/README.md` for the message contract.
