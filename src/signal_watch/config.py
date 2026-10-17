"""監視対象の設定ファイル(targets.yaml)の読み込みと検証(基本設計 F-01)。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlsplit

import yaml


@dataclass(frozen=True)
class Source:
    """取得元サイトの運営者と、コンテンツの利用規約(スナップショットの出典表示に使う)。"""

    publisher: str
    license: str


# 取得してよいドメインと、その出典表示。利用規約・robots.txt を確認したサイトだけを足す
# (.devcontainer/init-firewall.sh の「巡回対象の Web サイト」とも揃える)
SOURCES: dict[str, Source] = {
    "www.digital.go.jp": Source(publisher="デジタル庁", license="公共データ利用規約(第1.0版)"),
}
ALLOWED_DOMAINS = frozenset(SOURCES)
MIN_INTERVAL_HOURS = 1
DEFAULT_INTERVAL_HOURS = 6

DiffMode = Literal["lines", "added_only"]
DIFF_MODES: tuple[DiffMode, ...] = ("lines", "added_only")

_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_KNOWN_KEYS = frozenset(
    {
        "id",
        "name",
        "url",
        "interval_hours",
        "selector",
        "exclude_selectors",
        "exclude_patterns",
        "diff_mode",
        "enabled",
    }
)


def source_of(url: str) -> Source:
    """URL の取得元の出典表示。許可ドメインの URL であること(設定の検証で保証される)。"""
    host = urlsplit(url).hostname
    return SOURCES[host or ""]


@dataclass(frozen=True)
class Target:
    """監視対象1件。"""

    id: str
    name: str
    url: str
    interval_hours: int = DEFAULT_INTERVAL_HOURS
    selector: str | None = None
    exclude_selectors: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()
    diff_mode: DiffMode = "lines"
    enabled: bool = True


class ConfigError(Exception):
    """設定ファイルが不正。見つかった問題をすべて `errors` に持つ。"""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


def load_targets(path: Path) -> list[Target]:
    """設定ファイルを読み、検証済みの監視対象を返す。不正なら ConfigError を投げる。"""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise ConfigError([f"{path}: 読み込めません: {e}"]) from e
    return parse_targets(data)


def parse_targets(data: object) -> list[Target]:
    """YAML から読んだ値を検証して監視対象にする。問題はまとめて ConfigError で報告する。"""
    if not isinstance(data, dict) or not isinstance(data.get("targets"), list):
        raise ConfigError(["最上位に targets(監視対象のリスト)が必要です"])
    unknown_top = set(data) - {"targets"}
    errors = [f"最上位の不明な項目: {key}" for key in sorted(map(str, unknown_top))]

    targets: list[Target] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(cast(list[object], data["targets"])):
        raw_id = item.get("id") if isinstance(item, dict) else None
        label = f"targets[{index}]" + (f"({raw_id})" if isinstance(raw_id, str) else "")
        if isinstance(raw_id, str):
            if raw_id in seen_ids:
                errors.append(f"{label}: id が重複しています")
            seen_ids.add(raw_id)
        target, item_errors = _parse_target(item)
        errors.extend(f"{label}: {message}" for message in item_errors)
        if target is not None:
            targets.append(target)

    if errors:
        raise ConfigError(errors)
    return targets


def _parse_target(item: object) -> tuple[Target | None, list[str]]:
    if not isinstance(item, dict):
        return None, ["監視対象はキーと値の組で書いてください"]
    raw = cast(dict[str, Any], item)
    errors = [f"不明な項目: {key}" for key in sorted(map(str, set(raw) - _KNOWN_KEYS))]

    target_id = raw.get("id")
    if not isinstance(target_id, str) or not _ID_PATTERN.fullmatch(target_id):
        errors.append("id は英小文字・数字・ハイフンで書いてください")

    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("name が必要です")

    url = raw.get("url")
    if not isinstance(url, str):
        errors.append("url が必要です")
    else:
        errors.extend(_check_url(url))

    interval = raw.get("interval_hours", DEFAULT_INTERVAL_HOURS)
    # bool は int の一種なので除く(interval_hours: true を 1 時間と解釈しない)
    if isinstance(interval, bool) or not isinstance(interval, int):
        errors.append("interval_hours は整数で書いてください")
    elif interval < MIN_INTERVAL_HOURS:
        errors.append(f"interval_hours は {MIN_INTERVAL_HOURS} 以上にしてください")

    selector = raw.get("selector")
    if selector is not None and (not isinstance(selector, str) or not selector.strip()):
        errors.append("selector は空でない文字列で書いてください")

    exclude_selectors = _string_list(raw, "exclude_selectors", errors)
    exclude_patterns = _string_list(raw, "exclude_patterns", errors)
    for pattern in exclude_patterns:
        try:
            re.compile(pattern)
        except re.error as e:
            errors.append(f"exclude_patterns の正規表現が不正です: {pattern!r}({e})")

    diff_mode = raw.get("diff_mode", "lines")
    if diff_mode not in DIFF_MODES:
        errors.append(f"diff_mode は {' / '.join(DIFF_MODES)} のどれかにしてください")

    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        errors.append("enabled は true / false で書いてください")

    if errors:
        return None, errors
    return (
        Target(
            id=cast(str, target_id),
            name=cast(str, name),
            url=cast(str, url),
            interval_hours=cast(int, interval),
            selector=cast("str | None", selector),
            exclude_selectors=exclude_selectors,
            exclude_patterns=exclude_patterns,
            diff_mode=cast(DiffMode, diff_mode),
            enabled=cast(bool, enabled),
        ),
        [],
    )


def _check_url(url: str) -> list[str]:
    parts = urlsplit(url)
    if parts.scheme != "https":
        return ["url は https で書いてください"]
    if parts.hostname not in ALLOWED_DOMAINS:
        allowed = ", ".join(sorted(ALLOWED_DOMAINS))
        return [f"url のドメイン {parts.hostname} は許可されていません(許可: {allowed})"]
    if parts.username or parts.password or parts.port:
        return ["url にユーザー名・パスワード・ポートを含めないでください"]
    return []


def _string_list(raw: dict[str, Any], key: str, errors: list[str]) -> tuple[str, ...]:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        errors.append(f"{key} は空でない文字列のリストで書いてください")
        return ()
    return tuple(cast(list[str], value))
