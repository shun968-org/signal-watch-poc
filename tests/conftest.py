import subprocess
from pathlib import Path

import pytest

from signal_watch.store import SnapshotStore


@pytest.fixture
def store(tmp_path: Path) -> SnapshotStore:
    """snapshots ブランチの代わりの、空の git リポジトリ。"""
    root = tmp_path / "snapshots"
    root.mkdir()
    for args in (
        ["init", "--quiet", "--initial-branch", "snapshots"],
        ["config", "user.name", "test"],
        ["config", "user.email", "test@example.com"],
        ["commit", "--quiet", "--allow-empty", "-m", "init"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True)
    return SnapshotStore(root)


def git_log(store: SnapshotStore) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(store.root), "log", "--format=%s"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return out.splitlines()
