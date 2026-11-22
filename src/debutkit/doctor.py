"""방송 준비 점검: 이 PC가 버튜버 방송을 시작할 준비가 됐는지 항목별로 확인한다.

각 점검은 :class:`System` 이 알려 주는 사실만 본다. 테스트는 ``System`` 의 함수를
가짜로 바꿔 실제 PC와 무관하게 결과를 확인한다. 점검은 아무것도 설치하거나 바꾸지
않으며 네트워크로는 이 PC 안의 포트(127.0.0.1)만 확인한다.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Mapping

OK, WARN, FAIL, INFO = "ok", "warn", "fail", "info"
LABELS = {OK: "정상", WARN: "주의", FAIL: "필요", INFO: "참고"}

OBS_WEBSOCKET_PORT = 4455
VTS_API_PORT = 8001  # VTube Studio 플러그인 API 기본 포트
OVERLAY_PORT = 8790  # debutkit overlay 기본 포트. 치지직 로그인은 8765 사용

SITE_URL = "https://budongjw.github.io/debutkit/"
SOFTWARE_URL = SITE_URL + "software.html"
JOIN_URL = SITE_URL + "join.html"

#: Steam 라이브러리의 ``steamapps/common`` 아래 폴더 이름과 표시 이름
STEAM_TRACKERS = {
    "VTube Studio": "VTube Studio (Live2D)",
    "Warudo": "Warudo (3D)",
    "VMagicMirror": "VMagicMirror (3D)",
    "VNyan": "VNyan (3D)",
    "PrprLive": "PrprLive (Live2D)",
}


@dataclass(frozen=True)
class Check:
    key: str
    title: str
    status: str
    detail: str = ""
    hint: str = ""


# --------------------------------------------------------------------------- 실제 PC를 보는 함수들


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _run(args: list[str]) -> str | None:
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=8, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _memory_gb() -> float | None:
    if sys.platform == "win32":
        import ctypes

        class _Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                        ("total_page", ctypes.c_ulonglong), ("avail_page", ctypes.c_ulonglong), ("total_virtual", ctypes.c_ulonglong),
                        ("avail_virtual", ctypes.c_ulonglong), ("avail_ext", ctypes.c_ulonglong)]

        status = _Status()
        status.length = ctypes.sizeof(_Status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
            return status.total / 1024**3
        return None
    try:
        pages, size = os.sysconf("SC_PHYS_PAGES"), os.sysconf("SC_PAGE_SIZE")
        return pages * size / 1024**3
    except (ValueError, OSError, AttributeError):
        return None


def _disk_free_gb(path: str) -> float | None:
    try:
        return shutil.disk_usage(path).free / 1024**3
    except OSError:
        return None


def _import_version(module: str) -> str | None:
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover
        return None
    try:
        return version(module)
    except PackageNotFoundError:
        return None


def _read_text(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _steam_root() -> str | None:
    if sys.platform != "win32":
        for guess in ("~/.steam/steam", "~/.local/share/Steam", "~/Library/Application Support/Steam"):
            if os.path.isdir(os.path.expanduser(guess)):
                return os.path.expanduser(guess)
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            return str(winreg.QueryValueEx(key, "SteamPath")[0])
    except OSError:
        fallback = os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Steam")
        return fallback if os.path.isdir(fallback) else None


#: Windows 소리 장치 속성 키: 장치 설명(마이크 등), 연결 이름(제품명)
_DEVICE_DESC = "{a45c254e-df1c-4efd-8020-67d146a850e0},2"
_DEVICE_IFACE = "{b3f8fa53-0004-438e-9003-51a46e139bfc},6"


def _audio_inputs() -> list[str] | None:
    """사용 가능한 마이크(소리 입력 장치) 이름. 확인할 수 없으면 ``None``."""
    if sys.platform == "win32":
        try:
            import winreg

            root = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture"
            names = []
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root) as capture:
                for index in range(winreg.QueryInfoKey(capture)[0]):
                    device = winreg.EnumKey(capture, index)
                    with winreg.OpenKey(capture, device) as key:
                        if winreg.QueryValueEx(key, "DeviceState")[0] != 1:  # 1: 사용 중(꺼짐, 분리, 없음 제외)
                            continue
                    try:
                        with winreg.OpenKey(capture, device + r"\Properties") as props:
                            desc = str(winreg.QueryValueEx(props, _DEVICE_DESC)[0])
                            iface = str(winreg.QueryValueEx(props, _DEVICE_IFACE)[0])
                    except OSError:
                        desc, iface = "마이크", ""
                    names.append(f"{desc} ({iface})" if iface else desc)
            return names
        except OSError:
            return None
    if sys.platform == "darwin":
        out = _run(["system_profiler", "SPAudioDataType", "-json"])
        try:
            items = json.loads(out or "")["SPAudioDataType"][0]["_items"]
        except (ValueError, KeyError, IndexError, TypeError):
            return None
        return [str(item.get("_name")) for item in items if item.get("coreaudio_device_input")]
    out = _run(["arecord", "-l"])
    if out is None:
        return None
    return re.findall(r"^card \d+: [^\[]*\[([^\]]+)\]", out, flags=re.M)


def _cameras() -> list[str] | None:
    """연결된 카메라 이름. 확인할 수 없으면 ``None``."""
    if sys.platform == "win32":
        out = _run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_PnPEntity -Filter \"PNPClass='Camera' OR PNPClass='Image'\" | Where-Object Status -eq 'OK' | "
                    "ForEach-Object Name"])
        return None if out is None else [line.strip() for line in out.splitlines() if line.strip()]
    if sys.platform == "darwin":
        out = _run(["system_profiler", "SPCameraDataType", "-json"])
        try:
            return [str(item.get("_name")) for item in json.loads(out or "")["SPCameraDataType"]]
        except (ValueError, KeyError, TypeError):
            return None
    folder = Path("/sys/class/video4linux")
    if not folder.is_dir():
        return None
    names = []
    for device in sorted(folder.iterdir()):
        name = _read_text(str(device / "name"))
        if name and name.strip() not in names:
            names.append(name.strip())
    return names


def _find_ffmpeg() -> str | None:
    from .tools import ffmpeg_path

    return ffmpeg_path()


def _gpu_names() -> list[str]:
    out = _run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
    if out:
        return [line.strip() for line in out.splitlines() if line.strip()]
    if sys.platform == "win32":
        out = _run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController).Name"])
    elif sys.platform == "darwin":
        out = _run(["system_profiler", "SPDisplaysDataType"])
        out = "\n".join(line.split(":", 1)[1] for line in (out or "").splitlines() if "Chipset Model" in line)
    else:
        out = _run(["sh", "-c", "lspci | grep -iE 'vga|3d'"])
    return [line.strip() for line in (out or "").splitlines() if line.strip()]


@dataclass
class System:
    """점검이 볼 수 있는 것. 모든 항목은 테스트에서 교체할 수 있다."""

    os_name: str = field(default_factory=platform.system)  # Windows / Darwin / Linux
    env: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))
    which: Callable[[str], str | None] = shutil.which
    exists: Callable[[str], bool] = os.path.exists
    port_open: Callable[[str, int], bool] = _port_open
    memory_gb: Callable[[], float | None] = _memory_gb
    cpu_count: Callable[[], int | None] = os.cpu_count
    disk_free_gb: Callable[[str], float | None] = _disk_free_gb
    gpu_names: Callable[[], list[str]] = _gpu_names
    package_version: Callable[[str], str | None] = _import_version
    steam_root: Callable[[], str | None] = _steam_root
    read_text: Callable[[str], str | None] = _read_text
    find_ffmpeg: Callable[[], str | None] = _find_ffmpeg  # PATH 밖에 다운로드한 ffmpeg까지 찾는다
    audio_inputs: Callable[[], list[str] | None] = _audio_inputs
    cameras: Callable[[], list[str] | None] = _cameras
    home: str = field(default_factory=lambda: str(Path.home()))


# --------------------------------------------------------------------------- 점검 항목


def check_hardware(system: System) -> list[Check]:
    found: list[Check] = []
    memory = system.memory_gb()
    if memory is None:
        found.append(Check("memory", "메모리", INFO, "확인하지 못함"))
    elif memory >= 15.5:
        found.append(Check("memory", "메모리", OK, f"{memory:.0f} GB"))
    elif memory >= 7.5:
        found.append(Check("memory", "메모리", WARN, f"{memory:.0f} GB", "트래킹, 게임, 송출 동시 실행 시 16 GB 이상 권장"))
    else:
        found.append(Check("memory", "메모리", FAIL, f"{memory:.0f} GB", "8 GB 미만은 송출 끊김 위험. 게임 없는 토크 방송부터 시작 권장"))
    cores = system.cpu_count()
    if cores is None:
        found.append(Check("cpu", "CPU", INFO, "확인하지 못함"))
    elif cores >= 6:
        found.append(Check("cpu", "CPU", OK, f"논리 코어 {cores}개"))
    elif cores >= 4:
        found.append(Check("cpu", "CPU", WARN, f"논리 코어 {cores}개", "x264(CPU) 인코딩 대신 그래픽카드 인코더(NVENC, AMF, QSV) 사용 권장"))
    else:
        found.append(Check("cpu", "CPU", FAIL, f"논리 코어 {cores}개", "트래킹과 송출 동시 실행 어려움"))
    gpus = system.gpu_names()
    if not gpus:
        found.append(Check("gpu", "그래픽카드", INFO, "확인하지 못함"))
    else:
        joined = ", ".join(gpus)
        if any(re.search(r"nvidia|geforce|rtx|gtx", name, re.I) for name in gpus):
            found.append(Check("gpu", "그래픽카드", OK, joined, "OBS 설정의 출력 탭에서 NVENC 인코더 선택 가능"))
        elif any(re.search(r"radeon|amd", name, re.I) for name in gpus):
            found.append(Check("gpu", "그래픽카드", OK, joined, "OBS 설정의 출력 탭에서 AMF 인코더 선택 가능"))
        elif any(re.search(r"apple|m\d", name, re.I) for name in gpus):
            found.append(Check("gpu", "그래픽카드", OK, joined, "OBS 설정의 출력 탭에서 Apple VT 하드웨어 인코더 선택 가능"))
        else:
            found.append(Check("gpu", "그래픽카드", WARN, joined, "내장 그래픽은 트래킹과 게임을 함께 실행하면 성능 부족 가능. Intel QSV 인코더 사용 권장"))
    videos = os.path.join(system.home, "Videos")
    free = system.disk_free_gb(videos if system.exists(videos) else system.home)
    if free is None:
        found.append(Check("disk", "저장 공간", INFO, "확인하지 못함"))
    elif free >= 50:
        found.append(Check("disk", "저장 공간", OK, f"여유 {free:.0f} GB"))
    elif free >= 10:
        found.append(Check("disk", "저장 공간", WARN, f"여유 {free:.0f} GB", "1080p 녹화는 1시간에 약 3에서 8 GB. 녹화본 보관 시 50 GB 이상 권장"))
    else:
        found.append(Check("disk", "저장 공간", FAIL, f"여유 {free:.0f} GB", "녹화, 리플레이 저장 실패 위험"))
    return found


def _names(found: list[str], limit: int = 2) -> str:
    return ", ".join(found[:limit]) + (f" 외 {len(found) - limit}개" if len(found) > limit else "")


def check_devices(system: System) -> list[Check]:
    """마이크(방송 필수)와 웹캠(얼굴 트래킹)."""
    found: list[Check] = []
    mics = system.audio_inputs()
    if mics is None:
        found.append(Check("mic", "마이크", INFO, "확인하지 못함"))
    elif mics:
        found.append(Check("mic", "마이크", OK, _names(mics)))
    else:
        found.append(Check("mic", "마이크", FAIL, "사용 가능한 입력 장치 없음",
                           "마이크 연결 후 운영체제 소리 설정에서 입력 장치 사용 여부 확인(꺼진 장치, 분리된 장치는 점검 대상에서 제외)"))
    cameras = system.cameras()
    if cameras is None:
        found.append(Check("camera", "웹캠", INFO, "확인하지 못함"))
    elif cameras:
        found.append(Check("camera", "웹캠", OK, _names(cameras)))
    else:
        found.append(Check("camera", "웹캠", WARN, "찾지 못함", "웹캠 얼굴 트래킹에 필요. 아이폰 얼굴 트래킹, PNGTuber는 불필요"))
    return found


def obs_paths(system: System) -> list[str]:
    if system.os_name == "Windows":
        program_files = system.env.get("ProgramFiles", r"C:\Program Files")
        paths = [os.path.join(program_files, "obs-studio", "bin", "64bit", "obs64.exe")]
        steam = system.steam_root()
        if steam:
            paths.append(os.path.join(steam, "steamapps", "common", "OBS Studio", "bin", "64bit", "obs64.exe"))
        return paths
    if system.os_name == "Darwin":
        return ["/Applications/OBS.app"]
    return [os.path.join(system.home, ".var", "app", "com.obsproject.Studio")]  # Flatpak


def check_obs(system: System) -> list[Check]:
    installed = next((path for path in obs_paths(system) if system.exists(path)), None) or system.which("obs") or system.which("obs64")
    if not installed:
        return [Check("obs", "OBS Studio", FAIL, "찾지 못함", "https://obsproject.com 에서 설치 (무료, GPL-2.0)")]
    found = [Check("obs", "OBS Studio", OK, installed)]
    if system.port_open("127.0.0.1", OBS_WEBSOCKET_PORT):
        found.append(Check("obs-websocket", "OBS 원격 제어", OK, f"127.0.0.1:{OBS_WEBSOCKET_PORT} 응답", "debutkit scenes 로 장면 세트 구성 가능"))
    else:
        found.append(Check("obs-websocket", "OBS 원격 제어", WARN, "응답 없음",
                           "OBS 실행 후 도구 메뉴의 WebSocket 서버 설정에서 WebSocket 서버 사용 체크(장면 자동 구성, 자동 클립에 필요)"))
    return found


def steam_libraries(system: System) -> list[str]:
    root = system.steam_root()
    if not root:
        return []
    libraries = [root]
    text = system.read_text(os.path.join(root, "steamapps", "libraryfolders.vdf")) or ""
    for path in re.findall(r'"path"\s+"([^"]+)"', text):
        path = path.replace("\\\\", "\\")
        if path not in libraries:
            libraries.append(path)
    return libraries


def check_tracking(system: System) -> list[Check]:
    names: list[str] = []
    for library in steam_libraries(system):
        for folder, title in STEAM_TRACKERS.items():
            if title not in names and system.exists(os.path.join(library, "steamapps", "common", folder)):
                names.append(title)
    if system.port_open("127.0.0.1", VTS_API_PORT) and "VTube Studio (Live2D)" not in names:
        names.append("VTube Studio (실행 중)")
    if names:
        found = [Check("tracking", "트래킹 프로그램", OK, ", ".join(names))]
    else:
        found = [Check("tracking", "트래킹 프로그램", WARN, "Steam에서 찾지 못함",
                       f"Live2D는 VTube Studio, 3D(VRM)는 VSeeFace, Warudo 등 사용. Steam 외 경로에 설치한 경우 해당 없음. 목록: {SOFTWARE_URL}")]
    if system.port_open("127.0.0.1", VTS_API_PORT):
        found.append(Check("vts-api", "VTube Studio API", OK, f"127.0.0.1:{VTS_API_PORT} 응답"))
    return found


def check_live_tools(system: System) -> list[Check]:
    """채팅 연결 모듈(OBS 제어, 채팅 수신, 자동 클립)과 ffmpeg(자동 클립)."""
    found: list[Check] = []
    version = system.package_version("stream2clip")
    if version:
        found.append(Check("live", "채팅 연결 모듈", OK, f"설치됨 ({version})"))
    else:
        found.append(Check("live", "채팅 연결 모듈", WARN, "설치 안 됨", 'pip install "debutkit[live]" (OBS 장면, 채팅창, 자동 클립에 필요)'))
    ffmpeg = system.which("ffmpeg") or system.find_ffmpeg()
    if ffmpeg:
        found.append(Check("ffmpeg", "ffmpeg", OK, str(ffmpeg)))
    else:
        from .tools import install_hint

        platform_name = {"Windows": "win32", "Darwin": "darwin"}.get(system.os_name, "linux")
        found.append(Check("ffmpeg", "ffmpeg", INFO, "찾지 못함", f"자동 클립에만 필요(방송에는 불필요). {install_hint(platform_name)}"))
    return found


def check_overlay_port(system: System, port: int = OVERLAY_PORT) -> list[Check]:
    if system.port_open("127.0.0.1", port):
        return [Check("overlay-port", "오버레이 포트", WARN, f"{port} 사용 중",
                      "debutkit overlay가 이미 실행 중이거나 다른 프로그램이 사용 중. 다른 프로그램인 경우 --port로 다른 번호 지정")]
    return [Check("overlay-port", "오버레이 포트", OK, f"{port} 사용 가능")]


def check_avatar(path: str, *, agency: bool) -> list[Check]:
    """VRM 모델 파일에 들어 있는 사용 조건 확인. 소속(기획사) 활동은 법인 사용으로 본다."""
    if not path.lower().endswith(".vrm"):
        return [Check("avatar", "아바타 사용 조건", INFO, os.path.basename(path),
                      "Live2D 등 VRM 외 모델은 판매처 약관 직접 확인: 영리 사용, 법인(기획사) 사용, 개변, 크레딧 표기")]
    try:
        from stream2clip.vrm import check_vrm, read_vrm_meta
    except ImportError:
        return [Check("avatar", "아바타 사용 조건", INFO, "채팅 연결 모듈 없음", 'pip install "debutkit[live]" 후 다시 실행')]
    try:
        meta = read_vrm_meta(path)
    except (OSError, ValueError) as error:
        return [Check("avatar", "아바타 사용 조건", FAIL, f"읽지 못함: {error}")]
    issues = check_vrm(meta, monetized=True, corporation=agency)
    errors = [issue.message for issue in issues if issue.level == "error"]
    warnings = [issue.message for issue in issues if issue.level == "warning"]
    if errors:
        return [Check("avatar", "아바타 사용 조건", FAIL, ", ".join(errors), "모델 제작자에게 사용 허락 요청 또는 다른 모델 사용")]
    if warnings:
        return [Check("avatar", "아바타 사용 조건", WARN, ", ".join(warnings))]
    return [Check("avatar", "아바타 사용 조건", OK, "수익화" + (", 법인(기획사) 사용" if agency else "") + " 허용")]


def run_checks(system: System | None = None, *, avatar: str | None = None, agency: bool = False, overlay_port: int = OVERLAY_PORT) -> list[Check]:
    system = system or System()
    found: list[Check] = []
    for step in (check_hardware, check_devices, check_obs, check_tracking, check_live_tools):
        try:
            found.extend(step(system))
        except Exception as error:  # 한 항목이 실패해도 나머지 점검은 계속
            found.append(Check(step.__name__, step.__name__, INFO, f"점검 중 오류: {error}"))
    found.extend(check_overlay_port(system, overlay_port))
    if avatar:
        found.extend(check_avatar(avatar, agency=agency))
    return found


def summary(checks: list[Check]) -> str:
    counts = {status: sum(1 for c in checks if c.status == status) for status in (OK, WARN, FAIL)}
    if counts[FAIL]:
        return f"준비 필요 {counts[FAIL]}건, 주의 {counts[WARN]}건. 필요 항목부터 해결"
    if counts[WARN]:
        return f"방송 가능. 주의 {counts[WARN]}건 확인 권장"
    return "방송 준비 완료"


def _display_width(text: str) -> int:
    """터미널에서 차지하는 칸 수. 한글 같은 전각 문자는 2칸."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def format_report(checks: list[Check]) -> str:
    width = max((_display_width(c.title) for c in checks), default=0)
    lines = ["debutkit doctor - 방송 준비 점검", ""]
    for check in checks:
        title = check.title + " " * (width - _display_width(check.title))
        lines.append(f"  [{LABELS.get(check.status, check.status)}] {title}  {check.detail}".rstrip())
        if check.hint and check.status != OK:
            lines.append(f"         조치: {check.hint}")
    lines += ["", summary(checks)]
    return "\n".join(lines)


def to_json(checks: list[Check]) -> str:
    return json.dumps([asdict(check) for check in checks], ensure_ascii=False, indent=2)
