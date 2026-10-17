import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from signal_watch.pruner import prune
from signal_watch.store import SnapshotStore

NOW = datetime(2026, 11, 1, 17, 47, tzinfo=UTC)


def _git(root: Path, *args: str, env: dict[str, str] | None = None) -> str:
    import os

    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    ).stdout


def _commit(store: SnapshotStore, name: str, content: str, days_ago: int) -> None:
    (store.root / name).write_text(content, encoding="utf-8")
    date = (NOW - timedelta(days=days_ago)).isoformat()
    _git(store.root, "add", name)
    _git(
        store.root,
        "commit",
        "--quiet",
        "-m",
        f"{name} {days_ago}d",
        env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
    )


def _log(store: SnapshotStore) -> list[str]:
    return _git(store.root, "log", "--format=%s").splitlines()


def _setup(store: SnapshotStore) -> None:
    # conftest の store は "init" コミットを今の日時で作るので、古い日時のリポジトリを作り直す
    _git(store.root, "update-ref", "-d", "HEAD")
    _commit(store, "README.md", "readme", 60)
    _commit(store, "state.json", "{1}", 45)
    _commit(store, "news.txt", "a", 40)
    _commit(store, "news.txt", "a\nb", 10)
    _commit(store, "state.json", "{2}", 1)


def test_old_history_is_squashed_and_content_is_kept(store: SnapshotStore) -> None:
    _setup(store)
    before = _git(store.root, "rev-parse", "HEAD^{tree}")

    result = prune(store.root, now=NOW)

    assert (result.squashed, result.kept) == (3, 2)
    assert _git(store.root, "rev-parse", "HEAD^{tree}") == before  # 最新の内容は同じ
    log = _log(store)
    assert log[:2] == ["state.json 1d", "news.txt 10d"]
    assert log[2].startswith("snapshots: 2026-10-02 より前の履歴 3 件をまとめた")
    assert len(log) == 3
    # 積み直したコミットの作成日時は保たれ、来月も正しく判定できる
    dates = _git(store.root, "log", "--format=%at").split()
    assert int(dates[0]) == int((NOW - timedelta(days=1)).timestamp())
    # もう一度実行しても、まとめるものは無い
    assert prune(store.root, now=NOW).squashed == 0


def test_dry_run_does_not_change_history(store: SnapshotStore) -> None:
    _setup(store)
    head = _git(store.root, "rev-parse", "HEAD")
    result = prune(store.root, now=NOW, dry_run=True)
    assert (result.squashed, result.kept) == (3, 2)
    assert _git(store.root, "rev-parse", "HEAD") == head


def test_all_history_old(store: SnapshotStore) -> None:
    _setup(store)
    tree = _git(store.root, "rev-parse", "HEAD^{tree}")
    result = prune(store.root, now=NOW + timedelta(days=100))
    assert (result.squashed, result.kept) == (5, 0)
    assert len(_log(store)) == 1
    assert _git(store.root, "rev-parse", "HEAD^{tree}") == tree


def test_nothing_old(store: SnapshotStore) -> None:
    _setup(store)
    head = _git(store.root, "rev-parse", "HEAD")
    assert prune(store.root, now=NOW - timedelta(days=50)).squashed == 0
    assert _git(store.root, "rev-parse", "HEAD") == head
