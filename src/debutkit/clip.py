"""방송 중 자동 클립: 오버레이가 받은 채팅으로 stream2clip 라이브 모드를 돌린다.

채팅 연결은 오버레이와 하나를 같이 쓴다. 여러 플랫폼에 동시 송출하면 모든 채팅을 합쳐서
판단한다. 채팅이 평소보다 크게 몰리면(stream2clip ``SurgeDetector``) OBS 리플레이 버퍼를
저장하고 그 순간을 잘라 클립으로 만든다(stream2clip ``ReplayClipper``). 스트리머나
매니저가 채팅에 ``!clip`` 같은 표시 명령을 쓰면 바로 저장한다.

닉네임은 판단에만 쓰고(해시) 저장하지 않는다.
"""

from __future__ import annotations

import os
import queue
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .overlay.events import OverlayEvent, system_event

KINDS = {"chat": "text", "donation": "paid", "member": "member"}


def default_clip_dir() -> Path:
    videos = Path.home() / "Videos"
    return (videos if videos.is_dir() else Path.home()) / "debutkit-clips"


def to_chat_message(event: OverlayEvent) -> Any | None:
    """오버레이 사건 → stream2clip ``ChatMessage``. 채팅이 아닌 사건은 ``None``."""
    if event.kind not in KINDS or event.platform == "system":
        return None
    from stream2clip.chat import ChatMessage, author_key

    return ChatMessage(time=event.time, text=event.text, author=author_key(f"{event.platform}:{event.name}"), kind=KINDS[event.kind],
                       amount=event.amount, currency=event.unit or None, role=event.role)


class ChatTap:
    """허브에 붙여 사건을 받고, stream2clip 라이브 모드가 읽는 채팅 수신기(``ChatSource``)처럼 내준다."""

    def __init__(self) -> None:
        self.ended = False
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=20000)

    def __call__(self, event: OverlayEvent) -> None:
        message = to_chat_message(event)
        if message is not None and not self.ended:
            try:
                self._queue.put_nowait(message)
            except queue.Full:
                pass

    def read(self) -> list[Any]:
        found = []
        while True:
            try:
                found.append(self._queue.get_nowait())
            except queue.Empty:
                return found

    def close(self) -> None:
        self.ended = True


def replay_clipper(out_dir: str | os.PathLike[str], host: str = "127.0.0.1", port: int = 4455, password: str | None = None) -> Any:
    """OBS 리플레이 버퍼를 저장해 클립을 만드는 stream2clip ``ReplayClipper``. 저장할 때마다 OBS에 새로 연결한다."""
    from stream2clip.live import ReplayClipper
    from stream2clip.obs import ObsClient

    return ReplayClipper(out_dir, lambda: ObsClient(host, port, password))


class AutoClipper:
    """허브의 채팅을 지켜보다 급증하면 ``clipper(trigger)`` 를 부르고 결과를 오버레이 설정 화면에 알린다."""

    def __init__(self, hub: Any, clipper: Callable[[Any], Any], *, config: Any = None, clock: Callable[[], float] = time.time, poll: float = 1.0) -> None:
        from stream2clip.live import LiveConfig, SurgeDetector

        self.hub = hub
        self.clipper = clipper
        self.config = config or LiveConfig()
        self.clock = clock
        self.poll = poll
        self.tap = ChatTap()
        self.detector = SurgeDetector(self.config, live_from=clock())
        self.saved: list[Any] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _on_trigger(self, trigger: Any) -> None:
        reasons = ", ".join(trigger.reasons) or f"점수 {trigger.score:.1f}"
        try:
            saved = self.clipper(trigger)
        except Exception as error:  # OBS가 꺼졌거나 리플레이 버퍼가 멈춤
            self.hub.publish(system_event(f"클립 저장 실패 ({reasons}): {error}"))
            return
        self.saved.append(saved)
        note = f" - {saved.note}" if getattr(saved, "note", "") else ""
        self.hub.publish(system_event(f"클립 저장: {Path(saved.clip).name} ({reasons}){note}"))

    def _run(self) -> None:
        from stream2clip.live import watch

        try:
            watch(self.tap, self.detector, self._on_trigger, clock=self.clock, sleep=lambda s: self._stop.wait(s), poll=self.poll, should_stop=self._stop.is_set)
        except Exception as error:
            self.hub.publish(system_event(f"자동 클립 중단: {error}"))

    def start(self) -> "AutoClipper":
        self.hub.taps.append(self.tap)
        self._thread = threading.Thread(target=self._run, name="debutkit-autoclip", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self.tap.close()
        if self.tap in self.hub.taps:
            self.hub.taps.remove(self.tap)
        if self._thread is not None:
            self._thread.join(timeout=5)
