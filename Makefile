.PHONY: help up demo share quick down dev engine reset smoke test logs

LAN_IP := $(shell ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | cut -d' ' -f1)
export LAN_URL ?= http://$(LAN_IP):8000

help:
	@echo "make demo   server + story engine in Docker (same-wifi QR)"
	@echo "make share  demo + public https tunnel (QR works from any phone)"
	@echo "make smoke  render one fal.ai clip to check the key and models (paid)"
	@echo "make quick  demo with 30s beats / 10s lock for rehearsing"
	@echo "make reset  restart the show from the opening"
	@echo "make up     server only in Docker"
	@echo "make down   stop Docker"
	@echo "make logs   follow play-by-play logs"
	@echo "make dev    server locally with reload"
	@echo "make engine story engine locally"
	@echo "make test   run tests"
	@echo "wifi URL: $(LAN_URL)"

up:
	docker compose build && docker compose up

demo:
	docker compose --profile demo build && docker compose --profile demo up

share:
	docker compose --profile demo --profile share build && docker compose --profile demo --profile share up

smoke:
	cd server && uv run python -m engine.smoke

quick: export BEAT_SECONDS=30
quick: export LOCK_LEAD_S=10
quick:
	docker compose --profile demo build && docker compose --profile demo up

reset:
	curl -s -X POST "localhost:8000/admin/reset?token=$${ADMIN_TOKEN}"; echo

down:
	docker compose --profile demo --profile share down

dev:
	cd server && uv run uvicorn app.main:app --reload --log-level warning --host 0.0.0.0 --port 8000

engine:
	cd server && uv run python -m engine

test:
	cd server && uv run pytest -q

logs:
	docker compose logs -f --no-log-prefix server
