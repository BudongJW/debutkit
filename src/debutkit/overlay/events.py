"""오버레이에 띄울 사건(채팅, 후원)과 플랫폼별 변환.

채팅 연결 모듈의 수신기는 분석용이라 작성자를 해시로만 남긴다. 오버레이는 닉네임과
이모티콘이 필요하므로 연결, 토큰, 재접속은 그 수신기를 그대로 쓰고 받은 원본 프레임만
여기서 화면용 :class:`OverlayEvent` 로 바꾼다. 이 모듈의 변환 함수는 네트워크 없이
테스트할 수 있는 순수 함수다.

오버레이는 받은 채팅을 저장하지 않는다(메모리의 최근 몇십 개만 유지).
"""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

_CHZZK_EMOJI = re.compile(r"\{:([^:{}]+):\}")
_SOOP_SESSION = re.compile(r"\(\d+\)$")
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


@dataclass(frozen=True)
class OverlayEvent:
    platform: str  # chzzk | soop | twitch | demo | system
    kind: str  # chat | donation | member | system
    name: str
    parts: tuple[tuple[str, str], ...] = ()  # ("text", 글) 또는 ("emote", https 주소)
    amount: float = 0.0
    unit: str = ""  # 원 | 별풍선 | bits
    role: str = ""  # owner | moderator | ""
    color: str = ""  # 닉네임 색 #RRGGBB (플랫폼이 줄 때만)
    time: float = field(default_factory=time.time)

    @property
    def text(self) -> str:
        return "".join(value if kind == "text" else "" for kind, value in self.parts)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["parts"] = [{"type": kind, "value": value} for kind, value in self.parts]
        return data


def text_parts(text: str, emotes: dict[str, str] | None = None, pattern: re.Pattern[str] = _CHZZK_EMOJI) -> tuple[tuple[str, str], ...]:
    """글 속 이모티콘 자리(``{:이름:}``)를 그림 주소로 나눈다. https 주소만 그림으로 쓴다."""
    emotes = emotes or {}
    parts: list[tuple[str, str]] = []
    position = 0
    for found in pattern.finditer(text):
        url = str(emotes.get(found.group(1), ""))
        if not url.startswith("https://"):
            continue
        if found.start() > position:
            parts.append(("text", text[position:found.start()]))
        parts.append(("emote", url))
        position = found.end()
    if position < len(text):
        parts.append(("text", text[position:]))
    return tuple(parts)


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        loaded = json.loads(value) if isinstance(value, str) and value else {}
    except ValueError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


# --------------------------------------------------------------------------- CHZZK


def chzzk_event(item: dict[str, Any], *, donation: bool = False) -> OverlayEvent | None:
    """CHZZK 라이브 채팅 프레임(cmd 93101 채팅, 93102 후원)의 ``bdy`` 항목 하나."""
    if item.get("msgStatusType", "NORMAL") != "NORMAL":
        return None  # 가려진 메시지
    profile = _json_object(item.get("profile"))
    extras = _json_object(item.get("extras"))
    amount = float(extras.get("payAmount") or 0)
    paid = donation or item.get("msgTypeCode") == 10 or amount > 0
    name = str(profile.get("nickname") or ("익명 후원자" if paid else "익명"))
    role_code = str(profile.get("userRoleCode") or "")
    role = "owner" if role_code == "streamer" else "moderator" if role_code in ("streaming_channel_manager", "streaming_chat_manager") else ""
    stamp = item.get("msgTime") or item.get("ctime")
    return OverlayEvent(
        "chzzk", "donation" if paid else "chat", name, text_parts(str(item.get("msg") or ""), _json_object(extras.get("emojis"))),
        amount=amount, unit="원" if paid else "", role=role, time=float(stamp) / 1000 if stamp else time.time(),
    )


def chzzk_frame(frame: Any) -> list[OverlayEvent]:
    try:
        data = json.loads(frame)
    except (TypeError, ValueError):
        return []
    command = data.get("cmd") if isinstance(data, dict) else None
    if command not in (93101, 93102) or not isinstance(data.get("bdy"), list):
        return []
    events = (chzzk_event(item, donation=command == 93102) for item in data["bdy"] if isinstance(item, dict))
    return [event for event in events if event is not None]


def chzzk_api_event(name: str, data: dict[str, Any]) -> OverlayEvent | None:
    """CHZZK 공식 Open API 세션 이벤트(``CHAT`` / ``DONATION`` / ``SUBSCRIPTION``) 하나. 내 채널 전용, 로그인 필요."""
    if name == "CHAT":
        profile = _json_object(data.get("profile"))
        role_code = str(profile.get("userRoleCode") or data.get("userRoleCode") or "")
        role = "owner" if role_code == "streamer" else "moderator" if "manager" in role_code else ""
        stamp = data.get("messageTime")
        return OverlayEvent("chzzk", "chat", str(profile.get("nickname") or "익명"),
                            text_parts(str(data.get("content") or ""), _json_object(data.get("emojis"))), role=role,
                            time=float(stamp) / 1000 if isinstance(stamp, (int, float)) else time.time())
    if name == "DONATION":
        try:
            amount = float(str(data.get("payAmount") or "0").replace(",", ""))
        except ValueError:
            amount = 0.0
        return OverlayEvent("chzzk", "donation", str(data.get("donatorNickname") or "익명 후원자"),
                            text_parts(str(data.get("donationText") or ""), _json_object(data.get("emojis"))), amount=amount, unit="원")
    if name == "SUBSCRIPTION":
        month = data.get("month")
        notice = f"{month}개월 구독" if month else "구독"
        return OverlayEvent("chzzk", "member", str(data.get("subscriberNickname") or "구독자"), (("text", notice),))
    return None


# --------------------------------------------------------------------------- SOOP


def soop_event(packet: bytes, streamer: str = "") -> OverlayEvent | None:
    """SOOP 라이브 채팅 패킷 하나. 필드 위치는 stream2clip ``soop_live_message`` 와 같고 닉네임 칸을 더 읽는다.

    닉네임 위치는 공개 문서가 없다. 채팅의 6번째 칸은 2026-11-21 실제 방송 채팅으로 확인했고,
    별풍선 3번째, 애드벌룬과 영상풍선 4번째 칸은 커뮤니티 구현을 따른 것으로 아직 실방송 확인 전이다.
    칸이 비어 있으면 아이디를 이름으로 쓴다.
    """
    if len(packet) < 14 or packet[:2] != b"\x1b\t":
        return None
    service = packet[2:6]
    parts = packet[14:].decode("utf-8", errors="replace").split("\x0c")

    def at(index: int) -> str:
        return parts[index] if len(parts) > index else ""

    if service == b"0005" and len(parts) > 2:
        user = _SOOP_SESSION.sub("", at(2))
        role = "owner" if streamer and user == streamer else ""
        return OverlayEvent("soop", "chat", at(6) or user, (("text", at(1)),), role=role)
    balloons = {b"0018": (2, 3, 4), b"0087": (3, 4, 10), b"0105": (3, 4, 5)}  # 아이디, 닉네임, 개수
    if service in balloons:
        user, nick, count = balloons[service]
        if not at(count).isdigit():
            return None
        unit = "애드벌룬" if service == b"0087" else "별풍선"
        return OverlayEvent("soop", "donation", at(nick) or _SOOP_SESSION.sub("", at(user)), (), amount=float(at(count)), unit=unit)
    return None


# --------------------------------------------------------------------------- Twitch

_IRC = re.compile(r"^(?:@(?P<tags>\S+) )?(?::(?P<prefix>\S+) )?(?P<command>\S+)(?: (?P<params>.*))?$")
_IRC_ESCAPES = {r"\s": " ", r"\:": ";", r"\\": "\\", r"\r": "\r", r"\n": "\n"}


def twitch_event(line: str) -> OverlayEvent | None:
    """Twitch IRC 한 줄(태그 포함). 채팅(PRIVMSG), 구독과 선물(USERNOTICE)만."""
    match = _IRC.match(line.strip())
    if not match or match.group("command") not in ("PRIVMSG", "USERNOTICE"):
        return None
    tags: dict[str, str] = {}
    for pair in (match.group("tags") or "").split(";"):
        key, _, value = pair.partition("=")
        tags[key] = re.sub(r"\\[s:\\rn]", lambda found: _IRC_ESCAPES[found.group()], value)
    _channel, _, text = (match.group("params") or "").partition(" :")
    if text.startswith("\x01ACTION ") and text.endswith("\x01"):
        text = text[8:-1]
    name = tags.get("display-name") or (match.group("prefix") or "").partition("!")[0]
    badges = tags.get("badges", "")
    role = "owner" if "broadcaster/" in badges else "moderator" if tags.get("mod") == "1" else ""
    color = tags.get("color", "") if _COLOR.match(tags.get("color", "")) else ""
    if match.group("command") == "USERNOTICE":
        if tags.get("msg-id") not in ("sub", "resub", "subgift", "submysterygift", "anonsubgift", "anonsubmysterygift"):
            return None
        notice = tags.get("system-msg", "") or "구독"
        return OverlayEvent("twitch", "member", name, (("text", notice + (f" {text}" if text else "")),), role=role, color=color)
    bits = int(tags["bits"]) if tags.get("bits", "").isdigit() else 0
    return OverlayEvent("twitch", "donation" if bits else "chat", name, (("text", text),), amount=float(bits), unit="bits" if bits else "", role=role, color=color)


# --------------------------------------------------------------------------- 수신기: stream2clip 연결 + 화면용 변환


def chzzk_source(channel: str) -> Any:
    """CHZZK 채널의 라이브 채팅(로그인 없이 시청자로 읽기)."""
    from stream2clip.live import ChzzkLiveChat

    class ChzzkOverlayChat(ChzzkLiveChat):
        def _messages(self, frame: Any) -> list[Any]:  # type: ignore[override]
            try:
                if json.loads(frame).get("cmd") == 0:  # 서버의 연결 확인에 답한다 (stream2clip과 같음)
                    self._socket.send('{"ver":"3","cmd":10000}')
            except (TypeError, ValueError, AttributeError):
                pass
            return chzzk_frame(frame)

    return ChzzkOverlayChat(channel)


def chzzk_api_source() -> Any:
    """내 CHZZK 채널의 채팅, 후원, 구독(공식 Open API). 먼저 ``debutkit chzzk login`` 으로 한 번 로그인해 둔다.

    세션 연결과 이벤트 구독은 ``ChzzkApiChat`` 이 하고, 이벤트 내용만 여기서 바꾼다.
    """
    from ..chzzk import make_api

    api = make_api(None, None)  # Client ID, Secret이 없으면 한국어 안내와 함께 ChzzkLoginError
    from stream2clip.chzzk_api import ChzzkApiChat

    class ChzzkApiOverlayChat(ChzzkApiChat):
        def _frame(self, frame: str) -> list[Any]:  # type: ignore[override]
            if frame.startswith("42"):
                try:
                    name, *rest = json.loads(frame[2:])
                except (ValueError, TypeError):
                    return []
                if name in ("CHAT", "DONATION", "SUBSCRIPTION"):
                    event = chzzk_api_event(str(name), _json_object(rest[0] if rest else {}))
                    return [event] if event is not None else []
            return super()._frame(frame)  # 연결, 구독 같은 SYSTEM 프레임

    return ChzzkApiOverlayChat(api, events=("chat", "donation", "subscription"))


def soop_source(channel: str) -> Any:
    """SOOP 채널의 라이브 채팅(로그인 없이 시청자로 읽기)."""
    from stream2clip.live import SoopLiveChat

    class SoopOverlayChat(SoopLiveChat):
        def _messages(self, frame: Any) -> list[Any]:  # type: ignore[override]
            event = soop_event(frame if isinstance(frame, bytes) else str(frame).encode("utf-8"), self.streamer)
            return [event] if event is not None else []

    return SoopOverlayChat(channel)


def twitch_source(channel: str) -> Any:
    """Twitch 채널의 채팅(익명 시청자로 읽기). 연결은 stream2clip ``TwitchLiveChat`` 그대로, 줄 해석만 바꾼다."""
    import ssl

    from stream2clip.live import TwitchLiveChat

    class TwitchOverlayChat(TwitchLiveChat):
        def read(self) -> list[Any]:  # type: ignore[override]
            if self.ended:
                return []
            if self._socket is None:
                try:
                    self._start()
                except OSError as error:
                    self._failures += 1
                    if self._failures >= self.retries:
                        raise RuntimeError(f"Twitch 채팅에 연결하지 못함: {error}") from error
                    return []
            data = b""
            try:
                while True:
                    chunk = self._socket.recv(65536)
                    if not chunk:
                        self._drop()
                        break
                    data += chunk
            except (BlockingIOError, ssl.SSLWantReadError, ssl.SSLWantWriteError, TimeoutError):
                pass
            except OSError:
                self._drop()
            *lines, self._rest = (self._rest + data).split(b"\r\n")
            found = []
            for raw in lines:
                line = raw.decode("utf-8", errors="replace")
                if line.startswith("PING"):
                    self._send("PONG" + line[4:] + "\r\n")
                elif (event := twitch_event(line)) is not None:
                    found.append(event)
            return found

    return TwitchOverlayChat(channel)


SAMPLE_CHATS = ["안녕하세요!", "ㅋㅋㅋㅋㅋㅋ", "오늘 방송 기대돼요", "목소리 너무 좋다", "첫 방송 축하드려요!!", "草", "888888", "오 그거 어떻게 했어요?",
                "아바타 움직임 자연스럽다", "BGM 뭐예요?", "ㄹㅇㅋㅋ", "화이팅!"]
SAMPLE_NAMES = ["치즈냥", "숲속토끼", "새벽감성", "고양이집사", "lurker_kim", "별빛시청자", "도토리", "Haru"]


class DemoChat:
    """방송 없이 오버레이 모양을 맞춰 볼 때 쓰는 가짜 채팅. 몇 초마다 채팅, 가끔 후원."""

    ended = False

    def __init__(self, *, every: float = 1.5, seed: int | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.every = every
        self._random = random.Random(seed)
        self._clock = clock
        self._next = clock()

    def make(self) -> OverlayEvent:
        pick = self._random
        platform = pick.choice(["chzzk", "soop", "twitch"])
        name = pick.choice(SAMPLE_NAMES)
        if pick.random() < 0.12:
            amount, unit = {"chzzk": (float(pick.choice([1000, 5000, 10000])), "원"), "soop": (float(pick.choice([10, 50, 100])), "별풍선"),
                            "twitch": (float(pick.choice([100, 500])), "bits")}[platform]
            return OverlayEvent(platform, "donation", name, (("text", "데뷔 축하해요! 앞으로도 응원할게요"),), amount=amount, unit=unit)
        return OverlayEvent(platform, "chat", name, (("text", pick.choice(SAMPLE_CHATS)),), role="moderator" if pick.random() < 0.05 else "")

    def read(self) -> list[OverlayEvent]:
        found = []
        while self._clock() >= self._next:
            found.append(self.make())
            self._next += self.every * (0.4 + self._random.random() * 1.2)
        return found

    def close(self) -> None:
        self.ended = True


def system_event(text: str) -> OverlayEvent:
    return OverlayEvent("system", "system", "debutkit", (("text", text),))
