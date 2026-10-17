import json
import subprocess
from typing import Any

import pytest

from signal_watch.notifier import Notice, build_message
from signal_watch.summarizer import MAX_SUMMARY_CHARS, MODEL, SummaryRequest, summarize

REQUEST = SummaryRequest(name="新着", url="https://www.digital.go.jp/news", excerpt=("+ - 追加",))
ENV = {
    "CLAUDE_CODE_OAUTH_TOKEN": "oauth",
    "ANTHROPIC_API_KEY": "sk-should-not-be-used",
    "ANTHROPIC_AUTH_TOKEN": "x",
    "CLAUDE_CODE_USE_BEDROCK": "1",
    "PATH": "/usr/bin",
}


class FakeClaude:
    """claude コマンドの代わり。呼ばれた引数と環境変数を記録する。"""

    def __init__(
        self,
        auth: dict[str, Any] | None = None,
        stdout: str = "要約です。",
        returncode: int = 0,
        raises: Exception | None = None,
    ) -> None:
        self.auth = auth or {
            "loggedIn": True,
            "authMethod": "oauth_token",
            "apiProvider": "firstParty",
        }
        self.stdout = stdout
        self.returncode = returncode
        self.raises = raises
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((args, kwargs))
        if args[:3] == ["claude", "auth", "status"]:
            return subprocess.CompletedProcess(args, 0, json.dumps(self.auth), "")
        if self.raises:
            raise self.raises
        return subprocess.CompletedProcess(args, self.returncode, self.stdout, "")


def test_summarizes_with_subscription_and_no_api_keys() -> None:
    claude = FakeClaude(stdout="  新しいお知らせが1件追加されました。\n")
    assert summarize(REQUEST, environ=ENV, run=claude) == "新しいお知らせが1件追加されました。"

    args, kwargs = claude.calls[-1]
    assert args[:2] == ["claude", "-p"]
    assert args[args.index("--model") + 1] == MODEL
    assert args[args.index("--tools") + 1] == ""
    assert "--no-session-persistence" in args
    assert "--bare" not in args
    assert "+ - 追加" in kwargs["input"]
    for _, call_kwargs in claude.calls:
        env = call_kwargs["env"]
        assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "oauth"
        assert not any(key.startswith("ANTHROPIC_") for key in env)
        assert "CLAUDE_CODE_USE_BEDROCK" not in env


def test_no_token_means_no_summary_and_no_call() -> None:
    claude = FakeClaude()
    assert summarize(REQUEST, environ={"ANTHROPIC_API_KEY": "sk"}, run=claude) is None
    assert claude.calls == []


@pytest.mark.parametrize(
    "auth",
    [
        {"authMethod": "api_key", "apiProvider": "firstParty"},
        {"authMethod": "oauth_token", "apiProvider": "bedrock"},
        {"loggedIn": False},
    ],
)
def test_non_subscription_auth_is_refused(auth: dict[str, Any]) -> None:
    claude = FakeClaude(auth=auth)
    assert summarize(REQUEST, environ=ENV, run=claude) is None
    assert [args[:2] for args, _ in claude.calls] == [["claude", "auth"]]


@pytest.mark.parametrize(
    "claude",
    [
        FakeClaude(returncode=1),
        FakeClaude(stdout="   "),
        FakeClaude(raises=subprocess.TimeoutExpired("claude", 180)),
        FakeClaude(raises=FileNotFoundError("claude")),
    ],
    ids=["exit-code", "empty", "timeout", "not-installed"],
)
def test_failures_return_none(claude: FakeClaude) -> None:
    assert summarize(REQUEST, environ=ENV, run=claude) is None


def test_long_summary_is_truncated() -> None:
    summary = summarize(REQUEST, environ=ENV, run=FakeClaude(stdout="あ" * 1000))
    assert summary is not None and len(summary) == MAX_SUMMARY_CHARS


def test_summary_is_shown_and_escaped_in_message() -> None:
    from datetime import UTC, datetime

    notice = Notice(
        kind="changed",
        name="新着",
        url="https://www.digital.go.jp/news",
        detected_at=datetime(2026, 10, 17, tzinfo=UTC),
        excerpt=("+ a",),
        summary="<b>追加</b> & 更新",
    )
    blocks = build_message(notice)["blocks"]
    texts = [b["text"]["text"] for b in blocks if b["type"] == "section"]
    assert any("AI による要約" in t and "&lt;b&gt;追加&lt;/b&gt; &amp; 更新" in t for t in texts)
    assert all("AI による要約" not in t for t in texts if t.startswith("```"))
