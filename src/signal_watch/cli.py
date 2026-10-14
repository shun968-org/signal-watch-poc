"""コマンドラインの入口(`python -m signal_watch`)。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from signal_watch.config import ConfigError, load_targets

DEFAULT_TARGETS_PATH = Path("targets.yaml")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="signal_watch")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-config", help="監視対象の設定ファイルを検証する")
    validate.add_argument("path", nargs="?", type=Path, default=DEFAULT_TARGETS_PATH)
    args = parser.parse_args(argv)

    # コマンドは今のところ validate-config だけ(巡回の run はマイルストーン 2 で足す)
    return _validate_config(args.path)


def _validate_config(path: Path) -> int:
    try:
        targets = load_targets(path)
    except ConfigError as e:
        print(f"{path} に問題があります:", file=sys.stderr)
        for error in e.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    enabled = sum(t.enabled for t in targets)
    print(f"{path}: OK(監視対象 {len(targets)} 件、うち有効 {enabled} 件)")
    return 0
