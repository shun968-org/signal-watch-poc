import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests

from signal_watch.cli import main
from signal_watch.config import Target
from signal_watch.differ import Diff
from signal_watch.notifier import Notice, NotifyError, build_message, send
from signal_watch.report import notices_from_results, write_results
from signal_watch.runner import Outcome, TargetResult
from tests.fake_http import FakeAdapter, Reply, session_with

WEBHOOK = "https://hooks.slack.com/services/T000/B000/secret"
AT = datetime(2026, 10, 17, 0, 17, tzinfo=UTC)
TARGET = Target(id="example", name="例のページ", url="https://www.digital.go.jp/x")


def _changed(**overrides: object) -> Notice:
    fields: dict[str, object] = {
        "kind": "changed",
        "name": "例のページ",
        "url": "https://www.digital.go.jp/x",
        "detected_at": AT,
        "added": 1,
        "removed": 0,
        "excerpt": ("  前の行", "+ 追加 <https://www.digital.go.jp/y> & ```"),
        "diff_url": "https://github.com/o/r/commit/abc",
    }
    fields.update(overrides)
    return Notice(**fields)  # type: ignore[arg-type]


def test_changed_message() -> None:
    message = build_message(_changed())
    assert message["text"] == "【変更】例のページ"
    text = json.dumps(message, ensure_ascii=False)
    assert "2026-10-17 09:17 JST" in text  # 検出日時は JST
    assert "追加 1 行・削除 0 行" in text
    assert "<https://github.com/o/r/commit/abc|差分を見る>" in text
    assert "<https://www.digital.go.jp/x|元のページ>" in text
    # 抜粋の中の < > & はエスケープし、``` でコードブロックが閉じないようにする
    code = message["blocks"][2]["text"]["text"]
    assert code.startswith("```\n") and code.endswith("\n```")
    assert "&lt;https://www.digital.go.jp/y&gt; &amp; '''" in code


def test_failed_and_recovered_messages() -> None:
    failed = build_message(
        Notice(
            kind="failed",
            name="例",
            url="https://www.digital.go.jp/x",
            detected_at=AT,
            error="HTTP 500",
            failures=3,
        )
    )
    assert failed["text"] == "【取得失敗】例"
    assert "3 回続けて" in json.dumps(failed, ensure_ascii=False)
    recovered = build_message(Notice(kind="recovered", name="例", url="u", detected_at=AT))
    assert recovered["text"] == "【回復】例"


def test_long_header_is_truncated() -> None:
    message = build_message(_changed(name="長" * 300))
    assert len(message["blocks"][0]["text"]["text"]) == 150


def test_send_posts_each_notice_with_interval() -> None:
    adapter = FakeAdapter({WEBHOOK: Reply(body=b"ok")})
    sleeps: list[float] = []
    send(WEBHOOK, [_changed(), _changed()], session=session_with(adapter), sleep=sleeps.append)
    assert len(adapter.requests) == 2
    assert sleeps == [1.0]


@pytest.mark.parametrize(
    "reply", [Reply(status=404, body=b"no_service"), requests.ConnectionError(WEBHOOK)]
)
def test_send_failure_does_not_leak_webhook_url(reply: Reply | Exception) -> None:
    adapter = FakeAdapter({WEBHOOK: reply})
    with pytest.raises(NotifyError) as excinfo:
        send(WEBHOOK, [_changed()], session=session_with(adapter))
    assert "secret" not in str(excinfo.value)
    assert excinfo.value.__cause__ is None


def test_results_round_trip_to_notices(tmp_path: Path) -> None:
    diff = Diff(changed=True, added=2, removed=1, excerpt=("+ a",))
    results = [
        TargetResult(TARGET, Outcome.CHANGED, "+2 -1", diff, commit="abc123"),
        TargetResult(TARGET, Outcome.UNCHANGED, "304"),
        TargetResult(TARGET, Outcome.FIRST, "8 行", commit="def456"),
        TargetResult(
            TARGET, Outcome.FAILED, "x", notify_failure=False, error="HTTP 500", failures=1
        ),
        TargetResult(
            TARGET, Outcome.FAILED, "x", notify_failure=True, error="HTTP 500", failures=3
        ),
        TargetResult(TARGET, Outcome.UNCHANGED, "内容が同じ", recovered=True),
    ]
    path = tmp_path / "results.json"
    write_results(path, results, AT)

    notices = notices_from_results(path, "https://github.com/o/r")
    assert [n.kind for n in notices] == ["changed", "failed", "recovered"]
    changed = notices[0]
    assert changed.diff_url == "https://github.com/o/r/commit/abc123"
    assert (changed.added, changed.removed, changed.excerpt) == (2, 1, ("+ a",))
    assert changed.detected_at == AT
    assert (notices[1].error, notices[1].failures) == ("HTTP 500", 3)


def test_notify_command_needs_webhook_only_when_there_is_something_to_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    path = tmp_path / "results.json"
    write_results(path, [TargetResult(TARGET, Outcome.UNCHANGED, "304")], AT)
    assert main(["notify", "--results", str(path)]) == 0
    assert "通知することはありません" in capsys.readouterr().out

    assert main(["notify", "--test"]) == 1
    assert "SLACK_WEBHOOK_URL" in capsys.readouterr().err
