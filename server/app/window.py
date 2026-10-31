class CommentWindow:
    def __init__(self, max_comments: int = 500):
        self.max_comments = max_comments
        self.current_id = 1
        self._comments: list[str] = []

    def add(self, text: str) -> int:
        if len(self._comments) < self.max_comments:
            self._comments.append(text)
        return self.current_id

    def cut(self) -> tuple[int, list[str]]:
        cut = (self.current_id, self._comments)
        self.current_id += 1
        self._comments = []
        return cut
