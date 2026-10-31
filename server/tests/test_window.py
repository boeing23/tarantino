from app.window import CommentWindow


def test_comments_land_in_current_window_and_cut_rolls_over():
    w = CommentWindow()
    assert w.add("a") == 1
    assert w.add("b") == 1
    w.add_mood("tense")
    assert w.cut() == (1, ["a", "b"], ["tense"])
    assert w.add("c") == 2
    assert w.cut() == (2, ["c"], [])


def test_cut_empty_window():
    w = CommentWindow()
    assert w.cut() == (1, [], [])
    assert w.current_id == 2


def test_window_caps_size():
    w = CommentWindow(max_comments=2)
    w.add("a"); w.add("b"); w.add("c")
    assert w.cut()[1] == ["a", "b"]
