"""Story state: what has happened so far, and which ending the crowd is leaning toward."""

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class StoryState:
    chapter: int = 0  # index of the next live beat in bible["beats"]
    flags: dict[str, bool] = field(default_factory=dict)
    revealed: set[str] = field(default_factory=set)
    mood: str = ""
    tally: Counter = field(default_factory=Counter)
    recap: list[str] = field(default_factory=list)

    @classmethod
    def from_bible(cls, bible: dict) -> "StoryState":
        seed = bible["state_seed"]
        return cls(
            flags=dict(seed["flags"]),
            revealed={c["id"] for c in seed["clues"] if c["revealed"]},
            mood=seed["mood"],
        )

    def apply(self, summary: str, crowd_mood: str | None, flags_set: list[str], clues_revealed: list[str]) -> None:
        self.recap.append(summary)
        if crowd_mood:
            self.mood = crowd_mood
            self.tally[crowd_mood] += 1
        for f in flags_set:
            if f in self.flags:
                self.flags[f] = True
        self.revealed.update(clues_revealed)
        self.chapter += 1

    def pick_ending(self, bible: dict) -> dict:
        """Highest mood tally among endings whose required flags are all true; bible order breaks ties."""
        reachable = [e for e in bible["endings"] if all(self.flags.get(f) for f in e["required_flags"])]
        candidates = reachable or bible["endings"]
        return max(candidates, key=lambda e: sum(self.tally[m] for m in e["trigger_moods"]))

    def summary(self) -> dict:
        return {
            "chapters_so_far": self.recap,
            "flags": self.flags,
            "clues_revealed": sorted(self.revealed),
            "crowd_mood": self.mood,
            "mood_tally": dict(self.tally),
        }
