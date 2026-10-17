"""スナップショットの履歴の削除(基本設計 F-11・REQ-018)。

snapshots ブランチのうち、作成日時(author date)が保存期間より古いコミットを1つの起点コミットに
まとめ、それ以降のコミットをその上に積み直す。最新の内容(ファイル)は変わらない。
履歴を書き換えるので、コミットの SHA が変わり、それまでの通知の「差分を見る」のリンクは開けなくなる
(2026-10-17 に受け入れると決定)。push は呼び出し側(ワークフロー)が強制 push で行う。
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

RETENTION_DAYS = 30


@dataclass(frozen=True)
class PruneResult:
    squashed: int  # 起点コミットにまとめたコミットの数
    kept: int  # 積み直したコミットの数
    cutoff: datetime


def prune(
    root: Path, *, now: datetime, days: int = RETENTION_DAYS, dry_run: bool = False
) -> PruneResult:
    cutoff = now - timedelta(days=days)
    commits = [
        (sha, datetime.fromtimestamp(int(ts), UTC))
        for sha, ts in (
            line.split() for line in _git(root, "log", "--reverse", "--format=%H %at").splitlines()
        )
    ]
    old = [(sha, at) for sha, at in commits if at < cutoff]
    kept = len(commits) - len(old)
    # 古いコミットが1つ以下なら、まとめるものが無い
    if len(old) <= 1 or dry_run:
        return PruneResult(squashed=len(old) if len(old) > 1 else 0, kept=kept, cutoff=cutoff)

    base, base_at = old[-1]
    tree = _git(root, "rev-parse", f"{base}^{{tree}}").strip()
    message = (
        f"snapshots: {cutoff:%Y-%m-%d} より前の履歴 {len(old)} 件をまとめた"
        f"(保存期間 {days} 日。基本設計 F-11)"
    )
    # 起点コミットの作成日時は、まとめた最後のコミットの日時にする(次回の判定で古い側に入るように)
    date = base_at.isoformat()
    new_root = _git(
        root,
        "commit-tree",
        tree,
        "-m",
        message,
        env={"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
    ).strip()
    if kept:
        # 積み直してもコミットの作成日時(author date)は保たれる
        _git(root, "-c", "core.hooksPath=/dev/null", "rebase", "--quiet", "--onto", new_root, base)
    else:
        _git(root, "reset", "--quiet", "--hard", new_root)
    return PruneResult(squashed=len(old), kept=kept, cutoff=cutoff)


def _git(root: Path, *args: str, env: dict[str, str] | None = None) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    ).stdout
