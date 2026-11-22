"""YouTube 연결 확인(``debutkit youtube check``).

방송 주소, API 키와 라이브 채팅, 요청 방식, 스트리밍 방식을 한 번씩 실행해 결과를 보고한다.
할당량 사용: 방송 확인 1 단위, 요청 방식 1회 5 단위, 스트리밍 연결 1회 5 단위(합계 약 11 단위).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

from .youtube import YouTubeLiveChat


@dataclass(frozen=True)
class Step:
    name: str
    ok: bool | None  # None: 실행하지 않음
    detail: str


def check(address: str, api_key: str | None = None, *, timeout: float = 20.0, send: Callable[[str, dict[str, str]], tuple[int, bytes]] | None = None,
          probe: Callable[..., tuple[bool, str]] | None = None, streaming: bool | None = None) -> list[Step]:
    from .youtube_stream import available, probe_stream

    try:
        poller = YouTubeLiveChat(address, api_key, send=send)
    except ValueError as error:
        return [Step("방송 주소, API 키", False, str(error))]
    steps = [Step("방송 주소", True, f"영상 ID {poller.video}")]
    try:
        chat = poller.chat_id()
    except RuntimeError as error:
        return [*steps, Step("API 키, 라이브 채팅", False, str(error))]
    steps.append(Step("API 키, 라이브 채팅", True, "방송 중인 라이브 채팅 확인(1 단위)"))
    try:
        data = poller.fetch()
    except RuntimeError as error:
        steps.append(Step("요청 방식", False, str(error)))
    else:
        wait = float(data.get("pollingIntervalMillis") or 0) / 1000
        steps.append(Step("요청 방식", True, f"채팅 {len(data.get('items') or [])}개 수신(5 단위). YouTube 권장 요청 간격 {wait:.1f}초"))
    if not (available() if streaming is None else streaming):
        steps.append(Step("스트리밍 방식", None, '실행 안 함: grpcio, protobuf 필요(pip install "debutkit[youtube]")'))
    else:
        ok, detail = (probe or probe_stream)(chat, poller.api_key, timeout=timeout)
        steps.append(Step("스트리밍 방식", ok, detail))
    return steps


LABELS = {True: "정상", False: "실패", None: "생략"}


def format_steps(steps: list[Step]) -> str:
    return "\n".join(f"  [{LABELS[step.ok]}] {step.name}  {step.detail}" for step in steps)


def as_json(steps: list[Step]) -> list[dict[str, Any]]:
    return [asdict(step) for step in steps]
