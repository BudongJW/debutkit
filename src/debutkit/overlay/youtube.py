"""YouTube 라이브 채팅: 공식 YouTube Data API(liveChatMessages.list)를 API 키로 읽는다.

- 필요: Google Cloud 프로젝트에서 YouTube Data API v3 사용 설정, API 키 발급
- 할당량: 기본 하루 10,000 단위. 채팅 요청 1회 5 단위, 방송 확인(videos.list) 1회 1 단위
- 요청 간격: YouTube가 알려 주는 간격(pollingIntervalMillis)과 ``interval`` 중 긴 쪽.
  기본 10초면 1시간에 약 1,800 단위, 기본 할당량으로 약 5시간
- API 키는 요청 머리글(X-Goog-Api-Key)로만 보내고 저장하지 않는다

이 모듈의 변환 함수(:func:`video_id`, :func:`youtube_event`)는 네트워크 없이 테스트할 수 있다.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Callable

from .events import OverlayEvent

API = "https://www.googleapis.com/youtube/v3"
DEFAULT_INTERVAL = 10.0
MIN_INTERVAL = 5.0
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

#: API 오류 이유(reason)와 한국어 안내
_REASONS = {
    "quotaExceeded": "YouTube API 하루 할당량 초과(태평양 시간 자정 초기화). --youtube-interval 을 늘리거나 할당량 증설 신청",
    "dailyLimitExceeded": "YouTube API 하루 할당량 초과(태평양 시간 자정 초기화)",
    "rateLimitExceeded": "요청 간격이 너무 짧음. --youtube-interval 을 늘리기",
    "keyInvalid": "API 키 확인 필요(잘못된 키)",
    "accessNotConfigured": "Google Cloud 프로젝트에서 YouTube Data API v3 사용 설정 필요",
    "liveChatEnded": "라이브 채팅 종료",
    "liveChatNotFound": "라이브 채팅을 찾지 못함",
    "liveChatDisabled": "이 방송은 라이브 채팅이 꺼져 있음",
    "forbidden": "이 라이브 채팅을 읽을 권한 없음",
}


def video_id(address: str) -> str:
    """방송 주소나 영상 ID에서 11자리 영상 ID. 채널 주소는 지원하지 않는다(방송마다 영상 ID가 바뀜)."""
    text = address.strip()
    if _VIDEO_ID.match(text):
        return text
    parts = urllib.parse.urlsplit(text if "://" in text else "https://" + text)
    host = (parts.hostname or "").lower()
    candidate = ""
    if host.endswith("youtu.be"):
        candidate = parts.path.strip("/").split("/")[0]
    elif host.endswith("youtube.com"):
        query = urllib.parse.parse_qs(parts.query)
        if query.get("v"):
            candidate = query["v"][0]
        else:
            segments = [segment for segment in parts.path.split("/") if segment]
            if len(segments) >= 2 and segments[0] in ("live", "shorts", "embed"):
                candidate = segments[1]
    if not _VIDEO_ID.match(candidate):
        raise ValueError("YouTube 방송 주소 또는 영상 ID 필요(예: https://www.youtube.com/watch?v=영상ID). 채널 주소는 지원 안 함")
    return candidate


def _stamp(value: Any) -> float:
    text = str(value or "")
    match = re.match(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)?$", text)
    if not match:
        return time.time()
    zone = match.group(3) or "+00:00"
    fraction = (match.group(2) or "0")[:6].ljust(6, "0")
    try:
        return datetime.fromisoformat(f"{match.group(1)}.{fraction}{'+00:00' if zone == 'Z' else zone}").timestamp()
    except ValueError:
        return time.time()


def youtube_event(item: dict[str, Any]) -> OverlayEvent | None:
    """liveChatMessage 하나. 채팅, 슈퍼챗, 슈퍼스티커, 멤버십(가입, 기념일, 선물)만."""
    snippet = item.get("snippet") or {}
    author = item.get("authorDetails") or {}
    kind = snippet.get("type")
    name = str(author.get("displayName") or "익명")
    role = "owner" if author.get("isChatOwner") else "moderator" if author.get("isChatModerator") else ""
    stamp = _stamp(snippet.get("publishedAt"))
    if kind == "textMessageEvent":
        text = str((snippet.get("textMessageDetails") or {}).get("messageText") or snippet.get("displayMessage") or "")
        return OverlayEvent("youtube", "chat", name, (("text", text),), role=role, time=stamp)
    if kind in ("superChatEvent", "superStickerEvent"):
        details = snippet.get("superChatDetails") or snippet.get("superStickerDetails") or {}
        try:
            amount = float(details.get("amountMicros") or 0) / 1_000_000
        except (TypeError, ValueError):
            amount = 0.0
        currency = str(details.get("currency") or "")
        comment = str(details.get("userComment") or "")
        return OverlayEvent("youtube", "donation", name, (("text", comment),) if comment else (), amount=amount,
                            unit="원" if currency == "KRW" else currency, role=role, time=stamp)
    if kind == "newSponsorEvent":
        level = str((snippet.get("newSponsorDetails") or {}).get("memberLevelName") or "")
        return OverlayEvent("youtube", "member", name, (("text", "멤버십 가입" + (f" ({level})" if level else "")),), role=role, time=stamp)
    if kind == "memberMilestoneChatEvent":
        details = snippet.get("memberMilestoneChatDetails") or {}
        months = details.get("memberMonth")
        comment = str(details.get("userComment") or "")
        notice = f"멤버십 {months}개월" if months else "멤버십 기념일"
        return OverlayEvent("youtube", "member", name, (("text", notice + (f" {comment}" if comment else "")),), role=role, time=stamp)
    if kind == "membershipGiftingEvent":
        count = (snippet.get("membershipGiftingDetails") or {}).get("giftMembershipsCount")
        return OverlayEvent("youtube", "member", name, (("text", f"멤버십 선물 {count}개" if count else "멤버십 선물"),), role=role, time=stamp)
    return None


def _error(status: int, body: bytes) -> str:
    try:
        error = json.loads(body or b"{}").get("error") or {}
    except (ValueError, AttributeError):
        error = {}
    reasons = [str(item.get("reason") or "") for item in error.get("errors") or [] if isinstance(item, dict)]
    message = str(error.get("message") or "")
    for reason in reasons:
        if reason in _REASONS:
            return _REASONS[reason]
    if "API key not valid" in message:
        return _REASONS["keyInvalid"]
    return f"YouTube API 오류 {status}" + (f": {message}" if message else "")


def _get(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - 고정 https 주소
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


class YouTubeLiveChat:
    """오버레이 수신기. ``read()`` 는 요청 간격이 지났을 때만 YouTube에 묻고, 아니면 빈 목록을 바로 돌려준다."""

    def __init__(self, address: str, api_key: str | None = None, *, interval: float = DEFAULT_INTERVAL,
                 send: Callable[[str, dict[str, str]], tuple[int, bytes]] | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.video = video_id(address)
        self.api_key = api_key or os.environ.get("YOUTUBE_API_KEY", "")
        if not self.api_key:
            raise ValueError("YouTube API 키 필요: --youtube-key 또는 환경 변수 YOUTUBE_API_KEY (Google Cloud에서 YouTube Data API v3 사용 설정 후 발급)")
        self.interval = max(MIN_INTERVAL, float(interval))
        self.ended = False
        self._send = send or _get
        self._clock = clock
        self._chat_id: str | None = None
        self._page: str | None = None
        self._next = 0.0
        self._first = True

    def _call(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        status, body = self._send(f"{API}/{path}?{urllib.parse.urlencode(params)}", {"X-Goog-Api-Key": self.api_key, "Accept": "application/json"})
        if status != 200:
            raise RuntimeError(_error(status, body))
        data = json.loads(body or b"{}")
        return data if isinstance(data, dict) else {}

    def _chat(self) -> str:
        items = self._call("videos", {"part": "liveStreamingDetails", "id": self.video}).get("items") or []
        if not items:
            raise RuntimeError(f"YouTube 영상을 찾지 못함: {self.video}")
        chat = (items[0].get("liveStreamingDetails") or {}).get("activeLiveChatId")
        if not chat:
            raise RuntimeError("라이브 채팅 없음: 방송 중이 아니거나 채팅이 꺼져 있음")
        return str(chat)

    def read(self) -> list[OverlayEvent]:
        if self.ended or self._clock() < self._next:
            return []
        self._next = self._clock() + self.interval  # 실패해도 간격을 지킨다
        if self._chat_id is None:
            self._chat_id = self._chat()
        params: dict[str, Any] = {"liveChatId": self._chat_id, "part": "snippet,authorDetails", "maxResults": 2000, "hl": "ko"}
        if self._page:
            params["pageToken"] = self._page
        data = self._call("liveChat/messages", params)
        self._page = str(data.get("nextPageToken") or self._page or "") or None
        wait = float(data.get("pollingIntervalMillis") or 0) / 1000
        self._next = self._clock() + max(wait, self.interval)
        if data.get("offlineAt"):
            self.ended = True
        events = [event for event in (youtube_event(item) for item in data.get("items") or [] if isinstance(item, dict)) if event is not None]
        if self._first:  # 첫 응답은 이미 지난 채팅: 알림이 다시 뜨지 않게 버린다
            self._first = False
            return []
        return events

    def close(self) -> None:
        self.ended = True


def youtube_source(address: str, api_key: str | None = None, interval: float = DEFAULT_INTERVAL) -> YouTubeLiveChat:
    return YouTubeLiveChat(address, api_key, interval=interval)
