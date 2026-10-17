from signal_watch.differ import (
    EXCERPT_MAX_CHARS,
    EXCERPT_MAX_LINES,
    Diff,
    compare,
    shrink_error,
)


def test_no_change() -> None:
    assert compare(["a", "b"], ["a", "b"], "lines") == Diff(
        changed=False, added=0, removed=0, excerpt=()
    )


def test_lines_mode_reports_added_and_removed_with_context() -> None:
    old = ["題", "a", "b", "c", "d", "e"]
    new = ["題", "a", "B", "c", "d", "e", "f"]
    diff = compare(old, new, "lines")
    assert (diff.changed, diff.added, diff.removed) == (True, 2, 1)
    assert diff.excerpt == ("  a", "- b", "+ B", "  c", "  …", "  e", "+ f")


def test_removal_only_is_a_change_in_lines_mode() -> None:
    diff = compare(["a", "b"], ["a"], "lines")
    assert diff.changed
    assert diff.excerpt == ("  a", "- b")


def test_added_only_ignores_lines_pushed_out_of_a_list() -> None:
    old = ["新着", "- 3", "- 2", "- 1"]
    assert not compare(old, ["新着", "- 3", "- 2"], "added_only").changed

    diff = compare(old, ["新着", "- 4", "- 3", "- 2"], "added_only")
    assert (diff.changed, diff.added, diff.removed) == (True, 1, 1)
    assert diff.excerpt == ("+ - 4",)


def test_excerpt_is_truncated_by_lines() -> None:
    new = [f"行{i}" for i in range(40)]
    diff = compare([], new, "lines")
    assert len(diff.excerpt) == EXCERPT_MAX_LINES + 1
    assert diff.excerpt[-1] == f"(ほか {40 - EXCERPT_MAX_LINES} 行)"


def test_excerpt_is_truncated_by_chars() -> None:
    long_line = "あ" * (EXCERPT_MAX_CHARS * 2)
    diff = compare(["x"], ["x", long_line, "y"], "lines")
    assert diff.excerpt[0] == "  x"
    assert diff.excerpt[-1] == "(ほか 2 行)"

    only_long = compare([], [long_line], "lines")
    assert len(only_long.excerpt[0]) == EXCERPT_MAX_CHARS
    assert only_long.excerpt[0].endswith("…")


def test_shrink_error() -> None:
    old = [str(i) for i in range(10)]
    assert shrink_error(old, old[:5]) is None
    assert shrink_error(old, old[:4]) is not None
    assert shrink_error([], ["a"]) is None
