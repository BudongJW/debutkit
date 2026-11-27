"""시청자 참여 추첨: 채팅 명령(기본 ``!참가``)이나 후원으로 참가자를 모은 뒤 당첨자를 뽑거나 순서를 정한다.

- 모집은 조작 화면(``/draw/control``), 명령줄(``debutkit raffle``), 스트리머와 매니저의 채팅 명령(``!모집``, ``!마감``, ``!추첨 3``)으로 연다
- 모집 중 참가 명령을 입력한 시청자(플랫폼과 닉네임 기준 1번)가 참가. 후원 참가(선택)는 최소 금액 이상 후원한 시청자 자동 참가
  (원 기준, 별풍선 1개 100원, VTube Studio 후원 반응과 같은 환산)
- 추첨은 운영체제 난수(``random.SystemRandom``). 결과는 방송 화면(``/draw``)에 카드나 순서표로 표시
- 참가자 명단은 메모리에만 둔다(파일 저장 안 함). 모집을 새로 시작하면 지난 명단은 지운다
"""

from __future__ import annotations

import queue
import random
import threading
import time
from dataclasses import asdict, dataclass, replace
from typing import Any

from . import settings
from .vts import WON_PER_UNIT

DEFAULT_KEYWORD = "!참가"
DEFAULT_TITLE = "시청자 추첨"
MAX_ENTRIES = 1000
MAX_WINNERS = 30
MAX_TITLE = 20
#: 후원 참가자의 한마디: 후원 뒤 이 시간(초) 안에 처음 쓴 채팅(명령 빼고), 최대 글자 수
COMMENT_WAIT = 300
MAX_COMMENT = 40
MODES = {"pick": "당첨자 뽑기", "order": "순서 정하기"}


class RaffleError(ValueError):
    """잘못된 모집, 추첨 요청. 메시지는 한국어 안내."""


@dataclass(frozen=True)
class Entry:
    name: str
    platform: str
    source: str  # chat, donation, manual
    time: float
    comment: str = ""  # 후원 참가자가 후원 뒤 처음 쓴 채팅(레이스 당첨 화면)

    @property
    def key(self) -> str:
        return f"{self.platform}:{self.name}"


def check_keyword(keyword: Any) -> str:
    keyword = str(keyword or "").strip()
    if not keyword.startswith("!") or not 2 <= len(keyword) <= 20 or any(ch.isspace() for ch in keyword):
        raise RaffleError("참가 명령은 !로 시작하고 띄어쓰기 없는 20자 이내(예: !참가)")
    return keyword


def saved_options(saved: dict[str, Any] | None = None) -> dict[str, Any]:
    """저장한 모집 설정(참가 명령, 추첨 이름, 후원 참가 최소 금액). 다음 방송에도 같은 설정으로 시작."""
    saved = settings.load() if saved is None else saved
    try:
        keyword = check_keyword(saved.get("raffle_command", DEFAULT_KEYWORD))
    except RaffleError:
        keyword = DEFAULT_KEYWORD
    title = str(saved.get("raffle_title") or "").strip()[:MAX_TITLE] or DEFAULT_TITLE
    minimum = saved.get("raffle_donation_min")
    return {"keyword": keyword, "title": title, "donation_min": minimum if isinstance(minimum, int) and minimum >= 0 else None}


class Raffle:
    """참가자 명단과 모집 상태. 상태가 바뀌면 화면들에게 보내고, 추첨 결과는 결과로 한 번만 보낸다."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[Any] = []
        self._entries: dict[str, Entry] = {}
        self._awaiting: dict[str, float] = {}  # 한마디를 기다리는 후원 참가자: 키 -> 마감 시각
        self._rng = rng or random.SystemRandom()
        self._seq = 0
        options = saved_options()
        self.open = False
        self.keyword: str = options["keyword"]
        self.title: str = options["title"]
        self.donation_min: int | None = options["donation_min"]
        self.last_result: dict[str, Any] | None = None
        self.current: dict[str, Any] = self._status_event()

    # ------------------------------------------------------------------ 상태
    def _status_event(self, joined: Entry | None = None) -> dict[str, Any]:
        self._seq += 1
        event: dict[str, Any] = {"type": "status", "seq": self._seq, "time": round(time.time(), 3), "open": self.open, "keyword": self.keyword,
                                 "title": self.title, "donation_min": self.donation_min, "count": len(self._entries)}
        if joined is not None:
            event["joined"] = {"name": joined.name, "platform": joined.platform, "source": joined.source}
        return event

    def _send(self, event: dict[str, Any], *, status: bool) -> None:
        if status:
            self.current = event
        for subscriber in list(self._subscribers):
            try:
                subscriber.put_nowait(event)
            except Exception:  # 가득 찬 대기열(멈춘 화면)
                pass

    def status(self) -> dict[str, Any]:
        """조작 화면용: 모집 상태와 명단(먼저 참가한 순서)."""
        with self._lock:
            return {"open": self.open, "keyword": self.keyword, "title": self.title, "donation_min": self.donation_min,
                    "count": len(self._entries), "entries": [{**asdict(entry), "key": entry.key} for entry in self._entries.values()],
                    "last_result": self.last_result, "modes": MODES}

    # ------------------------------------------------------------------ 모집
    def start(self, keyword: Any = None, title: Any = None, donation_min: Any = "keep") -> dict[str, Any]:
        """새 모집 시작(지난 명단 삭제). 값을 주지 않은 항목은 이전 설정 유지. 설정은 저장해 다음 방송에도 사용."""
        keyword = check_keyword(keyword if keyword is not None else self.keyword)
        title = str(title if title is not None else self.title).strip() or DEFAULT_TITLE
        if len(title) > MAX_TITLE:
            raise RaffleError(f"추첨 이름은 {MAX_TITLE}자 이내")
        if donation_min == "keep":
            minimum = self.donation_min
        elif donation_min in (None, ""):
            minimum = None
        elif isinstance(donation_min, bool) or not isinstance(donation_min, (int, float)) or donation_min < 0 or donation_min != int(donation_min):
            raise RaffleError("후원 참가 최소 금액은 0 이상의 정수(원). 사용하지 않으면 비워 두기")
        else:
            minimum = int(donation_min)
        with self._lock:
            self.keyword, self.title, self.donation_min, self.open = keyword, title, minimum, True
            self._entries.clear()
            event = self._status_event()
            self._send(event, status=True)
        saved = settings.load()
        saved.update(raffle_command=keyword, raffle_title=title)
        if minimum is None:
            saved.pop("raffle_donation_min", None)
        else:
            saved["raffle_donation_min"] = minimum
        settings.save(saved)
        return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self.open = False
            self._send(self._status_event(), status=True)
        return self.status()

    def clear(self) -> dict[str, Any]:
        with self._lock:
            self._entries.clear()
            self._awaiting.clear()
            self.last_result = None
            self._send(self._status_event(), status=True)
        return self.status()

    def add(self, name: str, platform: str, source: str = "manual") -> bool:
        """참가. 이미 참가했거나 이름이 비었거나 명단이 가득 차면 False. 직접 추가(manual)는 모집 중이 아니어도 가능."""
        name = str(name or "").strip()[:40]
        if not name:
            return False
        entry = Entry(name, platform or "manual", source, round(time.time(), 3))
        with self._lock:
            if (source != "manual" and not self.open) or entry.key in self._entries or len(self._entries) >= MAX_ENTRIES:
                return False
            self._entries[entry.key] = entry
            if source == "donation":
                self._awaiting[entry.key] = time.time() + COMMENT_WAIT
            self._send(self._status_event(entry), status=True)
        return True

    def comment(self, name: str, platform: str, text: str) -> bool:
        """후원으로 참가한 시청자가 후원 뒤 처음 쓴 채팅을 한마디로(명령, 빈 글은 넘김). 넣었으면 True."""
        text = " ".join(str(text or "").split())[:MAX_COMMENT]
        key = f"{platform or 'manual'}:{str(name or '').strip()[:40]}"
        if not text or text.startswith("!"):
            return False
        with self._lock:
            deadline = self._awaiting.get(key)
            if deadline is None or key not in self._entries:
                return False
            del self._awaiting[key]
            if time.time() > deadline:
                return False
            self._entries[key] = replace(self._entries[key], comment=text)
            self._send(self._status_event(), status=True)
        return True

    def remove(self, key: str) -> bool:
        with self._lock:
            if self._entries.pop(str(key), None) is None:
                return False
            self._send(self._status_event(), status=True)
        return True

    # ------------------------------------------------------------------ 추첨
    def draw(self, count: Any = 1, mode: str = "pick") -> dict[str, Any]:
        """당첨자 뽑기(count명) 또는 순서 정하기(전체를 섞어 앞에서 최대 30명 표시). 모집 중이면 마감 후 추첨."""
        if mode not in MODES:
            raise RaffleError("추첨 방식은 pick(당첨자 뽑기) 또는 order(순서 정하기)")
        if mode == "pick" and (isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_WINNERS):
            raise RaffleError(f"당첨 인원은 1에서 {MAX_WINNERS} 사이의 정수")
        with self._lock:
            entries = list(self._entries.values())
            if not entries:
                raise RaffleError("참가자가 없음: 모집을 시작하고 채팅에 참가 명령이 들어온 뒤 추첨")
            if self.open:  # 모집 중이면 먼저 마감 상태를 보낸 뒤 결과
                self.open = False
                self._send(self._status_event(), status=True)
            if mode == "pick":
                chosen = self._rng.sample(entries, min(count, len(entries)))
            else:
                chosen = entries[:]
                self._rng.shuffle(chosen)
            self._seq += 1
            result = {"type": "result", "seq": self._seq, "time": round(time.time(), 3), "mode": mode, "title": self.title, "total": len(entries),
                      "winners": [{"name": entry.name, "platform": entry.platform, "source": entry.source} for entry in chosen[:MAX_WINNERS]]}
            if mode == "order":
                result["more"] = max(0, len(chosen) - MAX_WINNERS)
            self.last_result = result
            self._send(result, status=False)
        return result

    # ------------------------------------------------------------------ 구독(/live의 raffle)
    def subscribe(self, into: Any = None) -> tuple[Any, dict[str, Any]]:
        subscriber = into if into is not None else queue.Queue(maxsize=200)
        with self._lock:
            self._subscribers.append(subscriber)
            return subscriber, dict(self.current)

    def unsubscribe(self, subscriber: Any) -> None:
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)


def matches(text: str, keyword: str) -> bool:
    """채팅 첫 단어가 참가 명령인지(영문 대소문자 무시)."""
    first = text.strip().split(maxsplit=1)[0] if text.strip() else ""
    return first.casefold() == keyword.casefold()


class RaffleReactor:
    """오버레이 허브에 붙여 모집 중 참가 명령 채팅과 조건에 맞는 후원을 명단에 넣는다."""

    def __init__(self, raffle: Raffle) -> None:
        self.raffle = raffle

    def __call__(self, event: Any) -> None:
        raffle = self.raffle
        platform = str(getattr(event, "platform", ""))
        if platform == "system":
            return
        kind = getattr(event, "kind", "")
        name = str(getattr(event, "name", ""))
        text = str(getattr(event, "text", ""))
        if kind == "chat" and not (raffle.open and matches(text, raffle.keyword)):
            raffle.comment(name, platform, text)  # 후원 참가자의 한마디(모집을 마감한 뒤에도 기다리는 동안은)
            return
        if not raffle.open:
            return
        if kind == "chat":
            raffle.add(name, platform, "chat")
        elif kind == "donation" and raffle.donation_min is not None:
            rate = WON_PER_UNIT.get(str(getattr(event, "unit", "") or ""))
            amount = float(getattr(event, "amount", 0) or 0)
            if raffle.donation_min == 0 or (rate is not None and amount * rate >= raffle.donation_min):
                raffle.add(name, platform, "donation")
