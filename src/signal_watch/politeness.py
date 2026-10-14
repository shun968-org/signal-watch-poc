"""対象サイトへの配慮: robots.txt の判定と、同一ドメインへのアクセス間隔(基本設計 F-03)。"""

from __future__ import annotations

import time
from collections.abc import Callable
from urllib.robotparser import RobotFileParser

# 同一ドメインへのリクエストの最小間隔(秒)。robots.txt の Crawl-delay がこれより長ければそちらに従う
MIN_INTERVAL_SECONDS = 5.0


class RobotsRules:
    """1つのホストの robots.txt の規則。"""

    def __init__(self, parser: RobotFileParser | None, *, allow_all: bool) -> None:
        self._parser = parser
        self._allow_all = allow_all

    @classmethod
    def from_text(cls, text: str) -> RobotsRules:
        parser = RobotFileParser()
        parser.parse(text.splitlines())
        return cls(parser, allow_all=False)

    @classmethod
    def allow_everything(cls) -> RobotsRules:
        """robots.txt が無い(4xx)とき。RFC 9309 では全て許可とみなしてよい。"""
        return cls(None, allow_all=True)

    @classmethod
    def disallow_everything(cls) -> RobotsRules:
        """robots.txt を取得できない(5xx・通信失敗)とき。RFC 9309 では全て禁止とみなす。"""
        return cls(None, allow_all=False)

    def can_fetch(self, user_agent: str, url: str) -> bool:
        if self._parser is None:
            return self._allow_all
        return self._parser.can_fetch(user_agent, url)

    def crawl_delay(self, user_agent: str) -> float | None:
        if self._parser is None:
            return None
        delay = self._parser.crawl_delay(user_agent)
        return float(delay) if delay is not None else None


class HostThrottle:
    """ホストごとに、前回のリクエストから一定の間隔が空くまで待つ。"""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._clock = clock
        self._sleep = sleep
        self._last_request: dict[str, float] = {}

    def wait(self, host: str, interval: float) -> None:
        last = self._last_request.get(host)
        if last is not None:
            remaining = last + interval - self._clock()
            if remaining > 0:
                self._sleep(remaining)
        self._last_request[host] = self._clock()
