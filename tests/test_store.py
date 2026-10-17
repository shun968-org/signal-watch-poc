from datetime import UTC, datetime

from signal_watch.config import Target
from signal_watch.store import SnapshotStore, State, TargetState
from tests.conftest import git_log

TARGET = Target(id="digital-news", name="新着", url="https://www.digital.go.jp/news")


def test_snapshot_has_attribution_header(store: SnapshotStore) -> None:
    assert store.read_lines("digital-news") is None
    path = store.write_lines(TARGET, ["a", "b"])
    assert path.read_text(encoding="utf-8").splitlines() == [
        "出典:「新着」(デジタル庁)(https://www.digital.go.jp/news)",
        "公共データ利用規約(第1.0版)に基づき、"
        "signal-watch-poc が本文のテキストを抽出・加工して作成",
        "",
        "a",
        "b",
    ]
    assert store.read_lines("digital-news") == ["a", "b"]


def test_state_round_trip(store: SnapshotStore) -> None:
    assert store.load_state() == State()
    checked = datetime(2026, 10, 17, 0, 17, tzinfo=UTC)
    state = State(
        targets={
            "digital-news": TargetState(
                last_checked_at=checked, etag='"x"', consecutive_failures=2, last_error="HTTP 500"
            )
        }
    )
    path = store.save_state(state)
    assert '"last_checked_at": "2026-10-17T00:17:00Z"' in path.read_text(encoding="utf-8")
    assert store.load_state() == state


def test_commit_returns_sha_only_when_changed(store: SnapshotStore) -> None:
    path = store.write_lines(TARGET, ["a"])
    sha = store.commit([path], "snapshot(digital-news): 初回")
    assert sha is not None and len(sha) == 40
    assert store.commit([path], "変更なし") is None
    assert git_log(store) == ["snapshot(digital-news): 初回", "init"]
