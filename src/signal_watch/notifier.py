"""Slack への通知(基本設計 F-07・F-08)。

Incoming Webhook に Block Kit のメッセージを送る。Webhook URL は秘密情報なので、
ログ・例外のメッセージに含めない。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

TIMEOUT_SECONDS = 10
# Slack の Incoming Webhook は 1 秒に 1 件程度に抑える
SEND_INTERVAL_SECONDS = 1.0
# Block Kit の上限(header は 150 文字、section の text は 3000 文字)
_HEADER_MAX = 150
_SECTION_MAX = 3000

JST = timezone(timedelta(hours=9), "JST")


@dataclass(frozen=True)
class Notice:
    """通知1件分の内容。巡回の結果(runner.TargetResult)から作る。"""

    kind: str  # "changed" / "failed" / "recovered" / "test"
    name: str
    url: str
    detected_at: datetime
    added: int = 0
    removed: int = 0
    excerpt: tuple[str, ...] = ()
    diff_url: str | None = None
    error: str | None = None
    failures: int = 0


class NotifyError(Exception):
    """通知を送れなかった(メッセージに Webhook URL は含めない)。"""


def build_message(notice: Notice) -> dict[str, Any]:
    """Incoming Webhook に送る JSON を作る。"""
    when = notice.detected_at.astimezone(JST).strftime("%Y-%m-%d %H:%M JST")
    page_link = f"<{notice.url}|元のページ>"
    if notice.kind == "changed":
        title = f"【変更】{notice.name}"
        summary = f"{when} に変更を検出しました(追加 {notice.added} 行・削除 {notice.removed} 行)"
        links = [page_link]
        if notice.diff_url:
            links.insert(0, f"<{notice.diff_url}|差分を見る>")
        blocks = [
            _header(title),
            _section(summary),
            _section(_code_block(notice.excerpt)),
            _context(" ・ ".join(links)),
        ]
    elif notice.kind == "failed":
        title = f"【取得失敗】{notice.name}"
        summary = (
            f"{notice.failures} 回続けて取得に失敗しています({when} 時点)。"
            "回復するまで取得間隔を延ばします。"
        )
        blocks = [
            _header(title),
            _section(summary),
            _section(_code_block((notice.error or "",))),
            _context(page_link),
        ]
    elif notice.kind == "recovered":
        title = f"【回復】{notice.name}"
        blocks = [_header(title), _section(f"{when} に取得が回復しました。"), _context(page_link)]
    else:
        title = "【テスト】signal-watch-poc の通知"
        blocks = [_header(title), _section(f"{when} 通知の設定を確かめるためのテストです。")]
    return {"text": title, "blocks": blocks}


def send(
    webhook_url: str,
    notices: list[Notice],
    *,
    session: requests.Session | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """通知を順に送る。1件でも失敗したら NotifyError(残りは送らない)。"""
    session = session or requests.Session()
    for index, notice in enumerate(notices):
        if index:
            sleep(SEND_INTERVAL_SECONDS)
        try:
            response = session.post(
                webhook_url, json=build_message(notice), timeout=TIMEOUT_SECONDS
            )
        except requests.RequestException as e:
            raise NotifyError(f"Slack に送れなかった: {e.__class__.__name__}") from None
        if response.status_code != 200:
            body = response.text[:200]
            raise NotifyError(f"Slack が HTTP {response.status_code} を返した: {body}")


def _header(text: str) -> dict[str, Any]:
    if len(text) > _HEADER_MAX:
        text = text[: _HEADER_MAX - 1] + "…"
    return {"type": "header", "text": {"type": "plain_text", "text": text}}


def _section(text: str) -> dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text[:_SECTION_MAX]}}


def _context(text: str) -> dict[str, Any]:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}


def _escape(text: str) -> str:
    """Slack の mrkdwn で特別な意味を持つ &・<・> を文字として出す(「<URL>」をリンクにしない)。"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _code_block(lines: tuple[str, ...]) -> str:
    # コードブロックの中では mrkdwn の装飾が効かないので、ページの文字がそのまま出る。
    # ``` を含む行で閉じてしまわないよう置き換える
    body = "\n".join(_escape(line).replace("```", "'''") for line in lines)
    limit = _SECTION_MAX - len("```\n\n```")
    if len(body) > limit:
        body = body[: limit - 1] + "…"
    return f"```\n{body}\n```"
