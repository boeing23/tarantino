import os
from dataclasses import dataclass, field

from app.bible import load_bible


def _set(name: str) -> set[str]:
    return {w.strip().lower() for w in os.getenv(name, "").split(",") if w.strip()}


@dataclass
class Settings:
    lock_lead_s: float = 10
    max_comments: int = 500
    blocklist: set[str] = field(default_factory=set)
    public_url: str = ""
    lan_url: str = ""
    tunnel_api: str = ""
    admin_token: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        lead = os.getenv("LOCK_LEAD_S")
        return cls(
            lock_lead_s=float(lead) if lead else load_bible()["meta"]["lock_seconds_before_end"],
            max_comments=int(os.getenv("MAX_COMMENTS", "500")),
            blocklist=_set("BLOCKLIST"),
            public_url=os.getenv("PUBLIC_URL", ""),
            lan_url=os.getenv("LAN_URL", ""),
            tunnel_api=os.getenv("TUNNEL_API", ""),
            admin_token=os.getenv("ADMIN_TOKEN", ""),
        )
