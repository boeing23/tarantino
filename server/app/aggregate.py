import re
from collections import defaultdict
from typing import Awaitable, Callable

from app.contract import AudienceIntent, Suggestion

STOPWORDS = {"a", "an", "the", "to", "and", "of", "please", "should", "let", "lets"}

Aggregator = Callable[[int, list[str]], Awaitable[AudienceIntent]]


def _key(text: str) -> tuple[str, ...]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return tuple(w for w in words if w not in STOPWORDS) or tuple(words)


async def naive_aggregate(window_id: int, comments: list[str]) -> AudienceIntent:
    if not comments:
        return AudienceIntent(window_id=window_id)
    groups: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for c in comments:
        groups[_key(c)].append(c)
    ranked = sorted(groups.values(), key=len, reverse=True)[:3]
    top = [Suggestion(text=g[0], votes=len(g), examples=g[:3]) for g in ranked]
    return AudienceIntent(
        window_id=window_id,
        intent=top[0].text,
        confidence=top[0].votes / len(comments),
        top_suggestions=top,
        comment_count=len(comments),
    )
