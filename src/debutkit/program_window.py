"""송출 화면 창(Windows): 오버레이 서버의 ``/program`` 을 Edge(없으면 Chrome) 앱 창으로 열고 찾는다.

- 설정 폴더의 전용 프로필(``program-browser``)로 열어 사용자의 평소 브라우저와 섞이지 않는다. Edge는 InPrivate로 열어
  로그인, 동기화 안내 창이 화면을 가리지 않게 한다
- 화면 배율을 1로 고정(``--force-device-scale-factor=1``)해 창 크기가 곧 송출 픽셀 수가 되게 한다
- 다른 창에 가려져도 그리기를 멈추지 않게 한다(Chromium의 가려진 창 절전 끄기). 최소화하면 Windows가 그리지 않아 화면이 멈춘다
- 창 제목에 실행마다 다른 표식(``?window=``)을 넣어, 사용자가 평소 브라우저에서 연 송출 화면과 구분한다
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping

TITLE = "debutkit program"
CLASS_NAME = "Chrome_WidgetWin_1"  # Edge, Chrome 창
#: 창 크기(화면 배율 1 기준)에서 창 안 화면을 뺀 값: 좌우 보이지 않는 테두리 8+8, 제목 표시줄 31 + 아래 테두리 8
FRAME = (16, 39)
WM_CLOSE = 0x0010


def available(platform: str | None = None) -> bool:
    """송출 화면 창을 다룰 수 있는 운영체제인지(Windows)."""
    return (platform or sys.platform) == "win32"


def browser_candidates(environ: Mapping[str, str] | None = None) -> list[Path]:
    """Edge를 먼저(Windows 10, 11에 기본 설치), 그다음 Chrome. ``os.environ`` 은 Windows에서 대소문자를 가리지 않는다."""
    env = os.environ if environ is None else environ
    roots = [env.get(name, "") for name in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    found: list[Path] = []
    for relative in (("Microsoft", "Edge", "Application", "msedge.exe"), ("Google", "Chrome", "Application", "chrome.exe")):
        for root in roots:
            if root:
                found.append(Path(root, *relative))
    return found


def find_browser(exists: Callable[[Path], bool] = Path.is_file, environ: Mapping[str, str] | None = None) -> str | None:
    for path in browser_candidates(environ):
        if exists(path):
            return str(path)
    return None


def window_size(width: int, height: int) -> tuple[int, int]:
    """창 안 화면이 ``width`` x ``height`` 가 되는 창 크기(화면에 다 들어가지 않으면 브라우저가 줄인다)."""
    return width + FRAME[0], height + FRAME[1]


def browser_args(browser: str, url: str, profile: Path, width: int, height: int) -> list[str]:
    window_width, window_height = window_size(width, height)
    args = [browser, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check", "--disable-sync",
            "--force-device-scale-factor=1", f"--window-size={window_width},{window_height}", "--window-position=40,40",
            "--autoplay-policy=no-user-gesture-required", "--disable-features=CalculateNativeWinOcclusion",
            "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding", "--disable-background-timer-throttling"]
    if Path(browser).name.lower() == "msedge.exe":
        args.insert(3, "--inprivate")  # 새 프로필의 자동 로그인, 동기화 안내 창이 화면을 어둡게 가리는 것 방지
    return args


def launch(browser: str, url: str, profile: Path, width: int, height: int) -> subprocess.Popen[bytes]:
    profile.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(browser_args(browser, url, profile, width, height), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, close_fds=True)


def _user32():  # pragma: no cover - Windows 전용
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [proc, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    for name in ("IsWindowVisible", "IsIconic"):
        getattr(user32, name).argtypes = [wintypes.HWND]
        getattr(user32, name).restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    return ctypes, user32, proc


def windows() -> list[tuple[int, str, str]]:  # pragma: no cover - Windows 전용
    """보이는 최상위 창의 (핸들, 클래스, 제목)."""
    if not available():
        return []
    ctypes, user32, proc = _user32()
    found: list[tuple[int, str, str]] = []

    def visit(hwnd: int, _: int) -> bool:
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            kind = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, kind, 256)
            found.append((int(hwnd), kind.value, title.value))
        return True

    user32.EnumWindows(proc(visit), 0)
    return found


def title_for(token: str) -> str:
    return f"{TITLE} {token}"


def find(token: str, listing: Callable[[], list[tuple[int, str, str]]] = windows) -> int | None:
    """표식이 ``token`` 인 송출 화면 창의 핸들. InPrivate 창은 제목 뒤에 `` - [InPrivate]`` 가 붙는다."""
    wanted = title_for(token)
    for hwnd, kind, title in listing():
        if kind == CLASS_NAME and (title == wanted or title.startswith(wanted + " ")):
            return hwnd
    return None


def minimized(hwnd: int) -> bool:  # pragma: no cover - Windows 전용
    if not available():
        return False
    _, user32, _ = _user32()
    return bool(user32.IsIconic(hwnd))


def close(hwnd: int) -> None:  # pragma: no cover - Windows 전용
    """창 닫기 요청(브라우저가 정상 종료)."""
    if available():
        _, user32, _ = _user32()
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
