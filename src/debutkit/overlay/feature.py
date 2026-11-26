"""오버레이 서버에 붙는 방송 연출 기능(뽑기판, 후원 벽, 참여 레이스 등)의 공통 틀.

기능 하나가 자기 화면(정적 파일), 조회(GET), 조작(POST), 실시간 항목(``/live?feeds=``), 채팅과 후원 사건 받기를
:class:`Feature` 하나로 묶어 서버에 등록한다. 서버(server.py)는 등록된 기능을 차례로 확인할 뿐 기능 내용을 모른다.

- 조회, 조작 함수는 JSON으로 보낼 값을 돌려준다. 그림처럼 JSON이 아닌 응답은 :class:`Raw`
- 잘못된 요청은 :class:`FeatureError` (한국어 안내, 기본 400). 저장 실패(OSError)는 서버가 500과 안내로 바꾼다
- 실시간 항목의 상태는 ``subscribe(into) -> (구독자, 현재 값)`` 과 ``unsubscribe(구독자)`` 를 가진 객체(:class:`Channel`)
- 모든 요청은 서버가 Host, Origin을 먼저 확인한다(이 PC 안의 화면만)
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any, Callable


class FeatureError(Exception):
    """잘못된 조작 요청. 메시지는 한국어 안내."""

    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = int(status)


@dataclass(frozen=True)
class Raw:
    """JSON이 아닌 응답(그림, SVG 등). ``policy`` 는 Content-Security-Policy."""

    body: bytes
    content_type: str
    policy: str = ""


Query = dict[str, list[str]]


@dataclass
class Feature:
    """서버에 등록하는 기능 하나. 주소는 다른 기능, 서버 기본 주소와 겹치면 안 된다(server.py가 시작할 때 확인)."""

    name: str
    #: 주소 -> static 폴더의 파일 이름(예: ``{"/pick": "pick.html"}``)
    static: dict[str, str] = field(default_factory=dict)
    #: 주소 -> 함수(주소 뒤 질의) -> JSON 값 또는 Raw
    get: dict[str, Callable[[Query], Any]] = field(default_factory=dict)
    #: 주소 -> 함수(요청 본문 JSON 객체) -> JSON 값
    post: dict[str, Callable[[dict[str, Any]], Any]] = field(default_factory=dict)
    #: ``/live?feeds=`` 이름 -> 상태(Channel 등). 이름은 다른 기능과 겹치면 안 된다
    feeds: dict[str, Any] = field(default_factory=dict)
    #: 허브의 모든 사건(채팅, 후원, 구독)을 받는 함수. 오래 걸리면 안 된다
    taps: list[Callable[[Any], None]] = field(default_factory=list)
    #: 요청 본문 최대 크기(기본 4096 바이트). 그림을 받는 주소는 크게
    body_limit: dict[str, int] = field(default_factory=dict)
    #: 서버를 멈출 때 부르는 정리 함수
    stop: Callable[[], None] | None = None


@dataclass
class Context:
    """기능을 만들 때 받는 서버 부품. ``notify`` 는 채팅창에 보이는 debutkit 안내(시스템 메시지)."""

    notify: Callable[[str], None]
    publish: Callable[[Any], None] = lambda event: None  # 허브에 사건 보내기(시험 후원 등)
    raffle: Any = None  # raffle.Raffle(시청자 참여 추첨의 참가자 명단)
    draw: Any = None  # draw.DrawState
    tracking: Any = None  # tracking.TrackingState(얼굴 추적 값)
    port_of: Callable[[], int] = lambda: 8790


class Channel:
    """``/live`` 로 화면들에게 새 값을 나눠 주는 상태 하나. 새로 연결한 화면은 마지막 값부터 받는다.

    멈춘 화면(가득 찬 대기열) 때문에 서버가 막히지 않도록 넣지 못한 값은 버린다.
    """

    def __init__(self, current: dict[str, Any] | None = None, size: int = 100) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[Any] = []
        self._size = size
        self.current: dict[str, Any] = current if current is not None else {"seq": 0}

    def publish(self, value: dict[str, Any], *, keep: bool = True) -> None:
        """``keep`` 이 False면 새로 연결한 화면에는 보내지 않는 일회성 값(연출 신호 등)."""
        with self._lock:
            if keep:
                self.current = value
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(value)
            except Exception:  # 가득 찬 대기열(멈춘 화면)
                pass

    def subscribe(self, into: Any = None) -> tuple[Any, dict[str, Any]]:
        subscriber = into if into is not None else queue.Queue(maxsize=self._size)
        with self._lock:
            self._subscribers.append(subscriber)
            return subscriber, dict(self.current)

    def unsubscribe(self, subscriber: Any) -> None:
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)

    @property
    def listeners(self) -> int:
        with self._lock:
            return len(self._subscribers)


def default_features(context: Context) -> list[Feature]:
    """오버레이 서버가 기본으로 켜는 기능들. 기능을 추가하면 여기에 한 줄 더한다."""
    from .. import wall
    from ..pick import pick_feature
    from ..race import feature as race_feature
    from . import alerts, community, games, stage, theme, vmc

    theme_part, alerts_part = theme.make_feature(context), alerts.make_feature(context)
    found: list[Feature] = [theme_part, alerts_part, games.make_feature(context, theme_part, alerts_part), stage.make_feature(context),
                            vmc.make_feature(context)]
    found.append(wall.feature(context))  # 후원 벽, 목표 게이지, 후원 순위
    found.append(pick_feature(context))  # 뽑기판
    found.append(race_feature(context))  # 참여 레이스
    found.append(community.make_feature(context))  # 팬 커뮤니티 연동(올린 경우만 주고받음)
    return found
