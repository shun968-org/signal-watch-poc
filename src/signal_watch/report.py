"""巡回の結果を JSON に書き出し、通知の内容に変換する。

run(巡回とコミット)と notify(Slack への送信)を分けるため。ワークフローは run の後に
snapshots ブランチを push し、リンク先のコミットが GitHub に上がってから notify を実行する。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from signal_watch.notifier import Notice
from signal_watch.runner import Outcome, TargetResult

DEFAULT_REPOSITORY_URL = "https://github.com/shun968-org/signal-watch-poc"


def repository_url() -> str:
    """コミットへのリンクに使うリポジトリの URL(GitHub Actions では実行中のリポジトリ)。"""
    server = os.environ.get("GITHUB_SERVER_URL")
    repository = os.environ.get("GITHUB_REPOSITORY")
    if server and repository:
        return f"{server}/{repository}"
    return DEFAULT_REPOSITORY_URL


def write_results(path: Path, results: list[TargetResult], checked_at: datetime) -> None:
    data = {
        "checked_at": checked_at.isoformat(),
        "results": [_result_to_json(r) for r in results],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def notices_from_results(path: Path, repo_url: str) -> list[Notice]:
    """結果の JSON から、送るべき通知を取り出す(変更・連続失敗・回復)。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    checked_at = datetime.fromisoformat(data["checked_at"])
    notices: list[Notice] = []
    for item in data["results"]:
        common = {"name": item["name"], "url": item["url"], "detected_at": checked_at}
        if item["recovered"]:
            notices.append(Notice(kind="recovered", **common))
        if item["outcome"] == Outcome.CHANGED.name:
            commit = item["commit"]
            notices.append(
                Notice(
                    kind="changed",
                    added=item["added"],
                    removed=item["removed"],
                    excerpt=tuple(item["excerpt"]),
                    diff_url=f"{repo_url}/commit/{commit}" if commit else None,
                    **common,
                )
            )
        elif item["outcome"] == Outcome.FAILED.name and item["notify_failure"]:
            notices.append(
                Notice(kind="failed", error=item["error"], failures=item["failures"], **common)
            )
    return notices


def _result_to_json(result: TargetResult) -> dict[str, Any]:
    return {
        "id": result.target.id,
        "name": result.target.name,
        "url": result.target.url,
        "outcome": result.outcome.name,
        "detail": result.detail,
        "added": result.diff.added if result.diff else 0,
        "removed": result.diff.removed if result.diff else 0,
        "excerpt": list(result.diff.excerpt) if result.diff else [],
        "commit": result.commit,
        "notify_failure": result.notify_failure,
        "recovered": result.recovered,
        "error": result.error,
        "failures": result.failures,
    }
