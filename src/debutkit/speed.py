"""업로드 속도 측정과 송출 비트레이트 추천. 직접 실행할 때만 동작한다.

- 측정: Cloudflare 측정 서버(speed.cloudflare.com)에 임의 데이터를 크기를 늘려 가며 전송
  (약 10초, 최대 31 MB). 개인정보나 PC 정보는 보내지 않는다
- 추천: 측정값의 70%를 송출에 쓸 수 있다고 보고(30% 여유), 오디오 160 kbps를 뺀 값으로
  해상도와 영상 비트레이트를 고른다. 값은 일반 권장치이며 플랫폼별 최대값은 각 플랫폼 안내 확인
"""

from __future__ import annotations

import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Callable

UPLOAD_URL = "https://speed.cloudflare.com/__up"
SIZES = (1_000_000, 2_000_000, 4_000_000, 8_000_000, 16_000_000)
HEADROOM = 0.7
AUDIO_KBPS = 160

#: 영상 비트레이트(kbps)와 해상도. 위에서부터 고른다
PRESETS: tuple[tuple[int, str], ...] = (
    (6000, "1080p 60fps"),
    (4500, "1080p 30fps 또는 720p 60fps"),
    (3000, "720p 30fps"),
    (2000, "480p 30fps"),
)


def _post(body: bytes) -> None:
    request = urllib.request.Request(UPLOAD_URL, data=body, method="POST", headers={"Content-Type": "application/octet-stream", "User-Agent": "debutkit"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - 고정 https 주소
        response.read()


def measure_upload(*, send: Callable[[bytes], None] | None = None, clock: Callable[[], float] = time.perf_counter,
                   budget: float = 12.0, sizes: tuple[int, ...] = SIZES, progress: Callable[[float], None] | None = None) -> float:
    """업로드 속도(Mbps). 작은 전송은 지연 시간 때문에 낮게 나오므로 가장 높은 값을 쓴다."""
    send = send or _post
    best = 0.0
    started = clock()
    for size in sizes:
        body = os.urandom(size)  # 압축되지 않는 내용
        before = clock()
        send(body)
        took = clock() - before
        if took > 0:
            best = max(best, size * 8 / took / 1_000_000)
            if progress is not None:
                progress(best)
        if took >= 2.5 or (clock() - started) + took * 2.2 > budget:  # 다음 크기는 두 배라 시간 예산을 넘김
            break
    if best <= 0:
        raise RuntimeError("업로드 속도를 측정하지 못함")
    return best


@dataclass(frozen=True)
class Advice:
    mbps: float
    video_kbps: int  # 0이면 권장 설정 없음
    preset: str
    level: str  # ok | warn | fail


def advise(mbps: float) -> Advice:
    budget = int(mbps * 1000 * HEADROOM) - AUDIO_KBPS
    for kbps, preset in PRESETS:
        if budget >= kbps:
            level = "ok" if kbps >= 4500 else "warn"
            return Advice(mbps, kbps, preset, level)
    return Advice(mbps, 0, "", "fail")


def check(mbps: float):  # -> doctor.Check (순환 import 피하려고 늦게 가져옴)
    from .doctor import FAIL, OK, WARN, Check

    advice = advise(mbps)
    detail = f"{mbps:.1f} Mbps"
    if advice.level == "fail":
        return Check("upload", "업로드 속도", FAIL, detail, "송출에 부족(영상 2,000 kbps 미만). 유선 연결, 다른 기기의 업로드 중지 후 다시 측정")
    setting = f"{advice.preset}, 영상 {advice.video_kbps:,} kbps, 오디오 {AUDIO_KBPS} kbps (CBR)"
    if advice.level == "ok":
        return Check("upload", "업로드 속도", OK, f"{detail}. 권장 {setting}")
    return Check("upload", "업로드 속도", WARN, f"{detail}. 권장 {setting}", "고화질 송출에는 부족. 유선 연결 권장. 플랫폼별 최대 비트레이트는 각 플랫폼 안내 확인")
