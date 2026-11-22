"""외부 프로그램 준비: ffmpeg 찾기와 다운로드, 새 버전 확인.

자동 클립은 OBS 리플레이 파일을 ffmpeg로 잘라 만든다. ffmpeg는 키트에 포함하지 않고,
Windows에서는 고정된 빌드 하나를 SHA-256으로 확인한 뒤 사용자 캐시 폴더에 다운로드한다.
다른 운영체제는 패키지 관리자로 설치한다. 찾는 순서와 다운로드 위치는 채팅 연결 모듈
(``debutkit[live]``)과 같아서, 다운로드한 ffmpeg를 키트 전체가 같이 쓴다.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable

Progress = Callable[[int, int], None]

LATEST_RELEASE_API = "https://api.github.com/repos/BudongJW/debutkit/releases/latest"
RELEASES_PAGE = "https://github.com/BudongJW/debutkit/releases/latest"


_STAGES = {"a": 0, "b": 1, "rc": 2}


def _version_tuple(text: str) -> tuple[int, ...]:
    """비교용 값. 사전 릴리스(a, b, rc)는 같은 번호의 정식 버전보다 낮다(1.0.0rc1 < 1.0.0)."""
    found = re.search(r"(\d+)\.(\d+)\.(\d+)(?:[-.]?(a|b|rc)\.?(\d+))?", text)
    if not found:
        return (0,)
    major, minor, patch, stage, number = found.groups()
    return (int(major), int(minor), int(patch), _STAGES[stage] if stage else 3, int(number or 0))


def is_newer(latest: str, current: str) -> bool:
    """``latest`` 가 ``current`` 보다 높은 버전인지(v0.3.1 > 0.3.0, 1.0.0 > 1.0.0rc1)."""
    return _version_tuple(latest) > _version_tuple(current)


def latest_release(opener: Callable[..., Any] | None = None) -> str:
    """GitHub에 공개된 최신 릴리스 버전(예: 0.3.0). 요청할 때만 연결하고 아무 정보도 보내지 않는다."""
    request = urllib.request.Request(LATEST_RELEASE_API, headers={"Accept": "application/vnd.github+json", "User-Agent": "debutkit"})
    with (opener or urllib.request.urlopen)(request, timeout=15) as response:  # noqa: S310 - 고정 https 주소
        data = json.loads(response.read().decode("utf-8"))
    tag = str(data.get("tag_name") or "")
    if not tag:
        raise RuntimeError("최신 릴리스 정보 없음")
    return tag.lstrip("v")


def update_message(current: str, opener: Callable[..., Any] | None = None) -> str:
    """새 버전 확인 결과 한 줄. 연결 실패도 문장으로 돌려준다."""
    try:
        latest = latest_release(opener)
    except Exception as error:
        return f"새 버전 확인 실패: {error}"
    if is_newer(latest, current):
        return f"새 버전 {latest} 있음 (현재 {current}): {RELEASES_PAGE}"
    return f"최신 버전 사용 중 ({current})"


def ffmpeg_path() -> str | None:
    """ffmpeg와 ffprobe가 모두 있으면 ffmpeg 경로, 아니면 ``None``."""
    try:
        from stream2clip.ffmpeg import FFmpegNotFoundError, find_ffmpeg, find_ffprobe
    except ImportError:
        found = shutil.which("ffmpeg")
        return found if found and shutil.which("ffprobe") else None
    try:
        path = find_ffmpeg()
        find_ffprobe()
    except FFmpegNotFoundError:
        return None
    return path


def can_download_ffmpeg(platform: str | None = None) -> bool:
    """다운로드를 지원하는 운영체제인지(Windows)."""
    return (platform or sys.platform) == "win32"


def install_hint(platform: str | None = None) -> str:
    """이 운영체제에서 ffmpeg를 설치하는 방법 한 줄."""
    platform = platform or sys.platform
    if platform == "win32":
        return "debutkit setup --ffmpeg 실행 또는 설정 마법사 PC 점검 화면의 ffmpeg 다운로드 버튼 사용"
    if platform == "darwin":
        return "터미널에서 brew install ffmpeg 실행"
    return "배포판 패키지 관리자로 설치(예: sudo apt install ffmpeg)"


def ffmpeg_megabytes() -> int:
    """다운로드할 ffmpeg 압축 파일 크기(MB). 채팅 연결 모듈이 없으면 0."""
    try:
        from stream2clip.tools import FFMPEG_BUILD
    except ImportError:
        return 0
    return FFMPEG_BUILD.megabytes


def download_ffmpeg(*, archive: str | None = None, on_progress: Progress | None = None, cancelled: Callable[[], bool] | None = None) -> list[Path]:
    """ffmpeg와 ffprobe를 다운로드해 찾는 위치에 넣는다. ``archive`` 를 주면 이미 다운로드한 압축 파일을 쓴다(SHA-256 확인)."""
    if not can_download_ffmpeg():
        raise RuntimeError(f"이 운영체제는 다운로드 미지원: {install_hint()}")
    try:
        from stream2clip.tools import install_ffmpeg
    except ImportError as error:
        raise RuntimeError('ffmpeg 다운로드에는 채팅 연결 모듈 필요: pip install "debutkit[live]"') from error
    return install_ffmpeg(archive=archive, on_progress=on_progress, cancelled=cancelled)


def progress_printer(megabytes: int, step: int = 10, write: Callable[[str], None] = print) -> Progress:
    """(받은 바이트, 전체 바이트)를 받아 ``step`` 퍼센트마다 한 줄씩 쓰는 함수."""
    shown = [-step]

    def progress(done: int, total: int) -> None:
        percent = int(done * 100 / total) if total else 0
        if percent >= shown[0] + step or (total and done >= total and shown[0] < 100):
            shown[0] = 100 if total and done >= total else percent - percent % step
            write(f"  {shown[0]:3d}%  {done / 1e6:.0f} / {megabytes} MB")

    return progress
