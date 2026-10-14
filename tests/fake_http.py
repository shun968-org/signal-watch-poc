"""ネットワークに出ずに requests を動かすための偽の通信。"""

from __future__ import annotations

import io
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import requests
from requests.adapters import BaseAdapter
from requests.structures import CaseInsensitiveDict


@dataclass
class Reply:
    status: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)


Route = Reply | Exception | Callable[[requests.PreparedRequest], Reply]


class FakeAdapter(BaseAdapter):
    """URL ごとに決めた応答を返し、送られたリクエストを記録する。"""

    def __init__(self, routes: Mapping[str, Route]) -> None:
        super().__init__()
        self.routes = dict(routes)
        self.requests: list[requests.PreparedRequest] = []

    def send(  # type: ignore[override]  # 偽物なので送信オプションは受け取って捨てる
        self, request: requests.PreparedRequest, **kwargs: Any
    ) -> requests.Response:
        self.requests.append(request)
        assert request.url is not None
        route = self.routes.get(request.url, Reply(status=404))
        if isinstance(route, Exception):
            raise route
        reply = route(request) if callable(route) else route
        response = requests.Response()
        response.status_code = reply.status
        response.headers = CaseInsensitiveDict(reply.headers)
        response.raw = io.BytesIO(reply.body)
        response.url = request.url
        response.request = request
        return response

    def close(self) -> None:
        pass

    @property
    def urls(self) -> list[str | None]:
        return [r.url for r in self.requests]


def session_with(adapter: FakeAdapter) -> requests.Session:
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class FakeClock:
    """time.monotonic と time.sleep の代わり。sleep した分だけ時刻が進む。"""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
