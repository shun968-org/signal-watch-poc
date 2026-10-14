import pytest
import requests

from signal_watch.fetcher import (
    MAX_BYTES,
    USER_AGENT,
    Crawler,
    FetchError,
    NotModified,
    Page,
    Validators,
)
from signal_watch.politeness import HostThrottle
from tests.fake_http import FakeAdapter, FakeClock, Reply, session_with

ROBOTS = "https://www.digital.go.jp/robots.txt"
NEWS = "https://www.digital.go.jp/news"
HTML = {"Content-Type": "text/html; charset=UTF-8"}


def _crawler(adapter: FakeAdapter, clock: FakeClock | None = None) -> Crawler:
    clock = clock or FakeClock()
    throttle = HostThrottle(clock=clock.clock, sleep=clock.sleep)
    return Crawler(session_with(adapter), throttle=throttle)


def _robots(text: str = "User-agent: *\nDisallow: /admin/\n") -> Reply:
    return Reply(body=text.encode())


def test_fetches_page_after_checking_robots() -> None:
    adapter = FakeAdapter(
        {
            ROBOTS: _robots(),
            NEWS: Reply(body=b"<html>news</html>", headers={**HTML, "ETag": '"abc"'}),
        }
    )
    result = _crawler(adapter).fetch(NEWS)

    assert result == Page(
        url=NEWS,
        content=b"<html>news</html>",
        encoding="UTF-8",
        validators=Validators(etag='"abc"', last_modified=None),
    )
    assert adapter.urls == [ROBOTS, NEWS]
    assert adapter.requests[1].headers["User-Agent"] == USER_AGENT


def test_robots_is_fetched_once_per_host() -> None:
    other = "https://www.digital.go.jp/policies"
    adapter = FakeAdapter(
        {ROBOTS: _robots(), NEWS: Reply(headers=HTML), other: Reply(headers=HTML)}
    )
    crawler = _crawler(adapter)
    crawler.fetch(NEWS)
    crawler.fetch(other)
    assert adapter.urls == [ROBOTS, NEWS, other]


def test_disallowed_url_is_not_requested() -> None:
    admin = "https://www.digital.go.jp/admin/x"
    adapter = FakeAdapter({ROBOTS: _robots(), admin: Reply(headers=HTML)})
    with pytest.raises(FetchError, match=r"robots\.txt で禁止"):
        _crawler(adapter).fetch(admin)
    assert adapter.urls == [ROBOTS]


def test_missing_robots_allows_everything() -> None:
    adapter = FakeAdapter({ROBOTS: Reply(status=404), NEWS: Reply(headers=HTML)})
    assert isinstance(_crawler(adapter).fetch(NEWS), Page)


@pytest.mark.parametrize(
    "robots_reply", [Reply(status=503), requests.ConnectionError("down")], ids=["5xx", "error"]
)
def test_unavailable_robots_disallows_everything(robots_reply: Reply | Exception) -> None:
    adapter = FakeAdapter({ROBOTS: robots_reply, NEWS: Reply(headers=HTML)})
    with pytest.raises(FetchError, match=r"robots\.txt で禁止"):
        _crawler(adapter).fetch(NEWS)
    assert NEWS not in adapter.urls


def test_waits_between_requests_to_same_host() -> None:
    other = "https://www.digital.go.jp/policies"
    adapter = FakeAdapter(
        {ROBOTS: _robots(), NEWS: Reply(headers=HTML), other: Reply(headers=HTML)}
    )
    clock = FakeClock()
    crawler = _crawler(adapter, clock)
    crawler.fetch(NEWS)
    crawler.fetch(other)
    # robots.txt → NEWS → other の間に 5 秒ずつ
    assert clock.sleeps == [5.0, 5.0]


def test_longer_crawl_delay_is_respected() -> None:
    adapter = FakeAdapter(
        {ROBOTS: _robots("User-agent: *\nCrawl-delay: 20\n"), NEWS: Reply(headers=HTML)}
    )
    clock = FakeClock()
    _crawler(adapter, clock).fetch(NEWS)
    assert clock.sleeps == [20.0]


def test_conditional_request_and_not_modified() -> None:
    adapter = FakeAdapter({ROBOTS: _robots(), NEWS: Reply(status=304)})
    validators = Validators(etag='"abc"', last_modified="Tue, 13 Oct 2026 00:00:00 GMT")
    assert _crawler(adapter).fetch(NEWS, validators) == NotModified()
    sent = adapter.requests[-1].headers
    assert sent["If-None-Match"] == '"abc"'
    assert sent["If-Modified-Since"] == "Tue, 13 Oct 2026 00:00:00 GMT"


def test_follows_redirect_within_same_host() -> None:
    moved = "https://www.digital.go.jp/news/"
    adapter = FakeAdapter(
        {
            ROBOTS: _robots(),
            NEWS: Reply(status=301, headers={"Location": "/news/"}),
            moved: Reply(headers=HTML),
        }
    )
    result = _crawler(adapter).fetch(NEWS)
    assert isinstance(result, Page)
    assert result.url == moved


def test_redirect_to_other_host_fails() -> None:
    adapter = FakeAdapter(
        {ROBOTS: _robots(), NEWS: Reply(status=302, headers={"Location": "https://example.com/"})}
    )
    with pytest.raises(FetchError, match="別のホスト"):
        _crawler(adapter).fetch(NEWS)
    assert "https://example.com/" not in adapter.urls


def test_redirect_loop_fails() -> None:
    adapter = FakeAdapter({ROBOTS: _robots(), NEWS: Reply(status=302, headers={"Location": NEWS})})
    with pytest.raises(FetchError, match="リダイレクトが 5 回"):
        _crawler(adapter).fetch(NEWS)


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        (Reply(status=500), "HTTP 500"),
        (Reply(status=404), "HTTP 404"),
        (Reply(headers={"Content-Type": "application/pdf"}), "HTML ではない"),
        (Reply(), "Content-Type なし"),
        (Reply(body=b"x" * (MAX_BYTES + 1), headers=HTML), "大きすぎる"),
        (requests.Timeout(), "タイムアウト"),
        (requests.ConnectionError(), "通信に失敗"),
    ],
)
def test_failures(reply: Reply | Exception, message: str) -> None:
    adapter = FakeAdapter({ROBOTS: _robots(), NEWS: reply})
    with pytest.raises(FetchError, match=message):
        _crawler(adapter).fetch(NEWS)
    # 実行内では再試行しない
    assert adapter.urls.count(NEWS) == 1


def test_non_https_url_fails() -> None:
    with pytest.raises(FetchError, match="https"):
        _crawler(FakeAdapter({})).fetch("http://www.digital.go.jp/news")
