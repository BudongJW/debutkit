"""휴대폰 앱의 카메라 영상(WebRTC) 연결 중계: 앱의 연결 제안(offer)을 OBS 브라우저 소스의 수신 화면(``/camera/view``)으로,
수신 화면의 응답(answer)을 앱으로 전달한다.

- 영상은 휴대폰과 수신 화면이 같은 Wi-Fi에서 직접 주고받는다(STUN, TURN 같은 외부 서버 없음). debutkit 서버는 연결 정보(SDP)만 전달
- 브라우저는 자기 내부 주소를 임의 이름(``*.local``)으로 감추므로, 응답의 그 후보를 이 PC의 내부 주소로 바꿔 휴대폰이 찾아오게 한다
- 통화는 하나만: 새 제안이 오면 이전 통화는 끝낸다. 응답은 처음 응답한 수신 화면만(OBS와 일반 브라우저에 함께 열려 있어도 하나만 연결)
- 제안은 승인된 앱의 서명된 요청으로만 들어온다(remote.py). 수신 화면의 응답은 이 PC(127.0.0.1) 서버로만
"""

from __future__ import annotations

import queue
import secrets
import threading
import time
from typing import Any, Iterable

MAX_SDP = 20000
OFFER_SECONDS = 20.0  # 이 시간 안에 수신 화면이 응답하지 않으면 끝난 것으로


class CallError(ValueError):
    """잘못된 연결 정보. 메시지는 한국어 안내."""


def check_sdp(sdp: Any) -> str:
    text = str(sdp or "")
    if not text.startswith("v=0") or len(text) > MAX_SDP or "m=video" not in text:
        raise CallError("영상 연결 정보(SDP) 형식이 아님")
    return text


def rewrite_candidates(sdp: str, addresses: Iterable[str]) -> str:
    """``*.local`` 이름으로 감춘 후보를 이 PC의 내부 주소마다 하나씩으로 바꾼다(앞 주소가 먼저). 다른 후보는 그대로."""
    targets = list(dict.fromkeys(address for address in addresses if address))
    newline = "\r\n" if "\r\n" in sdp else "\n"
    lines: list[str] = []
    for line in sdp.split(newline):
        parts = line.split(" ")
        if line.startswith("a=candidate:") and len(parts) > 5 and parts[4].endswith(".local") and targets:
            lines += [" ".join(parts[:4] + [address] + parts[5:]) for address in targets]
        else:
            lines.append(line)
    return newline.join(lines)


class CameraCall:
    """현재 통화(제안, 응답, 끝)와 수신 화면 구독(``/live?feeds=camera``)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[Any] = []
        self._seq = 0
        self._answer: str | None = None
        self._offered_at = 0.0
        self.current: dict[str, Any] = self._event("idle")

    def _event(self, kind: str, **fields: Any) -> dict[str, Any]:
        self._seq += 1
        return {"type": kind, "seq": self._seq, "time": round(time.time(), 3), **fields}

    def _send(self, event: dict[str, Any]) -> None:
        self.current = event
        for subscriber in list(self._subscribers):
            try:
                subscriber.put_nowait(event)
            except Exception:  # 가득 찬 대기열(멈춘 화면)
                pass

    def offer(self, device: str, name: str, sdp: Any) -> str:
        """앱의 새 연결 제안. 이전 통화는 끝낸다. 통화 번호를 돌려준다."""
        text = check_sdp(sdp)
        call_id = secrets.token_hex(6)
        with self._lock:
            self._answer = None
            self._offered_at = time.monotonic()
            self._send(self._event("offer", id=call_id, device=device, name=name[:30], sdp=text))
        return call_id

    def answer(self, call_id: str, sdp: Any, addresses: Iterable[str]) -> bool:
        """수신 화면의 응답. 처음 응답한 화면만 받는다(이미 응답했거나 끝난 통화면 False)."""
        text = check_sdp(sdp)
        with self._lock:
            current = self.current
            if current.get("type") != "offer" or current.get("id") != call_id or self._answer is not None:
                return False
            self._answer = rewrite_candidates(text, addresses)
            self._send(self._event("answered", id=call_id, device=current.get("device"), name=current.get("name")))
            return True

    def poll(self, call_id: str, device: str) -> dict[str, Any]:
        """앱이 응답을 기다린다: waiting, answered(sdp), ended."""
        with self._lock:
            current = self.current
            if current.get("id") != call_id or current.get("device") != device or current.get("type") not in ("offer", "answered"):
                return {"state": "ended"}
            if self._answer is not None:
                return {"state": "answered", "sdp": self._answer}
            if time.monotonic() - self._offered_at > OFFER_SECONDS:
                self._send(self._event("idle"))
                return {"state": "ended", "reason": "수신 화면 응답 없음: OBS에 휴대폰 카메라(앱) 소스가 있는지 확인"}
            return {"state": "waiting"}

    def stop(self, call_id: str = "", device: str = "") -> bool:
        """통화 끝(앱의 멈춤, 기기 삭제). 번호나 기기를 주면 그 통화일 때만."""
        with self._lock:
            current = self.current
            if current.get("type") not in ("offer", "answered"):
                return False
            if (call_id and current.get("id") != call_id) or (device and current.get("device") != device):
                return False
            self._answer = None
            self._send(self._event("stop", id=current.get("id")))
            return True

    def status(self) -> dict[str, Any]:
        current = self.current
        state = {"offer": "connecting", "answered": "connected"}.get(str(current.get("type")), "idle")
        return {"state": state, "name": current.get("name", ""), "since": current.get("time")}

    def subscribe(self, into: Any = None) -> tuple[Any, dict[str, Any]]:
        subscriber = into if into is not None else queue.Queue(maxsize=50)
        with self._lock:
            self._subscribers.append(subscriber)
            return subscriber, dict(self.current)

    def unsubscribe(self, subscriber: Any) -> None:
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)
