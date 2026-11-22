"""외부 프로그램 준비: ffmpeg 찾기와 내려받기.

자동 클립은 OBS 리플레이 파일을 ffmpeg로 잘라 만든다. ffmpeg는 키트에 포함하지 않고,
Windows에서는 고정된 빌드 하나를 SHA-256으로 확인한 뒤 사용자 캐시 폴더에 내려받는다.
다른 운영체제는 패키지 관리자로 설치한다. 찾는 순서와 내려받는 위치는 채팅 연결 모듈
(``debutkit[live]``)과 같아서, 한 번 받은 ffmpeg를 키트 전체가 같이 쓴다.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Callable

Progress = Callable[[int, int], None]


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
    """내려받기를 지원하는 운영체제인지(Windows)."""
    return (platform or sys.platform) == "win32"


def install_hint(platform: str | None = None) -> str:
    """이 운영체제에서 ffmpeg를 설치하는 방법 한 줄."""
    platform = platform or sys.platform
    if platform == "win32":
        return "debutkit setup --ffmpeg 실행 또는 설정 마법사 PC 점검 화면의 ffmpeg 내려받기 사용"
    if platform == "darwin":
        return "터미널에서 brew install ffmpeg 실행"
    return "배포판 패키지 관리자로 설치 (예: sudo apt install ffmpeg)"


def ffmpeg_megabytes() -> int:
    """내려받을 ffmpeg 압축 파일 크기(MB). 채팅 연결 모듈이 없으면 0."""
    try:
        from stream2clip.tools import FFMPEG_BUILD
    except ImportError:
        return 0
    return FFMPEG_BUILD.megabytes


def download_ffmpeg(*, archive: str | None = None, on_progress: Progress | None = None, cancelled: Callable[[], bool] | None = None) -> list[Path]:
    """ffmpeg와 ffprobe를 내려받아 찾는 위치에 넣는다. ``archive`` 를 주면 이미 받은 압축 파일을 쓴다(SHA-256 확인)."""
    if not can_download_ffmpeg():
        raise RuntimeError(f"이 운영체제는 내려받기 미지원: {install_hint()}")
    try:
        from stream2clip.tools import install_ffmpeg
    except ImportError as error:
        raise RuntimeError('ffmpeg 내려받기에는 채팅 연결 모듈 필요: pip install "debutkit[live]"') from error
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
