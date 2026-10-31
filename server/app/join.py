import json
import urllib.request
from urllib.parse import urlparse

LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "testserver"}


def resolve_join_url(public_url: str, tunnel_host: str | None, request_url: str, lan_url: str) -> str:
    if public_url:
        return public_url.rstrip("/") + "/"
    if tunnel_host:
        return f"https://{tunnel_host}/"
    if urlparse(request_url).hostname in LOCAL_HOSTS and lan_url:
        return lan_url.rstrip("/") + "/"
    return request_url


class Tunnel:
    def __init__(self, api: str):
        self.api = api
        self.host: str | None = None

    def lookup(self) -> str | None:
        if self.host or not self.api:
            return self.host
        try:
            with urllib.request.urlopen(self.api, timeout=1) as r:
                self.host = json.load(r).get("hostname") or None
        except (OSError, ValueError):
            pass
        return self.host
