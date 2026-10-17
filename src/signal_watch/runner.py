"""巡回1回分の処理(基本設計 F-02・F-06・F-08)。

取得間隔に達した対象を取得 → 抽出 → 前回と比較し、変更があればスナップショットを
対象ごとに1コミットで保存する。最後に実行状態(state.json)をコミットする。
push と通知は呼び出し側(ワークフロー)が行う。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum

from signal_watch.config import MIN_INTERVAL_HOURS, Target
from signal_watch.differ import Diff, compare, shrink_error
from signal_watch.extractor import ExtractError, extract_lines
from signal_watch.fetcher import Crawler, FetchError, NotModified, Validators
from signal_watch.store import SnapshotStore, TargetState

# 失敗が続いたときに取得間隔を延ばす上限
MAX_BACKOFF_HOURS = 24
# この回数続けて失敗したら利用者に知らせる
FAILURE_NOTIFY_THRESHOLD = 3


class Outcome(Enum):
    SKIPPED = "間隔内"
    FIRST = "初回保存"
    CHANGED = "変更あり"
    UPDATED = "更新(通知なし)"
    UNCHANGED = "変更なし"
    FAILED = "失敗"


@dataclass(frozen=True)
class TargetResult:
    target: Target
    outcome: Outcome
    detail: str = ""
    diff: Diff | None = None
    commit: str | None = None  # スナップショットのコミット SHA(差分画面へのリンクに使う)
    notify_failure: bool = False  # 連続失敗が閾値に達した(通知する)
    recovered: bool = False  # 失敗の通知後に回復した(通知する)


class _CheckError(Exception):
    """取得・抽出・急減の検出のいずれかの失敗。"""


def run(
    targets: list[Target],
    store: SnapshotStore,
    crawler: Crawler,
    *,
    forced_ids: set[str] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> list[TargetResult]:
    """有効な監視対象を巡回する。

    forced_ids を指定すると、その対象だけを最小間隔(1時間)で取得する。
    """
    state = store.load_state()
    started = now()
    results: list[TargetResult] = []
    for target in targets:
        if forced_ids is not None and target.id not in forced_ids:
            continue
        if forced_ids is None and not target.enabled:
            continue
        target_state = state.of(target.id)
        interval = _interval(target, target_state, forced=forced_ids is not None)
        last = target_state.last_checked_at
        if last is not None and started - last < interval:
            results.append(
                TargetResult(
                    target, Outcome.SKIPPED, f"次回は {last + interval:%m/%d %H:%M} UTC 以降"
                )
            )
            continue
        results.append(_check(target, target_state, store, crawler, started))

    state_path = store.save_state(state)
    store.commit([state_path], f"state: 巡回 {started:%Y-%m-%d %H:%M} UTC")
    return results


def _interval(target: Target, state: TargetState, *, forced: bool) -> timedelta:
    if forced:
        return timedelta(hours=MIN_INTERVAL_HOURS)
    hours = target.interval_hours
    if state.consecutive_failures:
        # 失敗が続く間は間隔を倍々に延ばす(上限 24 時間。もともと長い間隔はそのまま)
        backoff = min(hours * 2**state.consecutive_failures, MAX_BACKOFF_HOURS)
        hours = max(hours, backoff)
    return timedelta(hours=hours)


def _check(
    target: Target,
    state: TargetState,
    store: SnapshotStore,
    crawler: Crawler,
    now: datetime,
) -> TargetResult:
    state.last_checked_at = now
    old = store.read_lines(target.id)
    try:
        result = _fetch_and_save(target, state, store, crawler, old, now)
    except _CheckError as e:
        state.consecutive_failures += 1
        state.last_error = str(e)
        notify = (
            state.consecutive_failures >= FAILURE_NOTIFY_THRESHOLD and not state.failure_notified
        )
        if notify:
            state.failure_notified = True
        detail = f"{e}(連続 {state.consecutive_failures} 回)"
        return TargetResult(target, Outcome.FAILED, detail, notify_failure=notify)

    recovered = state.failure_notified
    state.consecutive_failures = 0
    state.last_error = None
    state.failure_notified = False
    if recovered:
        return TargetResult(
            result.target, result.outcome, result.detail, result.diff, result.commit, recovered=True
        )
    return result


def _fetch_and_save(
    target: Target,
    state: TargetState,
    store: SnapshotStore,
    crawler: Crawler,
    old: list[str] | None,
    now: datetime,
) -> TargetResult:
    # スナップショットが無いときは、前回の応答が残っていても全文を取り直す
    validators = Validators(state.etag, state.last_modified) if old is not None else None
    try:
        page = crawler.fetch(target.url, validators)
    except FetchError as e:
        raise _CheckError(str(e)) from e
    if isinstance(page, NotModified):
        return TargetResult(target, Outcome.UNCHANGED, "304 Not Modified")

    try:
        lines = extract_lines(page.content, encoding=page.encoding, url=page.url, target=target)
    except ExtractError as e:
        raise _CheckError(str(e)) from e
    state.etag = page.validators.etag
    state.last_modified = page.validators.last_modified

    if old is None:
        path = store.write_lines(target, lines)
        sha = store.commit([path], f"snapshot({target.id}): 初回取得 {len(lines)} 行")
        return TargetResult(target, Outcome.FIRST, f"{len(lines)} 行", commit=sha)

    shrink = shrink_error(old, lines)
    if shrink:
        raise _CheckError(shrink)
    if lines == old:
        return TargetResult(target, Outcome.UNCHANGED, "内容が同じ")

    diff = compare(old, lines, target.diff_mode)
    path = store.write_lines(target, lines)
    counts = f"+{diff.added} -{diff.removed}"
    if not diff.changed:
        # added_only で押し出された行の削除だけ。通知はしないが、次の比較のために保存する
        store.commit([path], f"snapshot({target.id}): {counts}(通知なし)")
        return TargetResult(target, Outcome.UPDATED, counts, diff)
    sha = store.commit([path], f"snapshot({target.id}): {counts}")
    state.last_changed_at = now
    return TargetResult(target, Outcome.CHANGED, counts, diff, sha)
