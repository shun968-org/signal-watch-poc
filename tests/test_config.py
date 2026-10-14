from pathlib import Path
from typing import Any

import pytest

from signal_watch.cli import main
from signal_watch.config import ConfigError, Target, load_targets, parse_targets

REPO_ROOT = Path(__file__).resolve().parent.parent


def _target(**overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": "digital-news",
        "name": "デジタル庁 新着・更新",
        "url": "https://www.digital.go.jp/news",
    }
    item.update(overrides)
    return item


def _errors(data: object) -> list[str]:
    with pytest.raises(ConfigError) as excinfo:
        parse_targets(data)
    return excinfo.value.errors


def test_repository_targets_file_is_valid() -> None:
    targets = load_targets(REPO_ROOT / "targets.yaml")
    assert [t.id for t in targets] == [
        "digital-news",
        "digital-account-numbering-designate",
        "digital-jpki-user-list",
        "digital-electronic-invoice",
    ]
    assert targets[0].diff_mode == "added_only"


def test_defaults_are_applied() -> None:
    assert parse_targets({"targets": [_target()]}) == [
        Target(
            id="digital-news",
            name="デジタル庁 新着・更新",
            url="https://www.digital.go.jp/news",
            interval_hours=6,
            selector=None,
            exclude_selectors=(),
            exclude_patterns=(),
            diff_mode="lines",
            enabled=True,
        )
    ]


def test_all_fields_are_read() -> None:
    [target] = parse_targets(
        {
            "targets": [
                _target(
                    interval_hours=1,
                    selector="#mainContainer",
                    exclude_selectors=[".date"],
                    exclude_patterns=[r"\d{4}年\d+月\d+日"],
                    diff_mode="added_only",
                    enabled=False,
                )
            ]
        }
    )
    assert target.interval_hours == 1
    assert target.selector == "#mainContainer"
    assert target.exclude_selectors == (".date",)
    assert target.exclude_patterns == (r"\d{4}年\d+月\d+日",)
    assert target.diff_mode == "added_only"
    assert target.enabled is False


@pytest.mark.parametrize(
    "data",
    [None, [], {"targets": "x"}, {"other": []}],
)
def test_top_level_must_have_target_list(data: object) -> None:
    assert _errors(data) == ["最上位に targets(監視対象のリスト)が必要です"]


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"id": "Digital_News"}, "id は英小文字・数字・ハイフンで書いてください"),
        ({"name": " "}, "name が必要です"),
        ({"url": "http://www.digital.go.jp/news"}, "url は https で書いてください"),
        ({"url": "https://example.com/"}, "url のドメイン example.com は許可されていません"),
        ({"url": "https://www.digital.go.jp:8443/news"}, "url にユーザー名・パスワード・ポート"),
        ({"interval_hours": 0}, "interval_hours は 1 以上にしてください"),
        ({"interval_hours": True}, "interval_hours は整数で書いてください"),
        ({"interval_hours": "6"}, "interval_hours は整数で書いてください"),
        ({"selector": ""}, "selector は空でない文字列で書いてください"),
        ({"exclude_selectors": ".date"}, "exclude_selectors は空でない文字列のリスト"),
        ({"exclude_patterns": ["("]}, "exclude_patterns の正規表現が不正です"),
        ({"diff_mode": "words"}, "diff_mode は lines / added_only のどれか"),
        ({"enabled": "yes"}, "enabled は true / false で書いてください"),
        ({"intervals": 6}, "不明な項目: intervals"),
    ],
)
def test_invalid_field_is_reported(overrides: dict[str, Any], expected: str) -> None:
    [error] = _errors({"targets": [_target(**overrides)]})
    assert error.startswith("targets[0]")
    assert expected in error


def test_duplicate_id_is_reported() -> None:
    errors = _errors({"targets": [_target(), _target()]})
    assert errors == ["targets[1](digital-news): id が重複しています"]


def test_all_problems_are_reported_together() -> None:
    errors = _errors({"targets": [_target(interval_hours=0), "x", _target(id="b", name="")]})
    assert len(errors) == 3


def test_validate_config_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate-config", str(REPO_ROOT / "targets.yaml")]) == 0
    assert "監視対象 4 件" in capsys.readouterr().out

    broken = tmp_path / "targets.yaml"
    broken.write_text("targets:\n  - id: x\n", encoding="utf-8")
    assert main(["validate-config", str(broken)]) == 1
    assert "name が必要です" in capsys.readouterr().err
