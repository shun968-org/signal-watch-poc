"""取得した HTML から比較用のテキストを取り出す(基本設計 F-04)。

利用者にとって意味のある変化だけが差分に出るよう、比較範囲を切り出し、除外し、
ブロック要素ごとに1行のテキストへ正規化する。
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from signal_watch.config import Target

# 中身を比較に使わない要素
_REMOVED_TAGS = ("script", "style", "noscript", "iframe", "template", "svg", "button")

# 前後で改行するブロック要素(この単位で1行になる)
_BLOCK_TAGS = (
    "address",
    "article",
    "aside",
    "blockquote",
    "caption",
    "dd",
    "details",
    "div",
    "dl",
    "dt",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "summary",
    "table",
    "ul",
)

EXCLUDED_MARK = "<除外>"

# 改行・タブ以外の空白(全角空白・ノーブレークスペースを含む)の連続
_SPACES = re.compile(r"[^\S\n\t]+")


class ExtractError(Exception):
    """比較用のテキストを取り出せなかった(ページ構造の変化など)。"""


def extract_lines(html: bytes, *, encoding: str | None, url: str, target: Target) -> list[str]:
    """HTML から比較用のテキストを行のリストで返す。"""
    soup = BeautifulSoup(html, "html.parser", from_encoding=encoding)
    root = _select_root(soup, target.selector)

    for tag in root.find_all(_REMOVED_TAGS):
        if not tag.decomposed:  # 外側の要素と一緒に消えていることがある
            tag.decompose()
    for selector in target.exclude_selectors:
        for tag in root.select(selector):
            if not tag.decomposed:
                tag.decompose()

    _collapse_source_whitespace(root)
    _flatten_links(root, url)
    _flatten_table_rows(root)
    for br in root.find_all("br"):
        br.replace_with("\n")
    for li in root.find_all("li"):
        li.insert(0, "- ")
    for tag in root.find_all(_BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")

    lines = [_normalize(line) for line in root.get_text().split("\n")]
    lines = _join_bullets([line for line in lines if line.strip()])
    patterns = [re.compile(p) for p in target.exclude_patterns]
    lines = [_apply_patterns(line, patterns) for line in lines]
    if not lines:
        raise ExtractError("比較範囲のテキストが空")
    return lines


def _select_root(soup: BeautifulSoup, selector: str | None) -> Tag:
    if selector:
        found = soup.select_one(selector)
        if found is None:
            raise ExtractError(f"比較範囲が見つからない: {selector}")
        return found
    found = soup.find("main") or soup.find("body")
    if not isinstance(found, Tag):
        raise ExtractError("main・body 要素が見つからない")
    return found


def _collapse_source_whitespace(root: Tag) -> None:
    """HTML ソース中の改行・インデントを空白1つにする。

    行の区切りはブロック要素と br だけで決める。
    """
    for text in root.find_all(string=True):
        if not isinstance(text, NavigableString) or text.find_parent("pre"):
            continue
        collapsed = re.sub(r"\s+", " ", str(text))
        if collapsed != text:
            text.replace_with(collapsed)


def _flatten_links(root: Tag, base_url: str) -> None:
    """リンクを「テキスト <URL>」にする。リンク先の差し替えも差分に出すため。"""
    for a in root.find_all("a"):
        text = _inline(a.get_text(" "))
        href = a.get("href")
        target_url = _link_url(base_url, href) if isinstance(href, str) else None
        if target_url is None:
            a.replace_with(text)
        else:
            a.replace_with(f"{text} <{target_url}>" if text else f"<{target_url}>")


def _link_url(base_url: str, href: str) -> str | None:
    href = href.strip()
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
        return None
    absolute = urljoin(base_url, href)
    # 同じページ内のアンカー(フラグメントだけ違う)はリンク先として残さない
    if urlsplit(absolute)._replace(fragment="") == urlsplit(base_url)._replace(fragment=""):
        return None
    return absolute


def _flatten_table_rows(root: Tag) -> None:
    """表の行を、セルをタブで区切った1行にする。"""
    for tr in root.find_all("tr"):
        cells = [_inline(cell.get_text(" ")) for cell in tr.find_all(["th", "td"])]
        tr.replace_with(NavigableString("\n" + "\t".join(cells) + "\n"))


def _join_bullets(lines: list[str]) -> list[str]:
    """リスト項目の先頭がブロック要素のとき「-」だけの行ができるので、次の行とつなげる。"""
    joined: list[str] = []
    for line in lines:
        if joined and joined[-1] == "-":
            joined[-1] = f"- {line}"
        else:
            joined.append(line)
    return joined


def _normalize(text: str) -> str:
    """改行・タブは残し、それ以外の空白の連続を1つにする。"""
    text = unicodedata.normalize("NFC", text)
    return _SPACES.sub(" ", text).strip(" ")


def _inline(text: str) -> str:
    """改行も含めて空白の連続を1つにする(リンクや表のセルを1行に収めるため)。"""
    return " ".join(unicodedata.normalize("NFC", text).split())


def _apply_patterns(line: str, patterns: list[re.Pattern[str]]) -> str:
    for pattern in patterns:
        line = pattern.sub(EXCLUDED_MARK, line)
    return line
