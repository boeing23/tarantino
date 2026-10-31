from fastapi import WebSocket

from app.events import emit

ROLES = ("audience", "screen", "engine")


class Hub:
    def __init__(self):
        self.clients: dict[str, set[WebSocket]] = {r: set() for r in ROLES}

    def join(self, role: str, ws: WebSocket) -> None:
        self.clients[role].add(ws)

    def leave(self, role: str, ws: WebSocket) -> None:
        self.clients[role].discard(ws)

    def counts(self) -> dict[str, int]:
        return {r: len(s) for r, s in self.clients.items()}

    async def send(self, roles: tuple[str, ...], msg: dict) -> None:
        for role in roles:
            for ws in list(self.clients[role]):
                try:
                    await ws.send_json(msg)
                except Exception as e:
                    self.leave(role, ws)
                    emit("ws.send_failed", role=role, error=type(e).__name__, **self.counts())
