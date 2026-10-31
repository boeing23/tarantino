import json
import time
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
    def __init__(self, api: str, ttl_s: float = 5):
        self.api = api
        self.ttl_s = ttl_s
        self.host: str | None = None
        self.checked_at = float("-inf")

    def lookup(self) -> str | None:
        if not self.api or time.monotonic() - self.checked_at < self.ttl_s:
            return self.host
        self.checked_at = time.monotonic()
        try:
            with urllib.request.urlopen(self.api, timeout=1) as r:
                self.host = json.load(r).get("hostname") or None
        except (OSError, ValueError):
            self.host = None
        return self.host
