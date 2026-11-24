"""시험용 포트 번호: 이 PC에서 TCP와 UDP 모두 열 수 있는 빈 번호."""

from __future__ import annotations

import socket

ATTEMPTS = 200
#: (먼저 빈 번호를 받는 종류, 같은 번호로 열어 보는 종류)
ORDERS = ((socket.SOCK_STREAM, socket.SOCK_DGRAM), (socket.SOCK_DGRAM, socket.SOCK_STREAM))


def _both_open(first: int, second: int) -> int | None:
    with socket.socket(socket.AF_INET, first) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        with socket.socket(socket.AF_INET, second) as other:
            try:
                other.bind(("127.0.0.1", port))
            except OSError:
                return None
    return port


def free_port() -> int:
    """TCP와 UDP 모두 열 수 있는 번호.

    Windows는 한 종류만 예약된 번호대가 있음(Hyper-V, WSL, Docker). UDP로 받은 번호가 연달아 TCP 예약 번호대에 들어가는 경우가 있어
    TCP로 먼저 받고 같은 번호의 UDP 확인, UDP로 먼저 받고 같은 번호의 TCP 확인을 번갈아 시도.
    """
    for attempt in range(ATTEMPTS):
        port = _both_open(*ORDERS[attempt % len(ORDERS)])
        if port:
            return port
    raise RuntimeError(f"free port not found ({ATTEMPTS} attempts, TCP and UDP)")
