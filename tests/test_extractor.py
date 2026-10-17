import pytest

from signal_watch.config import Target
from signal_watch.extractor import EXCLUDED_MARK, ExtractError, extract_lines

URL = "https://www.digital.go.jp/policies/example"


def _target(**overrides: object) -> Target:
    fields: dict[str, object] = {"id": "example", "name": "例", "url": URL}
    fields.update(overrides)
    return Target(**fields)  # type: ignore[arg-type]


def _extract(body: str, **overrides: object) -> list[str]:
    html = f"<html><head><title>t</title></head><body>{body}</body></html>"
    return extract_lines(html.encode(), encoding="utf-8", url=URL, target=_target(**overrides))


def test_blocks_become_lines_and_source_whitespace_is_ignored() -> None:
    body = """
    <main>
      <h1>見出し</h1>
      <p>一行目の
         続き<br>改行の後</p>
      <div>ブロック　　全角空白</div>
    </main>
    """
    assert _extract(body) == ["見出し", "一行目の 続き", "改行の後", "ブロック 全角空白"]


def test_default_root_is_main_then_body() -> None:
    assert _extract("<nav>ナビ</nav><main><p>本文</p></main>") == ["本文"]
    assert _extract("<p>本文だけ</p>") == ["本文だけ"]


def test_selector_and_exclusions() -> None:
    body = """
    <main id="mainContainer">
      <nav class="breadcrumbs">ホーム</nav>
      <article><h1>題</h1><div class="feedbackForm">ご意見</div><p>本文 2026年10月13日</p></article>
      <script>var x = 1;</script>
    </main>
    """
    lines = _extract(
        body,
        selector="#mainContainer article",
        exclude_selectors=(".feedbackForm",),
        exclude_patterns=(r"\d{4}年\d{1,2}月\d{1,2}日",),
    )
    assert lines == ["題", f"本文 {EXCLUDED_MARK}"]


def test_links_keep_text_and_absolute_url() -> None:
    body = """
    <main>
      <ul>
        <li><a class="card" href="/news/1">
          <div><p>お知らせ</p><time>2026年10月16日</time></div>
        </a></li>
        <li><a href="#top">ページ先頭へ</a></li>
        <li><a href="https://docs.example.org/x">外部</a></li>
      </ul>
    </main>
    """
    assert _extract(body) == [
        "- お知らせ 2026年10月16日 <https://www.digital.go.jp/news/1>",
        "- ページ先頭へ",
        "- 外部 <https://docs.example.org/x>",
    ]


def test_nested_list_items_start_with_bullet() -> None:
    body = "<main><ul><li><p>親</p><ul><li>子</li></ul></li></ul></main>"
    assert _extract(body) == ["- 親", "- 子"]


def test_table_rows_are_tab_separated() -> None:
    body = """
    <main><table>
      <tr><th>名前</th><th>区分</th></tr>
      <tr><td>A 銀行</td><td>
          対象外</td></tr>
    </table></main>
    """
    assert _extract(body) == ["名前\t区分", "A 銀行\t対象外"]


def test_missing_selector_fails() -> None:
    with pytest.raises(ExtractError, match="比較範囲が見つからない"):
        _extract("<main><p>本文</p></main>", selector="#nope")


def test_empty_result_fails() -> None:
    with pytest.raises(ExtractError, match="空"):
        _extract("<main><script>x</script></main>")


def test_encoding_from_header_is_used() -> None:
    html = "<html><body><main><p>日本語</p></main></body></html>".encode("shift_jis")
    lines = extract_lines(html, encoding="shift_jis", url=URL, target=_target())
    assert lines == ["日本語"]
