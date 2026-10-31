import io
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import segno
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from app import events
from app.aggregate import Aggregator, naive_aggregate
from app.bible import load_bible, public_info
from app.config import Settings
from app.contract import INBOUND, Ack, Beat, Comment, Error, MoodVote, Whisper, envelope
from app.events import emit
from app.hub import ROLES, Hub
from app.join import Tunnel, resolve_join_url
from app.metrics import Metrics
from app.show import Show
from app.window import CommentWindow

STATIC = Path(__file__).parent / "static"
ALLOWED = {"audience": {"comment", "mood"}, "engine": {"beat"}, "screen": set()}


def create_app(settings: Settings | None = None, aggregate: Aggregator = naive_aggregate) -> FastAPI:
    events.setup()
    settings = settings or Settings.from_env()
    bible = load_bible()
    moods = set(bible["moods"])
    hub = Hub()
    window = CommentWindow(settings.max_comments)
    metrics = Metrics()
    show = Show(hub, window, aggregate, settings.lock_lead_s, metrics)
    tunnel = Tunnel(settings.tunnel_api)

    @asynccontextmanager
    async def lifespan(_):
        emit("server.start", lock_lead_s=settings.lock_lead_s, public_url=settings.public_url or "-")
        show.start()
        yield
        show.stop()
        emit("server.stop")

    app = FastAPI(title="tarantino", lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    def blocked(text: str) -> bool:
        low = text.lower()
        return any(w in low for w in settings.blocklist)

    def join_url(request: Request) -> str:
        return resolve_join_url(settings.public_url, tunnel.lookup(), str(request.base_url), settings.lan_url)

    async def reject(ws: WebSocket, cid: str, reason: str) -> None:
        metrics.comments_rejected += 1
        emit("comment.rejected", id=cid, reason=reason)
        await ws.send_json(envelope("error", Error(message=reason)))

    async def on_mood(ws: WebSocket, cid: str, v: MoodVote) -> None:
        if v.mood not in moods:
            return await reject(ws, cid, f"unknown mood {v.mood!r}")
        wid = window.add_mood(v.mood)
        emit("mood.vote", id=cid, window_id=wid, mood=v.mood)
        await ws.send_json(envelope("ack", Ack(window_id=wid)))

    async def on_comment(ws: WebSocket, cid: str, c: Comment) -> None:
        if c.mood and c.mood not in moods:
            return await reject(ws, cid, f"unknown mood {c.mood!r}")
        if blocked(c.text):
            return await reject(ws, cid, "comment rejected")
        wid = window.add(c.text)
        if c.mood:
            window.add_mood(c.mood)
        metrics.comments_total += 1
        emit("comment.accepted", id=cid, window_id=wid, text=c.text, mood=c.mood or "-")
        await ws.send_json(envelope("ack", Ack(window_id=wid)))
        await show.whisper(Whisper(window_id=wid, text=c.text))

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/")
    def audience():
        return FileResponse(STATIC / "audience.html")

    @app.get("/screen")
    def screen():
        return FileResponse(STATIC / "screen.html")

    @app.get("/show")
    def show_info():
        return public_info(bible)

    @app.get("/join")
    def join(request: Request):
        return {"url": join_url(request)}

    @app.get("/qr.svg")
    def qr(request: Request):
        buf = io.BytesIO()
        segno.make(join_url(request)).save(buf, kind="svg", scale=8, border=2, dark="#000", light="#fff")
        return Response(buf.getvalue(), media_type="image/svg+xml")

    @app.post("/admin/reset")
    async def reset(token: str = ""):
        if settings.admin_token and token != settings.admin_token:
            raise HTTPException(403)
        await show.reset()
        return {"ok": True}

    @app.get("/metrics")
    def get_metrics():
        return {**metrics.snapshot(), "connections": hub.counts()}

    @app.websocket("/ws/{role}")
    async def ws_endpoint(ws: WebSocket, role: str):
        peer = f"{ws.client.host}:{ws.client.port}" if ws.client else "-"
        if role not in ROLES:
            emit("ws.rejected", role=role, peer=peer)
            await ws.close(code=4404)
            return
        await ws.accept()
        cid = uuid.uuid4().hex[:6]
        hub.join(role, ws)
        emit("ws.connect", role=role, id=cid, peer=peer, **hub.counts())
        if role == "engine":
            await show.on_engine_connect(ws)
        else:
            for m in show.snapshot():
                await ws.send_json(m)
        reason = "closed"
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
                    emit("msg.invalid", role=role, id=cid, error=str(e).splitlines()[0][:120])
                    await ws.send_json(envelope("error", Error(message=str(e)[:200])))
                    continue
                if isinstance(model, Comment):
                    await on_comment(ws, cid, model)
                elif isinstance(model, MoodVote):
                    await on_mood(ws, cid, model)
                elif isinstance(model, Beat):
                    await show.enqueue(model)
        except WebSocketDisconnect as e:
            reason = f"code_{e.code}"
        except Exception as e:
            reason = type(e).__name__
            raise
        finally:
            hub.leave(role, ws)
            emit("ws.disconnect", role=role, id=cid, reason=reason, **hub.counts())

    return app


app = create_app()
