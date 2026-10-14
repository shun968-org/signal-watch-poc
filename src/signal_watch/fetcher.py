"""監視対象ページの HTTP 取得(基本設計 F-03)。

robots.txt を確認し、同一ドメインへの間隔を空けて取得する。実行内では再試行しない
(失敗したら次の実行まで待つ。対象サイトに短い間隔で繰り返しアクセスしないため)。
"""

from __future__ import annotations

from dataclasses import dataclass
from email.message import Message
from urllib.parse import urljoin, urlsplit

import requests

from signal_watch import __version__
from signal_watch.politeness import MIN_INTERVAL_SECONDS, HostThrottle, RobotsRules

USER_AGENT = f"signal-watch-poc/{__version__} (+https://github.com/shun968-org/signal-watch-poc)"
TIMEOUT_SECONDS = 30
MAX_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 5


@dataclass(frozen=True)
class Validators:
    """条件付きリクエスト用の値(前回の応答の ETag / Last-Modified)。"""

    etag: str | None = None
    last_modified: str | None = None


@dataclass(frozen=True)
class Page:
    """取得したページ。"""

    url: str  # リダイレクト後の URL
    content: bytes
    encoding: str | None  # Content-Type の charset。無ければ None(HTML 側の宣言に任せる)
    validators: Validators


@dataclass(frozen=True)
class NotModified:
    """304 Not Modified。前回から変わっていない。"""


class FetchError(Exception):
    """取得に失敗した。メッセージが失敗理由(state・通知に残す)。"""


class Crawler:
    """robots.txt と間隔を守ってページを取得する。1回の実行で1つ作って使い回す。"""

    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        throttle: HostThrottle | None = None,
        min_interval: float = MIN_INTERVAL_SECONDS,
    ) -> None:
        self._session = session or requests.Session()
        self._session.headers["User-Agent"] = USER_AGENT
        self._throttle = throttle or HostThrottle()
        self._min_interval = min_interval
        self._robots: dict[str, RobotsRules] = {}

    def fetch(self, url: str, validators: Validators | None = None) -> Page | NotModified:
        headers = {"Accept": "text/html,application/xhtml+xml"}
        if validators and validators.etag:
            headers["If-None-Match"] = validators.etag
        if validators and validators.last_modified:
            headers["If-Modified-Since"] = validators.last_modified

        response = self._get(url, headers, check_robots=True)
        try:
            if response.status_code == 304:
                return NotModified()
            if response.status_code != 200:
                raise FetchError(f"HTTP {response.status_code}")
            content_type = response.headers.get("Content-Type", "")
            media_type, charset = _parse_content_type(content_type)
            if media_type not in ("text/html", "application/xhtml+xml"):
                raise FetchError(f"HTML ではない応答: {content_type or '(Content-Type なし)'}")
            return Page(
                url=response.url,
                content=_read_limited(response),
                encoding=charset,
                validators=Validators(
                    etag=response.headers.get("ETag"),
                    last_modified=response.headers.get("Last-Modified"),
                ),
            )
        finally:
            response.close()

    def _get(self, url: str, headers: dict[str, str], *, check_robots: bool) -> requests.Response:
        """リダイレクトを同一ホスト内に限って追いながら GET する。"""
        host = _https_host(url)
        for _ in range(MAX_REDIRECTS + 1):
            if check_robots and not self._rules(host).can_fetch(USER_AGENT, url):
                raise FetchError(f"robots.txt で禁止されている: {url}")
            response = self._request(host, url, headers)
            if not response.is_redirect:
                return response
            response.close()
            url = urljoin(url, response.headers["Location"])
            if _https_host(url) != host:
                raise FetchError(f"別のホストへのリダイレクト: {url}")
        raise FetchError(f"リダイレクトが {MAX_REDIRECTS} 回を超えた")

    def _request(self, host: str, url: str, headers: dict[str, str]) -> requests.Response:
        self._throttle.wait(host, self._interval(host))
        try:
            return self._session.get(
                url, headers=headers, timeout=TIMEOUT_SECONDS, allow_redirects=False, stream=True
            )
        except requests.Timeout as e:
            raise FetchError(f"タイムアウト({TIMEOUT_SECONDS} 秒): {url}") from e
        except requests.RequestException as e:
            raise FetchError(f"通信に失敗: {url}: {e.__class__.__name__}") from e

    def _interval(self, host: str) -> float:
        rules = self._robots.get(host)
        delay = rules.crawl_delay(USER_AGENT) if rules else None
        return max(self._min_interval, delay or 0.0)

    def _rules(self, host: str) -> RobotsRules:
        if host not in self._robots:
            self._robots[host] = self._load_robots(host)
        return self._robots[host]

    def _load_robots(self, host: str) -> RobotsRules:
        try:
            response = self._get(f"https://{host}/robots.txt", {}, check_robots=False)
        except FetchError:
            return RobotsRules.disallow_everything()
        try:
            if 400 <= response.status_code < 500:
                return RobotsRules.allow_everything()
            if response.status_code != 200:
                return RobotsRules.disallow_everything()
            text = _read_limited(response).decode("utf-8", errors="replace")
            return RobotsRules.from_text(text)
        except FetchError:
            return RobotsRules.disallow_everything()
        finally:
            response.close()


def _https_host(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise FetchError(f"https の URL ではない: {url}")
    return parts.hostname


def _parse_content_type(value: str) -> tuple[str, str | None]:
    message = Message()
    message["Content-Type"] = value
    charset = message.get_param("charset")
    return message.get_content_type(), charset if isinstance(charset, str) else None


def _read_limited(response: requests.Response) -> bytes:
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        size += len(chunk)
        if size > MAX_BYTES:
            raise FetchError(f"応答が大きすぎる({MAX_BYTES} バイト超)")
        chunks.append(chunk)
    return b"".join(chunks)
