import io
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import segno
from fastapi.testclient import TestClient

from app.config import Settings
from app.join import Tunnel
from app.main import create_app


@pytest.fixture
def fake_cloudflared():
    state = {"hostname": "abc.trycloudflare.com"}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"hostname": state["hostname"]}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state["api"] = f"http://127.0.0.1:{server.server_port}/quicktunnel"
    yield state
    server.shutdown()


def test_lookup_returns_hostname(fake_cloudflared):
    assert Tunnel(fake_cloudflared["api"]).lookup() == "abc.trycloudflare.com"


def test_empty_hostname_while_tunnel_registers(fake_cloudflared):
    fake_cloudflared["hostname"] = ""
    assert Tunnel(fake_cloudflared["api"]).lookup() is None


def test_new_url_after_tunnel_restart_is_picked_up(fake_cloudflared):
    t = Tunnel(fake_cloudflared["api"], ttl_s=0)
    assert t.lookup() == "abc.trycloudflare.com"
    fake_cloudflared["hostname"] = "xyz.trycloudflare.com"
    assert t.lookup() == "xyz.trycloudflare.com"


def test_unreachable_tunnel_returns_none():
    assert Tunnel("http://127.0.0.1:9/quicktunnel", ttl_s=0).lookup() is None


def test_qr_encodes_tunnel_url(fake_cloudflared, settings):
    settings.tunnel_api = fake_cloudflared["api"]
    with TestClient(create_app(settings)) as c:
        assert c.get("/join").json()["url"] == "https://abc.trycloudflare.com/"
        buf = io.BytesIO()
        segno.make("https://abc.trycloudflare.com/").save(buf, kind="svg", scale=8, border=2, dark="#000", light="#fff")
        assert c.get("/qr.svg").content == buf.getvalue()


def test_screen_refreshes_qr_when_url_changes(client):
    html = client.get("/screen").text
    assert "setInterval" in html and "qr.svg?u=" in html
