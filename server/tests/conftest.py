import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings():
    return Settings(lock_lead_s=0.05)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def recv_until(ws, type_, limit=20):
    for _ in range(limit):
        m = ws.receive_json()
        if m["type"] == type_:
            return m
    raise AssertionError(f"no {type_!r} within {limit} messages")
