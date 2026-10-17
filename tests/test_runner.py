from datetime import UTC, datetime, timedelta

from signal_watch.config import Target
from signal_watch.fetcher import Crawler
from signal_watch.politeness import HostThrottle
from signal_watch.runner import Outcome, TargetResult, run
from signal_watch.store import SnapshotStore
from tests.conftest import git_log
from tests.fake_http import FakeAdapter, FakeClock, Reply, session_with

ROBOTS = "https://www.digital.go.jp/robots.txt"
URL = "https://www.digital.go.jp/policies/example"
TARGET = Target(id="example", name="例", url=URL, interval_hours=6)
T0 = datetime(2026, 10, 17, 0, 0, tzinfo=UTC)


def _page(*items: str, etag: str = '"1"') -> Reply:
    lis = "".join(f"<li>{item}</li>" for item in items)
    body = f"<html><body><main><h1>題</h1><ul>{lis}</ul></main></body></html>"
    return Reply(body=body.encode(), headers={"Content-Type": "text/html", "ETag": etag})


class Site:
    """対象ページの応答を差し替えられる偽のサイト。"""

    def __init__(self, reply: Reply | Exception) -> None:
        self.reply = reply
        self.adapter = FakeAdapter({ROBOTS: Reply(status=404), URL: lambda _: self._reply()})

    def _reply(self) -> Reply:
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply

    def crawler(self) -> Crawler:
        clock = FakeClock()
        throttle = HostThrottle(clock=clock.clock, sleep=clock.sleep)
        return Crawler(session_with(self.adapter), throttle=throttle)


def _results(
    store: SnapshotStore, site: Site, at: datetime, forced_ids: set[str] | None = None
) -> list[TargetResult]:
    return run([TARGET], store, site.crawler(), now=lambda: at, forced_ids=forced_ids)


def _run(
    store: SnapshotStore, site: Site, at: datetime, forced_ids: set[str] | None = None
) -> list[Outcome]:
    return [r.outcome for r in _results(store, site, at, forced_ids)]


def test_first_run_saves_without_notifying(store: SnapshotStore) -> None:
    site = Site(_page("A"))
    [result] = run([TARGET], store, site.crawler(), now=lambda: T0)
    assert result.outcome is Outcome.FIRST
    assert result.commit is not None
    assert store.read_lines("example") == ["題", "- A"]
    assert git_log(store)[:2] == [
        "state: 巡回 2026-10-17 00:00 UTC",
        "snapshot(example): 初回取得 2 行",
    ]


def test_skips_until_interval_has_passed(store: SnapshotStore) -> None:
    site = Site(_page("A"))
    _run(store, site, T0)
    assert _run(store, site, T0 + timedelta(hours=5)) == [Outcome.SKIPPED]
    assert _run(store, site, T0 + timedelta(hours=6)) == [Outcome.UNCHANGED]


def test_forced_run_respects_minimum_interval(store: SnapshotStore) -> None:
    site = Site(_page("A"))
    _run(store, site, T0)
    forced = {"example"}
    assert _run(store, site, T0 + timedelta(minutes=30), forced) == [Outcome.SKIPPED]
    assert _run(store, site, T0 + timedelta(hours=1), forced) == [Outcome.UNCHANGED]


def test_change_is_committed_with_diff(store: SnapshotStore) -> None:
    site = Site(_page("A"))
    _run(store, site, T0)
    site.reply = _page("A", "B", etag='"2"')
    [result] = run([TARGET], store, site.crawler(), now=lambda: T0 + timedelta(hours=6))
    assert result.outcome is Outcome.CHANGED
    assert result.diff is not None and result.diff.excerpt == ("  - A", "+ - B")
    assert "snapshot(example): +1 -0" in git_log(store)
    assert store.load_state().of("example").last_changed_at == T0 + timedelta(hours=6)


def test_conditional_request_uses_saved_etag(store: SnapshotStore) -> None:
    site = Site(_page("A", etag='"abc"'))
    _run(store, site, T0)
    site.reply = Reply(status=304)
    assert _run(store, site, T0 + timedelta(hours=6)) == [Outcome.UNCHANGED]
    assert site.adapter.requests[-1].headers["If-None-Match"] == '"abc"'


def test_failures_back_off_and_notify_once_then_recover(store: SnapshotStore) -> None:
    site = Site(_page("A"))
    _run(store, site, T0)
    site.reply = Reply(status=500)

    at = T0
    notified = []
    for hours in (6, 12, 24, 24):  # 失敗のたびに間隔が倍(上限 24 時間)
        assert _run(store, site, at + timedelta(hours=hours) - timedelta(minutes=1)) == [
            Outcome.SKIPPED
        ]
        at += timedelta(hours=hours)
        [result] = _results(store, site, at)
        assert result.outcome is Outcome.FAILED
        notified.append(result.notify_failure)
    assert notified == [False, False, True, False]
    assert store.load_state().of("example").last_error == "HTTP 500"

    site.reply = _page("A")
    at += timedelta(hours=24)
    [result] = run([TARGET], store, site.crawler(), now=lambda: at)
    assert result.outcome is Outcome.UNCHANGED
    assert result.recovered
    assert store.load_state().of("example").consecutive_failures == 0


def test_sudden_shrink_is_a_failure_not_a_change(store: SnapshotStore) -> None:
    site = Site(_page(*[str(i) for i in range(10)]))
    _run(store, site, T0)
    site.reply = _page("0")
    assert _run(store, site, T0 + timedelta(hours=6)) == [Outcome.FAILED]
    assert store.read_lines("example") is not None
    assert len(store.read_lines("example") or []) == 11


def test_added_only_saves_pushed_out_lines_without_notifying(store: SnapshotStore) -> None:
    target = Target(id="example", name="例", url=URL, diff_mode="added_only")
    site = Site(_page("3", "2", "1"))
    run([target], store, site.crawler(), now=lambda: T0)
    site.reply = _page("3", "2", etag='"2"')
    [result] = run([target], store, site.crawler(), now=lambda: T0 + timedelta(hours=6))
    assert result.outcome is Outcome.UPDATED
    assert store.read_lines("example") == ["題", "- 3", "- 2"]


def test_disabled_targets_are_skipped_unless_forced(store: SnapshotStore) -> None:
    disabled = Target(id="example", name="例", url=URL, enabled=False)
    site = Site(_page("A"))
    assert run([disabled], store, site.crawler(), now=lambda: T0) == []
    [result] = run([disabled], store, site.crawler(), now=lambda: T0, forced_ids={"example"})
    assert result.outcome is Outcome.FIRST
