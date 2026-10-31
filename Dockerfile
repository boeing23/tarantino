FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /srv/server
COPY server/pyproject.toml server/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY story /srv/story
COPY server/app ./app
COPY server/engine ./engine
ENV PORT=8000 PYTHONUNBUFFERED=1
CMD uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --log-level warning --proxy-headers --forwarded-allow-ips='*'
