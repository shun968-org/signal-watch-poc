"""スナップショットと実行状態の保存(基本設計 F-06・データ設計)。

保存先は snapshots ブランチをチェックアウトしたディレクトリ。
  targets/<id>.txt  抽出したテキスト(先頭に出典表示)
  state.json        監視対象ごとの実行状態
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from signal_watch.config import Target, source_of

# スナップショットの先頭の出典表示の行数(内容は毎回同じなので差分に出ない)
HEADER_LINES = 3


@dataclass
class TargetState:
    """監視対象1件の実行状態(データ設計 state.json)。"""

    last_checked_at: datetime | None = None
    last_changed_at: datetime | None = None
    etag: str | None = None
    last_modified: str | None = None
    consecutive_failures: int = 0
    last_error: str | None = None
    failure_notified: bool = False


@dataclass
class State:
    targets: dict[str, TargetState] = field(default_factory=dict)

    def of(self, target_id: str) -> TargetState:
        return self.targets.setdefault(target_id, TargetState())


class SnapshotStore:
    """snapshots ブランチの作業ディレクトリへの読み書きとコミット。"""

    def __init__(self, root: Path) -> None:
        self.root = root

    def snapshot_path(self, target_id: str) -> Path:
        return self.root / "targets" / f"{target_id}.txt"

    def read_lines(self, target_id: str) -> list[str] | None:
        path = self.snapshot_path(target_id)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8").splitlines()[HEADER_LINES:]

    def write_lines(self, target: Target, lines: list[str]) -> Path:
        path = self.snapshot_path(target.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        source = source_of(target.url)
        header = [
            f"出典:「{target.name}」({source.publisher})({target.url})",
            f"{source.license}に基づき、signal-watch-poc が本文のテキストを抽出・加工して作成",
            "",
        ]
        assert len(header) == HEADER_LINES
        path.write_text("\n".join(header + lines) + "\n", encoding="utf-8")
        return path

    def load_state(self) -> State:
        path = self.root / "state.json"
        if not path.exists():
            return State()
        raw = json.loads(path.read_text(encoding="utf-8"))
        return State(
            targets={key: _state_from_json(value) for key, value in raw["targets"].items()}
        )

    def save_state(self, state: State) -> Path:
        path = self.root / "state.json"
        data = {"targets": {key: _state_to_json(value) for key, value in state.targets.items()}}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def commit(self, paths: list[Path], message: str) -> str | None:
        """paths の変更をコミットし、コミットの SHA を返す。変更が無ければ何もせず None。"""
        self._git("add", "--", *(str(p.relative_to(self.root)) for p in paths))
        if self._git("diff", "--cached", "--quiet", check=False).returncode == 0:
            return None
        self._git("commit", "--quiet", "-m", message)
        return self._git("rev-parse", "HEAD").stdout.strip()

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.root), *args], check=check, capture_output=True, text=True
        )


def _state_to_json(state: TargetState) -> dict[str, Any]:
    data = asdict(state)
    for key in ("last_checked_at", "last_changed_at"):
        value = data[key]
        data[key] = value.isoformat().replace("+00:00", "Z") if value else None
    return data


def _state_from_json(data: dict[str, Any]) -> TargetState:
    state = TargetState(**data)
    for key in ("last_checked_at", "last_changed_at"):
        value = getattr(state, key)
        if isinstance(value, str):
            setattr(state, key, datetime.fromisoformat(value).astimezone(UTC))
    return state
