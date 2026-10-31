import copy
from collections import Counter

from app.contract import AudienceIntent


class Story:
    def __init__(self, bible: dict, beat_seconds: float | None = None):
        self.bible = bible
        self.beat_seconds = beat_seconds or bible["meta"]["beat_seconds"]
        self.reset()

    def reset(self) -> None:
        self.state = copy.deepcopy(self.bible["state_seed"])
        self.mood_tally: Counter[str] = Counter()
        self.history: list[AudienceIntent] = []
        self.position = -1
        self.kind = ""
        self.spec: dict = {}
        self.done = False

    def advance(self, intent: AudienceIntent) -> None:
        self.history.append(intent)
        self.mood_tally.update(intent.mood_votes)
        if intent.mood:
            self.state["mood"] = intent.mood
        self.position += 1
        beats = self.bible["beats"]
        if self.position == 0:
            self.kind, self.spec = "opening", self.bible["opening"]
        elif self.position <= len(beats):
            self.kind, self.spec = "beat", beats[self.position - 1]
        else:
            self.kind, self.spec = "ending", self.choose_ending()
            self.done = True

    def choose_ending(self) -> dict:
        flags = self.state["flags"]
        eligible = [e for e in self.bible["endings"] if all(flags.get(f) for f in e["required_flags"])]
        return max(eligible or self.bible["endings"], key=lambda e: sum(self.mood_tally[m] for m in e["trigger_moods"]))
