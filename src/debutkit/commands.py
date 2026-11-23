"""스트리머, 매니저 채팅 명령: 방송 중 채팅으로 캐릭터 동작, VTube Studio 단축키, 시청자 참여 추첨을 조작한다.

| 명령 | 동작 |
|---|---|
| ``!동작 이름`` | 3D 캐릭터 동작 실행(등록한 동작 ID 또는 이름) |
| ``!단축키 이름`` | VTube Studio 단축키 실행(``debutkit vts login`` 으로 연결한 경우) |
| ``!모집`` | 시청자 참여 추첨 모집 시작(지난 명단 삭제) |
| ``!마감`` | 모집 마감 |
| ``!추첨`` ``!추첨 3`` | 당첨자 뽑기(기본 1명) |
| ``!순서`` | 참가자 순서 정하기 |

- 스트리머(owner)와 매니저(moderator) 채팅만 처리. SOOP은 스트리머 본인만 구분(매니저 구분 정보 없음)
- 저장 설정 ``chat_commands`` 가 false이거나 ``debutkit overlay --no-chat-commands`` 이면 끔(기본 켬)
- 결과와 실패 안내는 오버레이 상태 안내(system 사건, 설정 화면과 기록 파일)로 남긴다
"""

from __future__ import annotations

import queue
import threading
from typing import Any, Callable

from . import motion, raffle, settings, vts

COMMANDS = ("!동작", "!단축키", "!모집", "!마감", "!추첨", "!순서")
ROLES = ("owner", "moderator")


def find_motion(query: str) -> Any:
    """등록한 동작: ID, 이름(대소문자 무시), 이름 일부가 하나에만 맞는 동작 순."""
    query = query.strip()
    items = motion.all_motions()
    lowered = query.casefold()
    exact = [item for item in items if item.id == query] + [item for item in items if item.name.casefold() == lowered]
    if query and exact:
        return exact[0]
    partial = [item for item in items if lowered and lowered in item.name.casefold()]
    if len(partial) == 1:
        return partial[0]
    names = ", ".join(item.name for item in items[:8]) or "없음"
    raise ValueError(f"등록한 동작 없음: {query or '(이름 없음)'}. 동작 목록: {names}")


class HotkeyWorker:
    """VTube Studio 단축키 실행을 별도 스레드에서(채팅 처리가 연결을 기다리지 않게). 처음 실행할 때 연결하고 끊기면 다음에 다시 연결."""

    def __init__(self, notify: Callable[[str], None], connect: Callable[[], Any] | None = None) -> None:
        self.notify = notify
        self._connect = connect or (lambda: vts.connect())
        self._queue: queue.Queue[str | None] = queue.Queue(maxsize=20)
        self._thread: threading.Thread | None = None
        self.triggered: list[str] = []

    def trigger(self, hotkey: str) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="debutkit-chat-vts", daemon=True)
            self._thread.start()
        try:
            self._queue.put_nowait(hotkey)
        except queue.Full:
            self.notify("채팅 명령: VTube Studio 단축키 요청이 밀려 있어 건너뜀")

    def _run(self) -> None:
        client = None
        while True:
            hotkey = self._queue.get()
            if hotkey is None:
                break
            try:
                if client is None:
                    client = self._connect()
                client.trigger(hotkey)
                self.triggered.append(hotkey)
                self.notify(f"채팅 명령: VTube Studio 단축키 {hotkey} 실행")
            except Exception as error:
                self.notify(f"채팅 명령 실패(!단축키 {hotkey}): {error}")
                if client is not None:
                    client.close()
                client = None
        if client is not None:
            client.close()

    def stop(self) -> None:
        if self._thread is not None:
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass
            self._thread.join(timeout=3)


class ChatCommands:
    """오버레이 허브에 붙이는 채팅 명령 처리기."""

    def __init__(self, *, motion_state: Any, raffle_state: raffle.Raffle, notify: Callable[[str], None], enabled: bool | None = None,
                 hotkeys: HotkeyWorker | None = None, has_token: Callable[[], bool] = lambda: vts.load_token() is not None) -> None:
        self.motion_state = motion_state
        self.raffle = raffle_state
        self.notify = notify
        self._enabled = enabled
        self.hotkeys = hotkeys or HotkeyWorker(notify)
        self._has_token = has_token

    def enabled(self) -> bool:
        if self._enabled is not None:
            return self._enabled
        return bool(settings.load().get("chat_commands", True))

    def __call__(self, event: Any) -> None:
        if getattr(event, "kind", "") != "chat" or getattr(event, "role", "") not in ROLES or getattr(event, "platform", "") == "system":
            return
        text = str(getattr(event, "text", "")).strip()
        head, _, rest = text.partition(" ")
        if head not in COMMANDS or not self.enabled():
            return
        rest = rest.strip()
        who = str(getattr(event, "name", ""))
        try:
            self._run(head, rest, who)
        except (ValueError, OSError) as error:
            self.notify(f"채팅 명령 실패({head}): {error}")

    def _run(self, head: str, rest: str, who: str) -> None:
        if head == "!동작":
            found = find_motion(rest)
            self.motion_state.play(found.id)
            self.notify(f"채팅 명령: 동작 {found.name} 실행({who})")
        elif head == "!단축키":
            if not rest:
                raise ValueError("단축키 이름을 함께 입력(예: !단축키 Heart)")
            if not self._has_token():
                raise ValueError("VTube Studio 연결 전: debutkit vts login 또는 설정 마법사의 VTube Studio 연결 필요")
            self.hotkeys.trigger(rest)
        elif head == "!모집":
            status = self.raffle.start()
            self.notify(f"채팅 명령: 참여 추첨 모집 시작. 채팅에 {status['keyword']}({who})")
        elif head == "!마감":
            status = self.raffle.stop()
            self.notify(f"채팅 명령: 참여 추첨 모집 마감, 참가 {status['count']}명({who})")
        elif head == "!추첨":
            count = int(rest) if rest.isdigit() else 1
            result = self.raffle.draw(count, "pick")
            self.notify("채팅 명령: 당첨 " + ", ".join(winner["name"] for winner in result["winners"]))
        elif head == "!순서":
            result = self.raffle.draw(mode="order")
            self.notify(f"채팅 명령: 참가자 {result['total']}명 순서 정하기")

    def stop(self) -> None:
        self.hotkeys.stop()
