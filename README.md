# Realtime movie gen

Run everything from this folder. Only Docker is required.

| Command | What it does |
|---|---|
| `make demo` | Server + fake story engine in Docker — full loop, nothing else needed |
| `make up` | Server only in Docker (connect your real engine to `/ws/engine`) |
| `make down` | Stop everything |
| `make dev` | Server locally with hot reload (needs `uv`) |
| `make engine` | Fake engine locally against `make dev` |
| `make test` | Run the test suite |

Then open:

- Audience (any browser — phone or laptop): http://localhost:8000/ (others on your wifi: `http://<your-ip>:8000/`)
- Big screen: http://localhost:8000/screen
- Metrics: http://localhost:8000/metrics

Tune with env vars, e.g. `LOCK_LEAD_S=5 BEAT_DURATION_S=20 make demo`. See `server/README.md` for the message contract.
