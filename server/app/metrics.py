import time
from dataclasses import asdict, dataclass, field


@dataclass
class Timer:
    count: int = 0
    last: float | None = None
    max: float = 0.0
    total: float = 0.0

    def observe(self, seconds: float) -> None:
        self.count += 1
        self.last = seconds
        self.max = max(self.max, seconds)
        self.total += seconds


@dataclass
class Metrics:
    started_at: float = field(default_factory=time.time)
    comments_total: int = 0
    comments_rejected: int = 0
    beats_total: int = 0
    windows_total: int = 0
    current_beat_id: str | None = None
    engine_latency_s: Timer = field(default_factory=Timer)

    def snapshot(self) -> dict:
        return {**asdict(self), "uptime_s": time.time() - self.started_at}
