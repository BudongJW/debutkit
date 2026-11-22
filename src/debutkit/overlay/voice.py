"""캐릭터 음성 반응: OBS 마이크 음량(obs-websocket InputVolumeMeters)으로 말하는 상태를 판단한다.

- OBS에 설정한 마이크와 필터(잡음 제거 등)를 그대로 사용. 별도 장치 권한이나 음성 라이브러리 불필요
- OBS 마이크(설정의 마이크/보조 오디오 1)를 우선 사용하고, 없으면 첫 마이크 입력 소스 사용. 이름을 지정할 수도 있다
- 말하기 판단: 기준 음량(기본 -40 dBFS)을 넘으면 말함, 기준보다 6 dB 낮아지고 0.25초가 지나면 멈춤(입 깜빡임 방지)
- 음성은 저장하거나 전송하지 않는다. 음량 수치만 이 PC의 캐릭터 화면에 전달
"""

from __future__ import annotations

import math
import queue
import threading
import time
from typing import Any, Callable

INPUT_VOLUME_METERS = 1 << 16  # obs-websocket EventSubscription.InputVolumeMeters
AUDIO_INPUT_KINDS = ("wasapi_input_capture", "coreaudio_input_capture", "pulse_input_capture", "alsa_input_capture", "jack_input_client")
DEFAULT_THRESHOLD = -40.0
FLOOR_DB = -60.0


def level_db(levels: Any) -> float:
    """``inputLevelsMul`` (채널별 [크기, 최대, 입력 최대] 배율)에서 가장 큰 채널의 dBFS."""
    loudest = 0.0
    for channel in levels or []:
        if isinstance(channel, (list, tuple)) and channel and isinstance(channel[0], (int, float)):
            loudest = max(loudest, float(channel[0]))
    return 20 * math.log10(loudest) if loudest > 1e-6 else -120.0


class TalkDetector:
    def __init__(self, threshold: float = DEFAULT_THRESHOLD, *, gap: float = 6.0, hold: float = 0.25) -> None:
        self.threshold, self.gap, self.hold = threshold, gap, hold
        self.talking = False
        self._quiet_since: float | None = None

    def update(self, db: float, now: float) -> bool:
        if db >= self.threshold:
            self.talking, self._quiet_since = True, None
        elif self.talking and db < self.threshold - self.gap:
            if self._quiet_since is None:
                self._quiet_since = now
            elif now - self._quiet_since >= self.hold:
                self.talking, self._quiet_since = False, None
        return self.talking


class VoiceState:
    """캐릭터 화면들이 받는 최신 상태. ``level`` 은 0에서 1(기준 음량 부근에서 0.5)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[Any] = []
        self.current: dict[str, Any] = {"talking": False, "level": 0.0, "db": -120.0, "source": ""}
        self._test_until = 0.0
        self._test_round = 0
        self._real: tuple[bool, float, str] = (False, -120.0, "")  # 시험 중 들어온 실제 음량(시험이 끝나면 다시 보냄)

    def publish(self, talking: bool, db: float, source: str, *, force: bool = False) -> None:
        if not force:
            self._real = (talking, db, source)
            if time.monotonic() < self._test_until:
                return  # 시험 중에는 실제 음량을 덮어쓰지 않음
        level = max(0.0, min(1.0, (db - FLOOR_DB) / (-FLOOR_DB)))
        state = {"talking": talking, "level": round(level, 3), "db": round(db, 1), "source": source}
        with self._lock:
            changed = state["talking"] != self.current["talking"] or abs(state["level"] - self.current["level"]) >= 0.02
            self.current = state
            subscribers = list(self._subscribers) if changed or force else []
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(state)
            except queue.Full:
                pass

    def test(self, talking: bool, seconds: float = 3.0) -> None:
        """설정 화면의 말하기 시험: 몇 초 동안 말하는 상태로 표시하고, 끝나면 실제 음량 상태로 되돌린다."""
        self._test_round += 1
        if not talking:
            self._test_until = 0.0
            self.publish(*self._real, force=True)
            return
        self._test_until = time.monotonic() + seconds
        self.publish(True, -20.0, "시험", force=True)
        timer = threading.Timer(seconds, self._end_test, args=(self._test_round,))
        timer.daemon = True
        timer.start()

    def _end_test(self, round_: int) -> None:
        if round_ == self._test_round:  # 그 사이에 새 시험을 시작하지 않았으면
            self._test_until = 0.0
            self.publish(*self._real, force=True)

    def subscribe(self, into: Any = None) -> tuple[Any, dict[str, Any]]:
        """새 값을 받을 대기열(``into`` 를 주면 그 대기열, ``put_nowait`` 만 사용)과 현재 값."""
        subscriber = into if into is not None else queue.Queue(maxsize=200)
        with self._lock:
            self._subscribers.append(subscriber)
            return subscriber, dict(self.current)

    def unsubscribe(self, subscriber: Any) -> None:
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)


def choose_input(client: Any, preferred: str | None = None) -> str | None:
    """사용할 마이크 입력 이름: 지정한 이름, OBS 마이크(mic1), 첫 마이크 입력 소스 순."""
    if preferred:
        return preferred
    try:
        special = client.request("GetSpecialInputs") or {}
        if special.get("mic1"):
            return str(special["mic1"])
    except Exception:
        pass
    inputs = (client.request("GetInputList") or {}).get("inputs") or []
    for item in inputs:
        if str(item.get("unversionedInputKind") or item.get("inputKind") or "") in AUDIO_INPUT_KINDS:
            return str(item.get("inputName"))
    return None


class VoiceMeter:
    """OBS에 연결해 마이크 음량을 받아 ``VoiceState`` 에 전달. 연결이 끊기면 다시 연결한다."""

    def __init__(self, state: VoiceState, host: str = "127.0.0.1", port: int = 4455, password: str | None = None, *, input_name: str | None = None,
                 threshold: float = DEFAULT_THRESHOLD, notify: Callable[[str], None] = lambda text: None, client_factory: Callable[[], Any] | None = None,
                 retry: float = 10.0, clock: Callable[[], float] = time.monotonic) -> None:
        self.state, self.input_name, self.retry, self.clock = state, input_name, retry, clock
        self._notify, self._last_note = notify, ""
        self.detector = TalkDetector(threshold)
        self._factory = client_factory or (lambda: _obs_client(host, port, password))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def notify(self, text: str) -> None:
        """같은 안내를 반복하지 않는다(OBS가 꺼져 있는 동안 재시도마다 같은 문장이 쌓이지 않게)."""
        if text != self._last_note:
            self._last_note = text
            self._notify(text)

    def run_once(self, client: Any, *, until: Callable[[], bool] = lambda: False) -> None:
        source = choose_input(client, self.input_name)
        if not source:
            raise RuntimeError("OBS에 마이크 입력 없음: OBS 설정의 오디오에서 마이크 지정")
        self.notify(f"캐릭터 음성 반응: OBS 마이크 '{source}' 사용(기준 {self.detector.threshold:.0f} dB)")
        while not self._stop.is_set() and not until():
            for event in client.poll(0.5):
                if event.get("eventType") != "InputVolumeMeters":
                    continue
                for item in (event.get("eventData") or {}).get("inputs") or []:
                    if item.get("inputName") == source:
                        db = level_db(item.get("inputLevelsMul"))
                        self.state.publish(self.detector.update(db, self.clock()), db, source)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                client = self._factory()
            except Exception as error:
                self.notify(f"캐릭터 음성 반응: OBS 연결 실패({error}). {self.retry:.0f}초 후 다시 시도")
                self._stop.wait(self.retry)
                continue
            try:
                with client:
                    self.run_once(client)
            except Exception as error:
                self.notify(f"캐릭터 음성 반응 중단: {error}. {self.retry:.0f}초 후 다시 시도")
            self.state.publish(False, -120.0, "")
            self._stop.wait(self.retry)

    def start(self) -> "VoiceMeter":
        self._thread = threading.Thread(target=self._run, name="debutkit-voice", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)


def _obs_client(host: str, port: int, password: str | None) -> Any:
    from stream2clip.obs import ObsClient

    return ObsClient(host, port, password, events=INPUT_VOLUME_METERS)
