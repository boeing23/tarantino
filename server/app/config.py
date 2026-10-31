import os
from dataclasses import dataclass, field


def _set(name: str) -> set[str]:
    return {w.strip().lower() for w in os.getenv(name, "").split(",") if w.strip()}


@dataclass
class Settings:
    lock_lead_s: float = float(os.getenv("LOCK_LEAD_S", "10"))
    max_comments: int = int(os.getenv("MAX_COMMENTS", "500"))
    blocklist: set[str] = field(default_factory=lambda: _set("BLOCKLIST"))
    public_url: str = os.getenv("PUBLIC_URL", "")
    lan_url: str = os.getenv("LAN_URL", "")
    tunnel_api: str = os.getenv("TUNNEL_API", "")
