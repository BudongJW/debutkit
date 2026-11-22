"""얼굴 추적 값 전달: 추적 화면(``/tracker``, 일반 브라우저)이 계산한 값을 캐릭터 화면(``/character``, OBS)으로 보낸다.

- 카메라 영상은 추적 화면(브라우저) 안에서만 처리하고, 이 서버에는 숫자 값만 들어온다. 저장하거나 외부로 보내지 않는다
- 값: ``yaw``, ``pitch``, ``roll`` (머리 회전, 라디안), ``blinkLeft``, ``blinkRight``, ``mouth``, ``smile`` (0에서 1), ``found`` (얼굴 인식 여부)
- OBS 브라우저 소스는 카메라를 쓸 수 없어 추적은 별도 브라우저 창에서 한다(docs/CHARACTER.md)
"""

from __future__ import annotations

import math
import queue
import threading
import time
from typing import Any

#: 항목별 허용 범위(벗어나면 잘라낸다)
FIELDS: dict[str, tuple[float, float]] = {"yaw": (-1.2, 1.2), "pitch": (-1.2, 1.2), "roll": (-1.2, 1.2), "blinkLeft": (0.0, 1.0),
                                          "blinkRight": (0.0, 1.0), "mouth": (0.0, 1.0), "smile": (0.0, 1.0)}


def clean(data: Any) -> dict[str, Any] | None:
    """추적 화면이 보낸 값 확인. 형식이 아니면 None, 범위를 벗어난 값은 잘라냄, 모르는 항목은 버림."""
    if not isinstance(data, dict):
        return None
    found: dict[str, Any] = {"found": data.get("found") is True}
    for name, (low, high) in FIELDS.items():
        value = data.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            found[name] = round(min(high, max(low, float(value))), 4)
    return found


class TrackingState:
    """캐릭터 화면들이 받는 최신 추적 값."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[Any] = []
        self.current: dict[str, Any] = {"found": False, "time": 0.0}

    def publish(self, values: dict[str, Any]) -> None:
        state = {**values, "time": round(time.time(), 3)}
        with self._lock:
            self.current = state
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(state)
            except queue.Full:  # 느린 화면 때문에 서버가 막히지 않도록 버린다
                pass

    def subscribe(self, into: Any = None) -> tuple[Any, dict[str, Any]]:
        """새 값을 받을 대기열(``into`` 를 주면 그 대기열, ``put_nowait`` 만 사용)과 현재 값."""
        subscriber = into if into is not None else queue.Queue(maxsize=120)
        with self._lock:
            self._subscribers.append(subscriber)
            return subscriber, dict(self.current)

    def unsubscribe(self, subscriber: Any) -> None:
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)
