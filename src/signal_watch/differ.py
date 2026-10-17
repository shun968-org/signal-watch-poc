"""前回のテキストとの比較と、通知用の抜粋(基本設計 F-05)。"""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from signal_watch.config import DiffMode

# 通知に載せる抜粋の上限
EXCERPT_MAX_LINES = 15
EXCERPT_MAX_CHARS = 1500
# 変更行の前後に付ける文脈の行数
CONTEXT_LINES = 1
# 前回よりこの割合以上に行数が減ったら、変更ではなくページ構造の変化(抽出の失敗)とみなす
SHRINK_RATIO = 0.5


@dataclass(frozen=True)
class Diff:
    """前回との比較結果。"""

    changed: bool  # 通知・保存すべき変更があるか
    added: int  # 追加された行数
    removed: int  # 削除された行数
    excerpt: tuple[str, ...]  # 通知用の抜粋。追加行は "+ "、削除行は "- "、文脈は "  " で始まる


def compare(old: list[str], new: list[str], mode: DiffMode) -> Diff:
    """前回(old)と今回(new)の行を比べる。

    mode が added_only のときは、追加行があるときだけ変更とみなす(一覧の末尾から押し出された行の
    削除は通知しない)。抜粋にも追加行だけを載せる。
    """
    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    added = removed = 0
    excerpt: list[str] = []
    for group in matcher.get_grouped_opcodes(CONTEXT_LINES):
        if excerpt and mode == "lines":
            excerpt.append("  …")  # 離れた変更の区切り
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                if mode == "lines":
                    excerpt.extend(f"  {line}" for line in old[i1:i2])
                continue
            if tag in ("replace", "delete"):
                removed += i2 - i1
                if mode == "lines":
                    excerpt.extend(f"- {line}" for line in old[i1:i2])
            if tag in ("replace", "insert"):
                added += j2 - j1
                excerpt.extend(f"+ {line}" for line in new[j1:j2])

    changed = added > 0 if mode == "added_only" else (added + removed) > 0
    return Diff(
        changed=changed, added=added, removed=removed, excerpt=_truncate(excerpt) if changed else ()
    )


def shrink_error(old: list[str], new: list[str]) -> str | None:
    """行数が急に減っていれば、その理由を返す(変更として通知せず、取得の失敗として扱うため)。"""
    if old and len(new) < len(old) * (1 - SHRINK_RATIO):
        return (
            f"比較範囲の行数が {len(old)} 行から {len(new)} 行に急減した"
            "(ページ構造が変わった可能性。設定の selector を確認する)"
        )
    return None


def _truncate(lines: list[str]) -> tuple[str, ...]:
    kept: list[str] = []
    chars = 0
    for line in lines:
        if len(kept) >= EXCERPT_MAX_LINES or chars + len(line) > EXCERPT_MAX_CHARS:
            if not kept:  # 1行目から長すぎるときは、その行を切り詰めて載せる
                kept.append(line[: EXCERPT_MAX_CHARS - 1] + "…")
            break
        kept.append(line)
        chars += len(line)
    rest = len(lines) - len(kept)
    if rest:
        kept.append(f"(ほか {rest} 行)")
    return tuple(kept)
