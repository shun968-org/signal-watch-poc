"""コマンドラインの入口(`python -m signal_watch`)。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from signal_watch.config import ConfigError, Target, load_targets
from signal_watch.fetcher import Crawler, FetchError, NotModified
from signal_watch.runner import Outcome, TargetResult, run
from signal_watch.store import SnapshotStore

DEFAULT_TARGETS_PATH = Path("targets.yaml")


def main(argv: list[str] | None = None, *, crawler: Crawler | None = None) -> int:
    parser = argparse.ArgumentParser(prog="signal_watch")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-config", help="監視対象の設定ファイルを検証する")
    validate.add_argument("path", nargs="?", type=Path, default=DEFAULT_TARGETS_PATH)

    fetch = commands.add_parser("fetch", help="有効な監視対象を取得して結果を表示する")
    fetch.add_argument("--targets", type=Path, default=DEFAULT_TARGETS_PATH)
    fetch.add_argument("--id", dest="ids", action="append", help="取得する対象の id(複数可)")
    fetch.add_argument("--save-dir", type=Path, help="取得した HTML を <id>.html として保存する")
    fetch.add_argument(
        "--summary",
        type=Path,
        default=os.environ.get("GITHUB_STEP_SUMMARY"),
        help="結果の表(Markdown)を追記するファイル。既定は GitHub Actions のジョブサマリー",
    )

    run_parser = commands.add_parser(
        "run", help="取得間隔に達した対象を巡回し、変更をスナップショットに保存する"
    )
    run_parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS_PATH)
    run_parser.add_argument(
        "--snapshots", type=Path, required=True, help="snapshots ブランチの作業ディレクトリ"
    )
    run_parser.add_argument(
        "--id", dest="ids", action="append", help="この対象だけを取得する(最小間隔 1 時間は守る)"
    )
    run_parser.add_argument("--summary", type=Path, default=os.environ.get("GITHUB_STEP_SUMMARY"))

    args = parser.parse_args(argv)
    if args.command == "validate-config":
        return _validate_config(args.path)
    if args.command == "run":
        return _run(args.targets, args.snapshots, args.ids, args.summary, crawler or Crawler())
    return _fetch(args.targets, args.ids, args.save_dir, args.summary, crawler or Crawler())


def _load(path: Path) -> list[Target] | None:
    try:
        return load_targets(path)
    except ConfigError as e:
        print(f"{path} に問題があります:", file=sys.stderr)
        for error in e.errors:
            print(f"  - {error}", file=sys.stderr)
        return None


def _validate_config(path: Path) -> int:
    targets = _load(path)
    if targets is None:
        return 1
    enabled = sum(t.enabled for t in targets)
    print(f"{path}: OK(監視対象 {len(targets)} 件、うち有効 {enabled} 件)")
    return 0


def _fetch(
    path: Path,
    ids: list[str] | None,
    save_dir: Path | None,
    summary: Path | None,
    crawler: Crawler,
) -> int:
    targets = _load(path)
    if targets is None:
        return 1
    if ids:
        unknown = set(ids) - {t.id for t in targets}
        if unknown:
            print(f"不明な id: {', '.join(sorted(unknown))}", file=sys.stderr)
            return 1
        targets = [t for t in targets if t.id in ids]
    else:
        targets = [t for t in targets if t.enabled]

    rows: list[tuple[str, str, str]] = []  # (結果, id, 詳細)
    for target in targets:
        try:
            result = crawler.fetch(target.url)
        except FetchError as e:
            rows.append(("失敗", target.id, str(e)))
        else:
            if isinstance(result, NotModified):
                rows.append(("変更なし", target.id, "304 Not Modified"))
            else:
                rows.append(("取得", target.id, f"{len(result.content)} バイト"))
                if save_dir:
                    save_dir.mkdir(parents=True, exist_ok=True)
                    (save_dir / f"{target.id}.html").write_bytes(result.content)
        print("\t".join(rows[-1]))

    if summary:
        _write_summary(summary, rows)
    return 1 if any(status == "失敗" for status, _, _ in rows) else 0


def _run(
    path: Path, snapshots: Path, ids: list[str] | None, summary: Path | None, crawler: Crawler
) -> int:
    targets = _load(path)
    if targets is None:
        return 1
    if ids:
        unknown = set(ids) - {t.id for t in targets}
        if unknown:
            print(f"不明な id: {', '.join(sorted(unknown))}", file=sys.stderr)
            return 1
    results = run(targets, SnapshotStore(snapshots), crawler, forced_ids=set(ids) if ids else None)
    rows = [_result_row(r) for r in results]
    for row in rows:
        print("\t".join(row))
    if summary:
        _write_summary(summary, rows, title="巡回結果")
    # 失敗は state.json に記録し、続いたら通知する。ワークフローは失敗させない
    return 0


def _result_row(result: TargetResult) -> tuple[str, str, str]:
    detail = result.detail
    if result.commit:
        detail += f"(コミット {result.commit[:7]})"
    if result.recovered:
        detail += "(回復)"
    if result.outcome is Outcome.FAILED and result.notify_failure:
        detail += "(通知対象)"
    return (result.outcome.value, result.target.id, detail)


def _write_summary(
    path: Path, rows: list[tuple[str, str, str]], *, title: str = "取得結果"
) -> None:
    lines = [f"## {title}", "", "| 結果 | 対象 | 詳細 |", "|---|---|---|"]
    lines += [
        f"| {status} | `{target_id}` | {detail.replace('|', '\\|')} |"
        for status, target_id, detail in rows
    ]
    with path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
