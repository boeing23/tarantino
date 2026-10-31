import asyncio
import json
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app.aggregate import Aggregator, naive_aggregate
from app.config import Settings
from app.contract import INBOUND, Ack, Beat, Comment, Error, Whisper, envelope
from app.hub import ROLES, Hub
from app.metrics import Metrics
from app.show import Show
from app.window import CommentWindow

STATIC = Path(__file__).parent / "static"
ALLOWED = {"audience": {"comment"}, "engine": {"beat"}, "screen": set()}


def create_app(settings: Settings | None = None, aggregate: Aggregator = naive_aggregate) -> FastAPI:
    settings = settings or Settings()
    hub = Hub()
    window = CommentWindow(settings.max_comments)
    metrics = Metrics()
    show = Show(hub, window, aggregate, settings.lock_lead_s, metrics)

    @asynccontextmanager
    async def lifespan(_):
        task = asyncio.create_task(show.run())
        yield
        task.cancel()

    app = FastAPI(title="tarantino", lifespan=lifespan)

    def blocked(text: str) -> bool:
        low = text.lower()
        return any(w in low for w in settings.blocklist)

    async def on_comment(ws: WebSocket, c: Comment) -> None:
        if blocked(c.text):
            metrics.comments_rejected += 1
            await ws.send_json(envelope("error", Error(message="comment rejected")))
            return
        wid = window.add(c.text)
        metrics.comments_total += 1
        await ws.send_json(envelope("ack", Ack(window_id=wid)))
        await hub.send(("screen",), envelope("whisper", Whisper(window_id=wid, text=c.text)))

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/")
    def audience():
        return FileResponse(STATIC / "audience.html")

    @app.get("/screen")
    def screen():
        return FileResponse(STATIC / "screen.html")

    @app.get("/metrics")
    def get_metrics():
        return {**metrics.snapshot(), "connections": hub.counts()}

    @app.websocket("/ws/{role}")
    async def ws_endpoint(ws: WebSocket, role: str):
        if role not in ROLES:
            await ws.close(code=4404)
            return
        await ws.accept()
        hub.join(role, ws)
        if role == "engine":
            await show.on_engine_connect(ws)
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                    typ = msg.get("type")
                    if typ not in ALLOWED[role]:
                        raise ValueError(f"{role} cannot send {typ!r}")
                    model = INBOUND[typ].model_validate(msg.get("data") or {})
                except (ValueError, ValidationError, AttributeError) as e:
                    await ws.send_json(envelope("error", Error(message=str(e)[:200])))
                    continue
                if isinstance(model, Comment):
                    await on_comment(ws, model)
                elif isinstance(model, Beat):
                    await show.enqueue(model)
        except WebSocketDisconnect:
            pass
        finally:
            hub.leave(role, ws)

    return app


app = create_app()
