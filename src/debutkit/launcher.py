"""방송 시작 버튼: 방송에 필요한 프로그램은 켜고, 방해되는 프로그램은 끈다. 방송이 끝나면 꺼 둔 프로그램을 다시 켠다.

- 세팅(방송, 게임, 작업 등)마다 켤 것(프로그램, 바로가기, 폴더, 사이트 주소)과 끌 것(프로그램 이름)을 정해 둔다
- 켜기를 누르면 끌 것을 먼저 끄고(창 닫기 요청 뒤 기다려도 남으면 강제 종료), 켤 것을 정한 간격으로 차례로 켠다
- 이미 켜진 프로그램은 다시 켜지 않는다. 기억한 창 위치와 크기가 있으면 그 자리로 옮긴다(Windows, 모니터가 없으면 건너뜀)
- 사이트는 브라우저의 새 창으로 열고 기억한 자리로 옮긴다
- 꺼 둔 프로그램이 방송 중에 다시 켜지면 알린다(선택: 다시 끄기). 방송 끝에는 꺼 둔 프로그램을 다시 켠다
- 운영체제, 보안 프로그램, debutkit 자신과 보호 목록의 프로그램은 끄지 않는다
- 설정은 설정 폴더의 ``launcher.json``, 이번 방송에서 끈 프로그램은 ``launcher-session.json`` (방송 끝에 다시 켜기용)
- 창 위치는 Windows만. macOS, Linux는 켜기, 끄기만(프로그램 이름 기준)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from . import settings

DATA = "launcher.json"
SESSION = "launcher-session.json"
KINDS = {"program": "프로그램", "shortcut": "바로가기", "folder": "폴더", "url": "사이트", "file": "파일"}
MAX_PROFILES = 20
MAX_ITEMS = 40
MAX_NAME = 30
DELAY = (0.0, 120.0)
DEFAULT_DELAY = 2.0
CLOSE_WAIT = 6.0  # 창 닫기 요청 뒤 강제 종료까지 기다리는 시간(초)
WINDOW_WAIT = 25.0  # 켠 뒤 창이 뜨기를 기다리는 시간(초)
#: 처음 사용할 때 만드는 세팅(비어 있음)
DEFAULT_PROFILES = ("방송",)
#: 끄지 않는 프로그램(소문자): 운영체제와 보안, 화면 구성, 소리. 사용자가 끌 것에 넣어도 건너뛴다
NEVER_STOP = frozenset({
    "system", "registry", "idle", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe", "lsaiso.exe",
    "svchost.exe", "explorer.exe", "dwm.exe", "fontdrvhost.exe", "sihost.exe", "ctfmon.exe", "taskhostw.exe", "runtimebroker.exe",
    "startmenuexperiencehost.exe", "shellexperiencehost.exe", "searchhost.exe", "searchapp.exe", "conhost.exe", "audiodg.exe",
    "spoolsv.exe", "msmpeng.exe", "nissrv.exe", "securityhealthservice.exe", "securityhealthsystray.exe", "smartscreen.exe",
    "taskmgr.exe", "lockapp.exe", "userinit.exe", "logonui.exe", "textinputhost.exe", "applicationframehost.exe", "dllhost.exe",
    "wudfhost.exe", "memory compression", "secure system", "debutkit.exe", "debutkit-gui.exe", "python.exe", "pythonw.exe",
    "launchd", "kernel_task", "windowserver", "loginwindow", "finder", "dock", "systemd", "init", "xorg", "gnome-shell", "kwin_x11", "kwin_wayland",
})
_URL = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)


class LauncherError(ValueError):
    """잘못된 세팅, 항목. 메시지는 한국어 안내."""


# --------------------------------------------------------------------------- 설정


@dataclass
class Item:
    """켤 것 하나. ``window`` 는 기억한 창 자리(Windows 창 배치 값: x, y, width, height, maximized)."""

    target: str
    kind: str = "program"
    args: str = ""
    delay: float = DEFAULT_DELAY  # 이 항목을 켠 뒤 다음 항목까지 기다리는 시간(초)
    window: dict[str, int] | None = None
    name: str = ""

    @property
    def label(self) -> str:
        return self.name or display_name(self.target, self.kind)


@dataclass
class Profile:
    name: str
    start: list[Item] = field(default_factory=list)
    stop: list[str] = field(default_factory=list)  # 프로그램 이름(예: Discord.exe) 또는 전체 경로
    skip_running: bool = True
    place_running: bool = False  # 이미 켜진 프로그램의 창도 기억한 자리로 옮김
    watch: bool = True  # 꺼 둔 프로그램이 다시 켜지면 알림
    rekill: bool = False  # 다시 켜지면 다시 끄기
    restore: bool = True  # 방송 끝에 꺼 둔 프로그램 다시 켜기
    overlay: bool = False  # 켠 뒤 debutkit 오버레이 시작(설정 마법사, 명령줄 --overlay)
    obs_check: bool = False  # 켠 뒤 OBS WebSocket 연결 확인


@dataclass
class Config:
    profiles: list[Profile] = field(default_factory=list)
    active: str = ""
    protect: list[str] = field(default_factory=list)  # 끄지 않을 프로그램(사용자 지정)

    def profile(self, name: str | None = None) -> Profile:
        wanted = name or self.active
        for profile in self.profiles:
            if profile.name == wanted:
                return profile
        if name:
            raise LauncherError(f"세팅 없음: {name} (있는 세팅: {', '.join(p.name for p in self.profiles) or '없음'})")
        return self.profiles[0]

    def to_dict(self) -> dict[str, Any]:
        return {"version": 1, "active": self.active, "protect": list(self.protect),
                "profiles": [{**asdict(profile), "start": [asdict(item) for item in profile.start]} for profile in self.profiles]}


def display_name(target: str, kind: str) -> str:
    if kind == "url":
        return re.sub(r"^https?://(www\.)?", "", target).split("/")[0] or target
    name = Path(target).name or target
    return name[:-4] if kind == "shortcut" and name.lower().endswith(".lnk") else name


def guess_kind(target: str, is_dir: Callable[[str], bool] = os.path.isdir) -> str:
    """끌어다 놓거나 입력한 값의 종류: 주소, 폴더, 바로가기(.lnk, .url), 프로그램(.exe 등), 그 밖의 파일."""
    text = target.strip()
    if _URL.match(text):
        return "url"
    if is_dir(text):
        return "folder"
    lower = text.lower()
    if lower.endswith((".lnk", ".url")):
        return "shortcut"
    if lower.endswith((".exe", ".bat", ".cmd", ".com", ".app")) or (not Path(text).suffix and sys.platform != "win32"):
        return "program"
    return "file"


def process_key(value: str) -> str:
    """끌 것, 보호 목록의 비교 이름: 경로면 파일 이름만, 소문자. Windows는 .exe가 없으면 붙인다."""
    name = Path(value.strip().strip('"')).name.lower()
    if sys.platform == "win32" and name and "." not in name:
        name += ".exe"
    return name


def _number(value: Any, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _window(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    try:
        found = {name: int(value[name]) for name in ("x", "y", "width", "height")}
    except (KeyError, TypeError, ValueError):
        return None
    if not (40 <= found["width"] <= 20000 and 40 <= found["height"] <= 20000 and abs(found["x"]) <= 40000 and abs(found["y"]) <= 40000):
        return None
    found["maximized"] = 1 if value.get("maximized") else 0
    return found


def check_item(data: Any) -> Item:
    """조작 화면, 명령줄, 저장 파일에서 받은 켤 것 하나. 틀리면 LauncherError."""
    if isinstance(data, str):
        data = {"target": data}
    if not isinstance(data, dict):
        raise LauncherError("켤 것의 형식이 올바르지 않음")
    target = str(data.get("target") or "").strip().strip('"')
    if not target:
        raise LauncherError("켤 것의 경로나 주소가 비어 있음")
    if len(target) > 2048:
        raise LauncherError("경로나 주소가 너무 김(2048자 이내)")
    kind = data.get("kind") or guess_kind(target)
    if kind not in KINDS:
        raise LauncherError(f"종류는 {', '.join(KINDS)} 중 하나")
    if kind == "url" and not _URL.match(target):
        raise LauncherError(f"사이트 주소는 http:// 또는 https://로 시작: {target[:40]}")
    delay = _number(data.get("delay", DEFAULT_DELAY), -1)
    if not DELAY[0] <= delay <= DELAY[1]:
        raise LauncherError(f"켜는 간격은 {DELAY[0]:g}초에서 {DELAY[1]:g}초 사이")
    args = str(data.get("args") or "").strip()
    if len(args) > 1024:
        raise LauncherError("실행 옵션은 1024자 이내")
    name = str(data.get("name") or "").strip()[:MAX_NAME]
    return Item(target=target, kind=kind, args=args if kind in ("program", "shortcut") else "", delay=round(delay, 1),
                window=_window(data.get("window")), name=name)


def check_name(name: Any) -> str:
    text = str(name or "").strip()
    if not text:
        raise LauncherError("세팅 이름이 비어 있음")
    if len(text) > MAX_NAME:
        raise LauncherError(f"세팅 이름은 {MAX_NAME}자 이내")
    return text


def check_profile(data: Any) -> Profile:
    if not isinstance(data, dict):
        raise LauncherError("세팅 형식이 올바르지 않음")
    name = check_name(data.get("name"))
    raw_start = data.get("start") or []
    raw_stop = data.get("stop") or []
    if not isinstance(raw_start, list) or not isinstance(raw_stop, list):
        raise LauncherError("켤 것, 끌 것은 목록")
    if len(raw_start) > MAX_ITEMS or len(raw_stop) > MAX_ITEMS:
        raise LauncherError(f"켤 것, 끌 것은 각각 {MAX_ITEMS}개까지")
    stop: list[str] = []
    for value in raw_stop:
        text = str(value or "").strip().strip('"')
        if text and process_key(text) not in {process_key(item) for item in stop}:
            stop.append(text)
    flags = {key: bool(data.get(key, default)) for key, default in (("skip_running", True), ("place_running", False), ("watch", True),
                                                                    ("rekill", False), ("restore", True), ("overlay", False), ("obs_check", False))}
    return Profile(name=name, start=[check_item(item) for item in raw_start], stop=stop, **flags)


def from_dict(data: Any) -> Config:
    """저장 파일. 손상된 세팅, 항목은 건너뛰고 세팅이 없으면 기본 세팅을 만든다."""
    data = data if isinstance(data, dict) else {}
    profiles: list[Profile] = []
    for raw in data.get("profiles") or []:
        if not isinstance(raw, dict):
            continue
        items = []
        for item in raw.get("start") or []:
            try:
                items.append(check_item(item))
            except LauncherError:
                continue
        try:
            profile = check_profile({**raw, "start": []})
        except LauncherError:
            continue
        profile.start = items[:MAX_ITEMS]
        if profile.name not in {p.name for p in profiles}:
            profiles.append(profile)
    if not profiles:
        profiles = [Profile(name) for name in DEFAULT_PROFILES]
    names = [p.name for p in profiles]
    active = data.get("active") if data.get("active") in names else names[0]
    protect = [str(value).strip() for value in data.get("protect") or [] if isinstance(value, str) and value.strip()]
    return Config(profiles=profiles[:MAX_PROFILES], active=active, protect=protect[:MAX_ITEMS])


def load() -> Config:
    return from_dict(settings.load_data(DATA))


def save(config: Config) -> Config:
    settings.save_data(DATA, config.to_dict())
    return config


def put_profile(config: Config, data: Any, *, old_name: str | None = None) -> Config:
    """세팅 추가 또는 바꾸기(``old_name`` 이 있으면 이름 변경 포함)."""
    profile = check_profile(data)
    names = [p.name for p in config.profiles]
    replacing = old_name if old_name in names else (profile.name if profile.name in names else None)
    if profile.name in names and profile.name != replacing:
        raise LauncherError(f"같은 이름의 세팅이 있음: {profile.name}")
    if replacing is None:
        if len(config.profiles) >= MAX_PROFILES:
            raise LauncherError(f"세팅은 {MAX_PROFILES}개까지")
        config.profiles.append(profile)
    else:
        config.profiles[names.index(replacing)] = profile
        if config.active == replacing:
            config.active = profile.name
    return config


def profile_dict(profile: Profile) -> dict[str, Any]:
    """세팅을 바꿀 때 쓰는 값(put_profile에 다시 넣을 수 있는 형식)."""
    return {**asdict(profile), "start": [asdict(item) for item in profile.start], "stop": list(profile.stop)}


def copy_profile(config: Config, name: str, new_name: Any) -> Config:
    """세팅 복제(창 위치 포함). 상황별 세팅을 금방 만들 때."""
    source = config.profile(name)
    data = {**asdict(source), "start": [asdict(item) for item in source.start], "name": check_name(new_name)}
    if data["name"] in {p.name for p in config.profiles}:
        raise LauncherError(f"같은 이름의 세팅이 있음: {data['name']}")
    return put_profile(config, data)


def remove_profile(config: Config, name: str) -> Config:
    config.profile(name)
    if len(config.profiles) == 1:
        raise LauncherError("세팅이 하나뿐이면 지울 수 없음")
    config.profiles = [p for p in config.profiles if p.name != name]
    if config.active == name:
        config.active = config.profiles[0].name
    return config


def export_text(config: Config) -> str:
    """다른 PC로 옮길 설정 백업(창 위치 포함)."""
    return json.dumps({"debutkit": "launcher", **config.to_dict()}, ensure_ascii=False, indent=2)


def import_text(text: str) -> Config:
    try:
        data = json.loads(text)
    except ValueError as error:
        raise LauncherError(f"백업 파일을 읽지 못함: {error}") from None
    if not isinstance(data, dict) or data.get("debutkit") != "launcher":
        raise LauncherError("debutkit 방송 시작 버튼 백업 파일이 아님")
    return from_dict(data)


# --------------------------------------------------------------------------- 운영체제


@dataclass(frozen=True)
class Proc:
    pid: int
    name: str
    path: str = ""

    @property
    def key(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class Window:
    handle: int
    pid: int
    title: str
    class_name: str = ""


class System:
    """프로그램 목록, 켜기, 끄기, 창 다루기. 운영체제마다 구현이 다르고 테스트는 가짜로 바꾼다."""

    can_place = False

    def processes(self) -> list[Proc]:
        if sys.platform == "win32":
            return _win_processes()
        try:
            output = subprocess.run(["ps", "-axo", "pid=,comm="], capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        found = []
        for line in output.splitlines():
            pid, _, command = line.strip().partition(" ")
            if pid.isdigit() and command.strip():
                found.append(Proc(int(pid), Path(command.strip()).name, command.strip()))
        return found

    def launch(self, item: Item) -> None:
        """켜기. 실패하면 OSError."""
        target = os.path.expandvars(item.target)
        if item.kind == "url":
            browser = _browser()
            if browser:
                subprocess.Popen([browser, "--new-window", target], **_detached())
                return
        if sys.platform == "win32":
            folder = str(Path(target).parent) if item.kind == "program" and Path(target).parent.is_dir() else None
            os.startfile(target, "open", item.args or "", folder)  # type: ignore[attr-defined]  # 바로가기, 폴더, 주소, 문서 모두
            return
        if item.kind == "program" and not target.endswith(".app"):
            subprocess.Popen([target, *_split(item.args)], cwd=str(Path(target).parent) if Path(target).parent.is_dir() else None, **_detached())
            return
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, target], **_detached())

    def close(self, proc: Proc, force: bool) -> None:
        if sys.platform == "win32":
            command = ["taskkill", "/PID", str(proc.pid), "/T"] + (["/F"] if force else [])
            subprocess.run(command, capture_output=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return
        import signal

        os.kill(proc.pid, signal.SIGKILL if force else signal.SIGTERM)

    def windows(self) -> list[Window]:
        return []

    def placement(self, window: Window) -> dict[str, int] | None:
        return None

    def place(self, window: Window, rect: dict[str, int]) -> bool:
        return False

    def on_screen(self, rect: dict[str, int]) -> bool:
        return True


def _split(args: str) -> list[str]:
    import shlex

    try:
        return shlex.split(args)
    except ValueError:
        return args.split()


def _detached() -> dict[str, Any]:
    if sys.platform == "win32":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0x8) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
        return {"creationflags": flags, "close_fds": True, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    return {"start_new_session": True, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}


def _browser() -> str | None:
    if sys.platform != "win32":
        return None
    from .program_window import find_browser

    return find_browser()


def _win_processes() -> list[Proc]:  # pragma: no cover - Windows 전용(실제 PC에서 확인)
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.OpenProcess.restype = wintypes.HANDLE
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)
    if not snapshot or snapshot == wintypes.HANDLE(-1).value:
        return []
    found: list[Proc] = []
    entry = Entry()
    entry.dwSize = ctypes.sizeof(Entry)
    try:
        ok = kernel32.Process32FirstW(wintypes.HANDLE(snapshot), ctypes.byref(entry))
        while ok:
            pid = int(entry.th32ProcessID)
            path = ""
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if handle:
                buffer = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(1024)
                if kernel32.QueryFullProcessImageNameW(wintypes.HANDLE(handle), 0, buffer, ctypes.byref(size)):
                    path = buffer.value
                kernel32.CloseHandle(wintypes.HANDLE(handle))
            found.append(Proc(pid, entry.szExeFile, path))
            ok = kernel32.Process32NextW(wintypes.HANDLE(snapshot), ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(wintypes.HANDLE(snapshot))
    return found


class WindowsSystem(System):  # pragma: no cover - Windows 전용(실제 PC에서 확인)
    """창 목록(보이는 최상위 창), 창 배치 기억과 복원(SetWindowPlacement: 최대화, 모니터 포함)."""

    can_place = True

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self.ctypes, self.wintypes = ctypes, wintypes
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)

        class Placement(ctypes.Structure):
            _fields_ = [("length", wintypes.UINT), ("flags", wintypes.UINT), ("showCmd", wintypes.UINT), ("ptMinPosition", wintypes.POINT),
                        ("ptMaxPosition", wintypes.POINT), ("rcNormalPosition", wintypes.RECT)]

        self.Placement = Placement
        self.user32.GetWindowPlacement.argtypes = [wintypes.HWND, ctypes.POINTER(Placement)]
        self.user32.SetWindowPlacement.argtypes = [wintypes.HWND, ctypes.POINTER(Placement)]
        self.user32.MonitorFromRect.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD]
        self.user32.MonitorFromRect.restype = wintypes.HANDLE

    def windows(self) -> list[Window]:
        ctypes, wintypes, user32 = self.ctypes, self.wintypes, self.user32
        found: list[Window] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(handle: int, _: int) -> bool:
            if not user32.IsWindowVisible(handle) or user32.GetWindow(handle, 4):  # GW_OWNER: 대화상자 등 딸린 창 제외
                return True
            if user32.GetWindowLongW(handle, -20) & 0x80:  # WS_EX_TOOLWINDOW
                return True
            length = user32.GetWindowTextLengthW(handle)
            if length <= 0:
                return True
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(handle, title, length + 1)
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(handle, class_name, 256)
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
            found.append(Window(int(handle), int(pid.value), title.value, class_name.value))
            return True

        user32.EnumWindows(visit, 0)
        return found

    def placement(self, window: Window) -> dict[str, int] | None:
        placement = self.Placement()
        placement.length = self.ctypes.sizeof(self.Placement)
        if not self.user32.GetWindowPlacement(window.handle, self.ctypes.byref(placement)):
            return None
        rect = placement.rcNormalPosition
        return _window({"x": rect.left, "y": rect.top, "width": rect.right - rect.left, "height": rect.bottom - rect.top,
                        "maximized": placement.showCmd == 3})

    def place(self, window: Window, rect: dict[str, int]) -> bool:
        placement = self.Placement()
        placement.length = self.ctypes.sizeof(self.Placement)
        if not self.user32.GetWindowPlacement(window.handle, self.ctypes.byref(placement)):
            return False
        placement.rcNormalPosition = self.wintypes.RECT(rect["x"], rect["y"], rect["x"] + rect["width"], rect["y"] + rect["height"])
        placement.showCmd = 3 if rect.get("maximized") else 1  # SW_SHOWMAXIMIZED, SW_SHOWNORMAL
        placement.flags = 0
        return bool(self.user32.SetWindowPlacement(window.handle, self.ctypes.byref(placement)))

    def on_screen(self, rect: dict[str, int]) -> bool:
        """기억한 자리가 지금 연결된 모니터에 걸치는지(모니터를 뺀 경우 옮기지 않음)."""
        area = self.wintypes.RECT(rect["x"], rect["y"], rect["x"] + rect["width"], rect["y"] + rect["height"])
        return bool(self.user32.MonitorFromRect(self.ctypes.byref(area), 0))  # MONITOR_DEFAULTTONULL


def default_system() -> System:
    return WindowsSystem() if sys.platform == "win32" else System()


# --------------------------------------------------------------------------- 실행


@dataclass
class Step:
    """실행 결과 한 줄. ``state``: started, skipped, stopped, forced, protected, missing, failed, placed, info"""

    state: str
    label: str
    detail: str = ""

    def text(self) -> str:
        words = {"started": "켬", "skipped": "이미 켜짐", "stopped": "끔", "forced": "강제로 끔", "protected": "보호(끄지 않음)",
                 "missing": "켜져 있지 않음", "failed": "실패", "placed": "창 위치 맞춤", "restored": "다시 켬", "info": "안내"}
        return f"{words.get(self.state, self.state)}: {self.label}" + (f" ({self.detail})" if self.detail else "")


def program_key(item: Item, resolve: Callable[[str], str | None] | None = None) -> str | None:
    """켤 것이 실행하는 프로그램 이름(이미 켜졌는지, 창 찾기에 사용). 바로가기는 대상 경로를 풀어서. 알 수 없으면 None."""
    if item.kind == "program":
        return process_key(item.target)
    if item.kind == "shortcut" and item.target.lower().endswith(".lnk"):
        target = (resolve or resolve_shortcut)(item.target)
        return process_key(target) if target and target.lower().endswith(".exe") else None
    if item.kind == "url":
        browser = _browser()
        return process_key(browser) if browser else None
    if item.kind == "folder" and sys.platform == "win32":
        return "explorer.exe"
    return None


def resolve_shortcut(path: str) -> str | None:  # pragma: no cover - Windows 전용
    """Windows 바로가기(.lnk)의 대상 경로. 실패하면 None."""
    if sys.platform != "win32" or not Path(path).is_file():
        return None
    script = "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($args[0]); [Console]::Out.Write($s.TargetPath)"
    try:
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script, path], capture_output=True, text=True,
                                timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    target = result.stdout.strip()
    return target or None


def blocked(name: str, config: Config) -> bool:
    """끄면 안 되는 프로그램인지(운영체제, 보안, debutkit 자신, 보호 목록)."""
    key = process_key(name)
    own = process_key(sys.executable)
    return key in NEVER_STOP or key == own or key in {process_key(value) for value in config.protect}


def matches(proc: Proc, wanted: str) -> bool:
    """끌 것 하나(이름 또는 전체 경로)에 맞는 프로그램인지."""
    wanted = wanted.strip().strip('"')
    if any(sep in wanted for sep in ("\\", "/")) and proc.path:
        return os.path.normcase(os.path.normpath(proc.path)) == os.path.normcase(os.path.normpath(wanted))
    return proc.key == process_key(wanted)


class Launcher:
    """세팅 하나를 켜고(``run``) 끝낸다(``end``). ``report`` 는 진행 상황을 한 줄씩 받는 함수."""

    def __init__(self, config: Config | None = None, system: System | None = None, *, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, resolve: Callable[[str], str | None] | None = None,
                 report: Callable[[Step], None] | None = None) -> None:
        self.config = config or load()
        self.system = system or default_system()
        self.sleep, self.clock = sleep, clock
        self.resolve = resolve
        self.report = report or (lambda step: None)
        self.steps: list[Step] = []

    def _add(self, state: str, label: str, detail: str = "") -> Step:
        step = Step(state, label, detail)
        self.steps.append(step)
        self.report(step)
        return step

    # ------------------------------------------------------------------ 끄기
    def stop_programs(self, profile: Profile, *, close_wait: float = CLOSE_WAIT) -> list[Proc]:
        """끌 것을 끈다: 먼저 창 닫기 요청, ``close_wait`` 초 안에 남으면 강제 종료. 끈 프로그램 목록(다시 켜기용)."""
        running = self.system.processes()
        closed: list[Proc] = []
        for wanted in profile.stop:
            label = Path(wanted).name
            if blocked(wanted, self.config):
                self._add("protected", label, "운영체제, 보안 프로그램, debutkit, 보호 목록은 끄지 않음")
                continue
            targets = [proc for proc in running if matches(proc, wanted)]
            if not targets:
                self._add("missing", label)
                continue
            for proc in targets:
                try:
                    self.system.close(proc, force=False)
                except (OSError, subprocess.SubprocessError):
                    pass
            deadline = self.clock() + close_wait
            left = targets
            while left and self.clock() < deadline:
                self.sleep(0.5)
                alive = {proc.pid for proc in self.system.processes()}
                left = [proc for proc in left if proc.pid in alive]
            forced = False
            for proc in left:
                try:
                    self.system.close(proc, force=True)
                    forced = True
                except (OSError, subprocess.SubprocessError) as error:
                    self._add("failed", label, f"끄지 못함: {error}")
            self._add("forced" if forced else "stopped", label, f"{len(targets)}개" if len(targets) > 1 else "")
            closed.extend(targets)
        return closed

    # ------------------------------------------------------------------ 켜기
    def start_programs(self, profile: Profile, *, window_wait: float = WINDOW_WAIT) -> list[str]:
        """켤 것을 차례로 켠다. 켠 항목의 표시 이름 목록."""
        started: list[str] = []
        pending: list[tuple[Item, str | None, set[int]]] = []  # 창 자리를 맞출 항목(프로그램 이름, 켜기 전 창들)
        for index, item in enumerate(profile.start):
            key = program_key(item, self.resolve)
            running = {proc.key for proc in self.system.processes()}
            if _missing(item):
                self._add("failed", item.label, "파일이나 폴더가 없음(옮기거나 지웠는지 확인)")
                continue
            if profile.skip_running and key and item.kind in ("program", "shortcut") and key in running:
                self._add("skipped", item.label)
                if profile.place_running and item.window:
                    self._place_now(item, key)
                continue
            before = {window.handle for window in self.system.windows()} if item.window and self.system.can_place else set()
            try:
                self.system.launch(item)
            except OSError as error:
                self._add("failed", item.label, str(error))
                continue
            self._add("started", item.label)
            started.append(item.label)
            if item.window and self.system.can_place:
                pending.append((item, key, before))
            if index < len(profile.start) - 1 and item.delay:
                self._wait_and_place(pending, item.delay)
        self._wait_and_place(pending, window_wait, until_done=True)
        for item, _, _ in pending:
            self._add("info", item.label, "창을 찾지 못해 자리를 맞추지 못함")
        return started

    def _place_now(self, item: Item, key: str) -> None:
        if not (self.system.can_place and item.window and self.system.on_screen(item.window)):
            return
        pids = {proc.pid for proc in self.system.processes() if proc.key == key}
        for window in self.system.windows():
            if window.pid in pids and self.system.place(window, item.window):
                self._add("placed", item.label)
                return

    def _wait_and_place(self, pending: list[tuple[Item, str | None, set[int]]], seconds: float, *, until_done: bool = False) -> None:
        """기다리는 동안 켠 프로그램의 새 창이 뜨면 기억한 자리로 옮긴다."""
        deadline = self.clock() + seconds
        while True:
            if pending:
                self._place_pending(pending)
            if self.clock() >= deadline or (until_done and not pending):
                return
            self.sleep(min(0.5, max(0.0, deadline - self.clock())))

    def _place_pending(self, pending: list[tuple[Item, str | None, set[int]]]) -> None:
        windows = self.system.windows()
        procs = {proc.pid: proc.key for proc in self.system.processes()}
        for entry in list(pending):
            item, key, before = entry
            assert item.window is not None
            if not self.system.on_screen(item.window):
                self._add("info", item.label, "기억한 모니터가 연결되어 있지 않아 자리를 맞추지 않음")
                pending.remove(entry)
                continue
            fresh = [window for window in windows if window.handle not in before and (key is None or procs.get(window.pid) == key)]
            if item.kind == "folder":
                folder = Path(item.target).name.lower()
                fresh = [window for window in fresh if window.title.lower() == folder or window.class_name == "CabinetWClass"]
            if fresh and self.system.place(fresh[0], item.window):
                self._add("placed", item.label)
                pending.remove(entry)

    # ------------------------------------------------------------------ 전체
    def run(self, name: str | None = None) -> list[Step]:
        """세팅 켜기: 끌 것을 먼저 끄고 켤 것을 차례로 켠다. 끈 프로그램은 방송 끝에 다시 켜도록 기록."""
        profile = self.config.profile(name)
        self.steps = []
        closed = self.stop_programs(profile)
        previous = load_session()
        killed = {item["key"]: item for item in previous.get("killed", []) if isinstance(item, dict) and item.get("key")}
        for proc in closed:
            if proc.key not in killed:
                killed[proc.key] = {"key": proc.key, "name": proc.name, "path": proc.path}
        save_session({"profile": profile.name, "time": time.time(), "killed": list(killed.values())})
        self.start_programs(profile)
        return self.steps

    def end(self, name: str | None = None, *, restore: bool | None = None) -> list[Step]:
        """방송 끝: 이번 방송에 끈 프로그램을 다시 켠다(세팅에서 끈 경우 건너뜀). 기록은 지운다."""
        profile = self.config.profile(name)
        self.steps = []
        session = load_session()
        wanted = profile.restore if restore is None else restore
        if wanted:
            running = {proc.key for proc in self.system.processes()}
            for item in session.get("killed", []):
                if not isinstance(item, dict):
                    continue
                label = str(item.get("name") or item.get("key") or "")
                path = str(item.get("path") or "")
                if str(item.get("key")) in running:
                    self._add("skipped", label)
                elif not path or not Path(path).is_file():
                    self._add("info", label, "경로를 몰라 다시 켜지 못함")
                else:
                    try:
                        self.system.launch(Item(target=path, kind="program"))
                        self._add("restored", label)
                    except OSError as error:
                        self._add("failed", label, str(error))
        clear_session()
        return self.steps


def _missing(item: Item) -> bool:
    """경로로 적은 켤 것이 없어졌는지. 이름만 적은 프로그램(PATH에서 찾음)과 주소는 확인하지 않는다."""
    if item.kind == "url":
        return False
    target = Path(os.path.expandvars(item.target))
    return target.is_absolute() and not target.exists()


def load_session() -> dict[str, Any]:
    return settings.load_data(SESSION)


def save_session(values: dict[str, Any]) -> None:
    settings.save_data(SESSION, values)


def clear_session() -> None:
    try:
        settings.data_path(SESSION).unlink()
    except OSError:
        pass


def remember_windows(config: Config, name: str | None = None, system: System | None = None,
                     resolve: Callable[[str], str | None] | None = None) -> list[Step]:
    """지금 켜져 있는 켤 것들의 창 자리와 크기를 기억한다(Windows). 프로그램마다 가장 큰 창."""
    system = system or default_system()
    profile = config.profile(name)
    steps: list[Step] = []
    if not system.can_place:
        return [Step("info", "창 위치", "Windows에서만 기억")]
    windows = system.windows()
    procs = {proc.pid: proc.key for proc in system.processes()}
    for item in profile.start:
        key = program_key(item, resolve)
        candidates = [window for window in windows if key and procs.get(window.pid) == key]
        if item.kind == "folder":
            candidates = [window for window in candidates if window.title.lower() == Path(item.target).name.lower()]
        best, best_area = None, -1
        for window in candidates:
            rect = system.placement(window)
            if rect and rect["width"] * rect["height"] > best_area:
                best, best_area = rect, rect["width"] * rect["height"]
        if best is None:
            steps.append(Step("missing", item.label, "켜진 창 없음(위치를 지우지 않고 유지)"))
            continue
        item.window = best
        steps.append(Step("placed", item.label, f"{best['x']},{best['y']} {best['width']}x{best['height']}" + (" 최대화" if best["maximized"] else "")))
    return steps


class Watcher:
    """끌 것이 방송 중에 다시 켜지면 알린다(``rekill`` 이면 다시 끔). ``interval`` 초마다 확인."""

    def __init__(self, profile: Profile, config: Config, notify: Callable[[str], None], system: System | None = None, interval: float = 3.0) -> None:
        self.profile, self.config, self.notify = profile, config, notify
        self.system = system or default_system()
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._seen: set[int] = set()

    def check(self) -> list[Proc]:
        """한 번 확인: 새로 켜진 끌 것 목록."""
        wanted = [name for name in self.profile.stop if not blocked(name, self.config)]
        found = [proc for proc in self.system.processes() if any(matches(proc, name) for name in wanted)]
        fresh = [proc for proc in found if proc.pid not in self._seen]
        self._seen = {proc.pid for proc in found}
        names = sorted({proc.name for proc in fresh})
        if names:
            if self.profile.rekill:
                for proc in fresh:
                    try:
                        self.system.close(proc, force=True)
                    except (OSError, subprocess.SubprocessError):
                        pass
                self.notify(f"꺼 둔 프로그램이 다시 켜져 다시 끔: {', '.join(names)}")
            else:
                self.notify(f"꺼 둔 프로그램이 다시 켜짐: {', '.join(names)}")
        return fresh

    def start(self) -> "Watcher":
        self._seen = {proc.pid for proc in self.system.processes() if any(matches(proc, name) for name in self.profile.stop)}
        self._thread = threading.Thread(target=self._loop, name="launcher-watch", daemon=True)
        self._thread.start()
        return self

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.check()
            except Exception:  # 목록 조회 실패는 다음 확인에서 다시
                pass

    def stop(self) -> None:
        self._stop.set()


def wait_for_port(host: str, port: int, timeout: float, *, clock: Callable[[], float] = time.monotonic,
                  sleep: Callable[[float], None] = time.sleep) -> bool:
    """OBS WebSocket처럼 켠 프로그램이 연결을 받을 때까지 기다린다(이 PC 안의 주소만)."""
    import socket

    deadline = clock() + timeout
    while True:
        try:
            with socket.create_connection((host, int(port)), timeout=1.0):
                return True
        except OSError:
            if clock() >= deadline:
                return False
            sleep(1.0)


def summary(steps: Iterable[Step]) -> str:
    return "\n".join(step.text() for step in steps) or "할 일이 없음: 켤 것, 끌 것을 추가"
