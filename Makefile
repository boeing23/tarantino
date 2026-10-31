.PHONY: up demo down dev engine test logs

up:
	docker compose up --build

demo:
	docker compose --profile demo up --build

down:
	docker compose --profile demo down

dev:
	cd server && LOCK_LEAD_S=$${LOCK_LEAD_S:-5} uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

engine:
	cd server && uv run python scripts/fake_engine.py

test:
	cd server && uv run pytest -q

logs:
	docker compose logs -f
