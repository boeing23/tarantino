class CommentWindow:
    def __init__(self, max_comments: int = 500):
        self.max_comments = max_comments
        self.current_id = 1
        self._comments: list[str] = []
        self._moods: list[str] = []

    def add(self, text: str) -> int:
        if len(self._comments) < self.max_comments:
            self._comments.append(text)
        return self.current_id

    def add_mood(self, mood: str) -> int:
        if len(self._moods) < self.max_comments:
            self._moods.append(mood)
        return self.current_id

    def cut(self) -> tuple[int, list[str], list[str]]:
        cut = (self.current_id, self._comments, self._moods)
        self.current_id += 1
        self._comments = []
        self._moods = []
        return cut
