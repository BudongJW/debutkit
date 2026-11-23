"""OBS 없이 바로 방송(Windows): 송출 화면 창을 ffmpeg로 캡처해 치지직, SOOP, YouTube, Twitch로 보낸다.

- 송출 화면(``/program``): 캐릭터, 채팅, 알림, 추첨, 휴대폰 카메라(앱)를 1920x1080 한 화면에 모은 페이지.
  Edge(없으면 Chrome) 앱 창으로 연다(program_window.py). 이 창이 방송 미리보기
- 영상: ffmpeg ``gfxcapture`` (Windows Graphics Capture)로 그 창만 캡처. 다른 창에 가려져도 되지만 최소화하면 멈춘다
- 인코더: 이 PC에서 실제로 되는 하드웨어 H.264(NVIDIA NVENC, Intel Quick Sync, AMD AMF)를 먼저, 없으면 x264(CPU)
- 소리: 마이크(DirectShow 녹음 장치)와 추가 장치 하나(예: 스테레오 믹스)를 섞는다. 고르지 않으면 무음
- 스트림 키: Windows DPAPI로 이 Windows 사용자만 풀 수 있게 암호화해 설정 폴더(``broadcast-keys.json``)에 저장.
  상태, 오류 문장에서는 가린다
- 연결이 끊기면(오래 방송한 뒤) 몇 번 다시 연결한다. 시작하자마자 실패하면(키, 주소 오류) 멈추고 이유를 알려 준다
- 게임 화면 캡처, 장면 전환은 없다(토크 방송용). 게임 방송은 OBS 사용
"""

from __future__ import annotations

import base64
import json
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
from collections import deque
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import IO, Any, Callable

from . import program_window, settings


class BroadcastError(ValueError):
    """잘못된 방송 설정이나 시작할 수 없는 상태. 메시지는 한국어 안내."""


@dataclass(frozen=True)
class Platform:
    id: str
    name: str
    server: str  # 기본 송출 서버. 비어 있으면 방송 플랫폼 화면에서 복사해 넣는다
    max_kbps: int  # 영상 비트레이트 상한(플랫폼 권장)
    keyframe: int  # 키프레임 간격(초)
    hint: str  # 스트림 키를 찾는 곳


PLATFORMS: dict[str, Platform] = {
    "chzzk": Platform("chzzk", "치지직", "", 8000, 1, "치지직 스튜디오의 방송 설정 화면에 있는 스트림 URL과 스트림 키"),
    "soop": Platform("soop", "SOOP", "", 8000, 2, "SOOP 방송 설정의 외부 기기 방송 화면에 있는 서버 URL과 스트림 키"),
    "youtube": Platform("youtube", "YouTube", "rtmps://a.rtmps.youtube.com/live2", 12000, 2, "YouTube Studio의 라이브 스트리밍 화면에 있는 스트림 키"),
    "twitch": Platform("twitch", "Twitch", "rtmps://live.twitch.tv:443/app", 6000, 2, "Twitch 크리에이터 대시보드 설정의 스트림 화면에 있는 기본 스트림 키"),
    "custom": Platform("custom", "직접 입력", "", 20000, 2, "송출 서버 주소(rtmp:// 또는 rtmps://)와 스트림 키"),
}


@dataclass(frozen=True)
class Quality:
    id: str
    name: str
    width: int
    height: int
    fps: int
    kbps: int


QUALITIES: dict[str, Quality] = {
    "720p30": Quality("720p30", "720p 30fps(가벼움, 권장)", 1280, 720, 30, 4500),
    "1080p30": Quality("1080p30", "1080p 30fps", 1920, 1080, 30, 6000),
    "1080p60": Quality("1080p60", "1080p 60fps(무거움)", 1920, 1080, 60, 8000),
}
STAGE = (1920, 1080)  # 송출 화면 페이지의 무대 크기(program.html)
#: 찾는 순서: 하드웨어 인코더, x264, Windows 기본(Media Foundation)
ENCODERS = ("h264_nvenc", "h264_qsv", "h264_amf", "libx264", "h264_mf")
ENCODER_NAMES = {"h264_nvenc": "NVIDIA NVENC", "h264_qsv": "Intel Quick Sync", "h264_amf": "AMD AMF", "libx264": "x264(CPU)", "h264_mf": "Media Foundation"}
AUDIO_KBPS = 160
KBPS_RANGE = (500, 20000)
SPEED_WINDOW = 10.0  # 초. 송출 속도(실시간 대비)를 계산하는 구간
TITLE_LIMIT = 40
DEVICE_LIMIT = 300
KEY_LIMIT = 256
SERVER_LIMIT = 300
_HEX = re.compile(r"^[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class BroadcastConfig:
    platform: str = "chzzk"
    servers: dict[str, str] = field(default_factory=dict)  # 플랫폼별 송출 서버. 없으면 플랫폼 기본 서버
    quality: str = "720p30"
    kbps: int = 0  # 0이면 화질 기본값(플랫폼 상한 이하)
    encoder: str = "auto"
    mic: str = ""  # DirectShow 녹음 장치(대체 이름). 비면 무음
    extra_audio: str = ""  # 함께 섞을 장치(스테레오 믹스 등)
    camera: bool = False  # 휴대폰 앱 카메라 영상을 크게
    title: str = ""  # 송출 화면 왼쪽 위 글자
    background: str = "2a1f3d"

    @property
    def target(self) -> Platform:
        return PLATFORMS[self.platform]

    @property
    def size(self) -> Quality:
        return QUALITIES[self.quality]

    @property
    def server(self) -> str:
        """지금 플랫폼에 직접 넣은 송출 서버(없으면 빈 값)."""
        return self.servers.get(self.platform, "")

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "server": self.server}

    def server_url(self) -> str:
        return (self.server or self.target.server).rstrip("/")

    def video_kbps(self) -> int:
        wanted = self.kbps or self.size.kbps
        return min(wanted, self.target.max_kbps)


def config_path() -> Path:
    return settings.settings_path().parent / "broadcast.json"


def keys_path() -> Path:
    return settings.settings_path().parent / "broadcast-keys.json"


def profile_path() -> Path:
    """송출 화면 창 전용 브라우저 프로필."""
    return settings.settings_path().parent / "program-browser"


def check_platform(value: Any) -> str:
    if value not in PLATFORMS:
        raise BroadcastError("방송 플랫폼은 " + ", ".join(f"{key}({item.name})" for key, item in PLATFORMS.items()) + " 중 하나")
    return str(value)


def check_server(value: Any) -> str:
    """송출 서버 주소(rtmp://, rtmps://). 빈 값은 플랫폼 기본 서버."""
    if not isinstance(value, str):
        raise BroadcastError("송출 서버 주소는 문자열")
    text = value.strip()
    if not text:
        return ""
    parsed = urllib.parse.urlsplit(text)
    if (parsed.scheme not in ("rtmp", "rtmps") or not parsed.hostname or len(text) > SERVER_LIMIT
            or any(ch.isspace() or ord(ch) < 32 for ch in text)):
        raise BroadcastError("송출 서버 주소는 rtmp:// 또는 rtmps:// 로 시작하는 주소(방송 플랫폼의 방송 설정 화면에서 복사)")
    return text.rstrip("/")


def check_quality(value: Any) -> str:
    if value not in QUALITIES:
        raise BroadcastError("화질은 " + ", ".join(QUALITIES) + " 중 하나")
    return str(value)


def check_kbps(value: Any) -> int:
    low, high = KBPS_RANGE
    if isinstance(value, bool) or not isinstance(value, int) or not (value == 0 or low <= value <= high):
        raise BroadcastError(f"영상 비트레이트는 0(자동) 또는 {low}에서 {high} 사이의 정수(kbps)")
    return value


def check_encoder(value: Any) -> str:
    if value != "auto" and value not in ENCODERS:
        raise BroadcastError("인코더는 auto 또는 " + ", ".join(ENCODERS) + " 중 하나")
    return str(value)


def check_device(value: Any) -> str:
    if not isinstance(value, str) or len(value) > DEVICE_LIMIT or any(ch in value for ch in '"\r\n\0'):
        raise BroadcastError("소리 장치 이름이 올바르지 않음(debutkit broadcast devices로 목록 확인)")
    return value.strip()


def check_title(value: Any) -> str:
    if not isinstance(value, str):
        raise BroadcastError("화면 글자는 문자열")
    text = " ".join(value.split())
    if len(text) > TITLE_LIMIT:
        raise BroadcastError(f"화면 글자는 {TITLE_LIMIT}자 이하")
    return text


def check_color(value: Any) -> str:
    text = value.strip().lstrip("#") if isinstance(value, str) else ""
    if not _HEX.match(text):
        raise BroadcastError("배경색은 16진수 6자리(예: 2a1f3d)")
    return text.lower()


def check_key(value: Any) -> str:
    """스트림 키: 공백 없는 영문, 숫자, 기호(복사할 때 붙은 앞뒤 공백은 지운다)."""
    text = value.strip() if isinstance(value, str) else ""
    if not 4 <= len(text) <= KEY_LIMIT or any(not 33 <= ord(ch) <= 126 for ch in text) or "/" in text:
        raise BroadcastError("스트림 키가 올바르지 않음: 방송 플랫폼 화면의 스트림 키를 그대로 복사해 붙여 넣기")
    return text


_CHECKS: dict[str, Callable[[Any], Any]] = {"platform": check_platform, "quality": check_quality, "kbps": check_kbps, "encoder": check_encoder,
                                            "mic": check_device, "extra_audio": check_device, "title": check_title, "background": check_color}


def from_request(data: dict[str, Any], base: BroadcastConfig | None = None) -> BroadcastConfig:
    """요청에 들어 있는 항목만 바꾼 설정. ``server`` 는 (바꾼 뒤의) 플랫폼의 송출 서버. 잘못된 값은 ``BroadcastError``."""
    config = base or BroadcastConfig()
    changes: dict[str, Any] = {}
    for name, check in _CHECKS.items():
        if name in data and data[name] is not None:
            changes[name] = check(data[name])
    if "camera" in data:
        if not isinstance(data["camera"], bool):
            raise BroadcastError("camera는 true 또는 false")
        changes["camera"] = data["camera"]
    if data.get("server") is not None:
        servers = dict(config.servers)
        platform = changes.get("platform", config.platform)
        servers[platform] = check_server(data["server"])
        changes["servers"] = {name: url for name, url in servers.items() if url}
    return replace(config, **changes)


def load_config(path: Path | None = None) -> BroadcastConfig:
    """저장한 설정. 없거나 잘못된 항목은 기본값."""
    path = path or config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    config = BroadcastConfig()
    for name in (*_CHECKS, "camera"):
        if name in data:
            try:
                config = from_request({name: data[name]}, config)
            except BroadcastError:
                pass
    servers = data.get("servers")
    for platform, url in (servers.items() if isinstance(servers, dict) else ()):
        try:
            config = replace(config, servers={**config.servers, check_platform(platform): check_server(url)})
        except BroadcastError:
            pass
    return replace(config, servers={name: url for name, url in config.servers.items() if url})


def save_config(config: BroadcastConfig, path: Path | None = None) -> Path:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# --- 스트림 키(Windows DPAPI) ---------------------------------------------------------------

_ENTROPY = b"debutkit-broadcast-key"


def _dpapi(data: bytes, protect: bool) -> bytes:  # pragma: no cover - Windows 전용(테스트는 Windows에서만 실행)
    if sys.platform != "win32":
        raise BroadcastError("스트림 키 저장은 Windows에서만 지원")
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                         ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    source_buffer = ctypes.create_string_buffer(data, len(data))
    entropy_buffer = ctypes.create_string_buffer(_ENTROPY, len(_ENTROPY))
    source = Blob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_char)))
    entropy = Blob(len(_ENTROPY), ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_char)))
    result = Blob()
    if not function(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 0x1, ctypes.byref(result)):  # CRYPTPROTECT_UI_FORBIDDEN
        raise OSError(ctypes.get_last_error(), "스트림 키 암호화 처리 실패")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(result.pbData, ctypes.c_void_p))


def _read_keys(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {name: value for name, value in data.items() if name in PLATFORMS and isinstance(value, str)} if isinstance(data, dict) else {}


def save_key(platform: str, key: str, path: Path | None = None, protect: Callable[[bytes], bytes] | None = None) -> None:
    """플랫폼별 스트림 키를 암호화해 저장."""
    path = path or keys_path()
    sealed = (protect or (lambda raw: _dpapi(raw, True)))(check_key(key).encode("ascii"))
    keys = _read_keys(path)
    keys[check_platform(platform)] = base64.b64encode(sealed).decode("ascii")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(keys, indent=2), encoding="utf-8")


def load_key(platform: str, path: Path | None = None, unprotect: Callable[[bytes], bytes] | None = None) -> str | None:
    """저장한 스트림 키. 없거나 풀지 못하면(다른 Windows 사용자, 손상) ``None``."""
    sealed = _read_keys(path or keys_path()).get(platform)
    if not sealed:
        return None
    try:
        return check_key((unprotect or (lambda raw: _dpapi(raw, False)))(base64.b64decode(sealed)).decode("ascii"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None


def has_key(platform: str, path: Path | None = None) -> bool:
    return platform in _read_keys(path or keys_path())


def clear_key(platform: str, path: Path | None = None) -> bool:
    path = path or keys_path()
    keys = _read_keys(path)
    if keys.pop(platform, None) is None:
        return False
    path.write_text(json.dumps(keys, indent=2), encoding="utf-8")
    return True


def publish_url(config: BroadcastConfig, key: str) -> str:
    server = config.server_url()
    if not server:
        raise BroadcastError(f"{config.target.name} 송출 서버 주소 필요: {config.target.hint}")
    return f"{server}/{key}"


def mask(text: str, *hidden: str) -> str:
    """오류 문장, 기록에서 스트림 키를 가린다."""
    for secret in hidden:
        if secret:
            text = text.replace(secret, "****")
    return text


# --- ffmpeg ------------------------------------------------------------------------------

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW: 설정 마법사에서 콘솔 창이 깜빡이지 않게
_DEVICE = re.compile(r'"(?P<name>[^"]+)" \((?P<kind>[^)]*)\)')
_ALTERNATIVE = re.compile(r'Alternative name "(?P<alt>[^"]+)"')


@dataclass(frozen=True)
class AudioDevice:
    name: str  # 보이는 이름
    id: str  # ffmpeg에 넘길 이름(대체 이름이 있으면 그것: 이름이 바뀌어도 같은 장치)


def parse_devices(text: str) -> list[AudioDevice]:
    """``ffmpeg -list_devices true -f dshow -i dummy`` 출력에서 녹음 장치."""
    found: list[AudioDevice] = []
    pending: str | None = None
    for line in text.splitlines():
        device = _DEVICE.search(line)
        if device:
            pending = device["name"] if "audio" in device["kind"] else None
            if pending:
                found.append(AudioDevice(pending, pending))
            continue
        alternative = _ALTERNATIVE.search(line)
        if alternative and pending and found and found[-1].name == pending:
            found[-1] = AudioDevice(pending, alternative["alt"])
            pending = None
    return found


Runner = Callable[..., Any]


def audio_devices(ffmpeg: str, run: Runner = subprocess.run) -> list[AudioDevice]:
    try:
        result = run([ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"], capture_output=True, timeout=20,
                     creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return []
    output = (result.stderr or b"") + (result.stdout or b"")
    return parse_devices(output.decode("utf-8", "replace") if isinstance(output, bytes) else str(output))


_ENCODER_CACHE: dict[str, str | None] = {}


def encoder_works(ffmpeg: str, encoder: str, run: Runner = subprocess.run) -> bool:
    """짧은 시험 인코딩으로 이 PC에서 실제로 되는지(드라이버, 그래픽 카드 확인)."""
    pixel = "yuv420p" if encoder == "libx264" else "nv12"
    try:
        result = run([ffmpeg, "-hide_banner", "-v", "error", "-f", "lavfi", "-i", "color=black:s=640x360:r=30", "-frames:v", "3", "-pix_fmt", pixel,
                      "-c:v", encoder, "-b:v", "1000k", "-f", "null", "-"], capture_output=True, timeout=30, creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def detect_encoder(ffmpeg: str, run: Runner = subprocess.run, *, refresh: bool = False) -> str | None:
    """되는 인코더 중 첫 번째(``ENCODERS`` 순서). 한 번 확인하면 기억."""
    if refresh or ffmpeg not in _ENCODER_CACHE:
        _ENCODER_CACHE[ffmpeg] = next((name for name in ENCODERS if encoder_works(ffmpeg, name, run)), None)
    return _ENCODER_CACHE[ffmpeg]


@dataclass(frozen=True)
class Crop:
    """캡처한 창 그림에서 무대(1920x1080 비율) 부분. x, y는 ffmpeg crop 식(창 그림 크기 iw, ih 기준)."""
    width: int
    height: int
    x: str
    y: str


def stage_crop(width: float, height: float, ratio: float) -> Crop:
    """창 안 화면 크기(CSS 픽셀)와 배율로 무대 영역. 창 그림은 제목 표시줄 + 화면이고, 화면은 아래쪽에 붙어 있다."""
    view_w, view_h = width * ratio, height * ratio
    scale = min(view_w / STAGE[0], view_h / STAGE[1])
    stage_w, stage_h = STAGE[0] * scale, STAGE[1] * scale
    left, top = (view_w - stage_w) / 2, (view_h - stage_h) / 2
    even_w, even_h = max(2, int(stage_w) // 2 * 2), max(2, int(stage_h) // 2 * 2)
    return Crop(even_w, even_h, f"(iw-{round(view_w)})/2+{round(left)}", f"ih-{round(view_h)}+{round(top)}")


def encoder_args(encoder: str, kbps: int, fps: int, keyframe: int) -> list[str]:
    """고정 비트레이트(CBR), 키프레임 간격 고정. 방송 플랫폼 권장 설정."""
    gop = str(fps * keyframe)
    rate = ["-b:v", f"{kbps}k", "-maxrate", f"{kbps}k", "-bufsize", f"{kbps * 2}k", "-g", gop]
    if encoder == "h264_nvenc":
        return ["-c:v", encoder, "-preset", "p4", "-rc", "cbr", *rate, "-bf", "2", "-profile:v", "high", "-pix_fmt", "nv12"]
    if encoder == "h264_qsv":
        return ["-c:v", encoder, "-preset", "veryfast", *rate, "-bf", "2", "-profile:v", "high", "-pix_fmt", "nv12"]
    if encoder == "h264_amf":
        return ["-c:v", encoder, "-usage", "transcoding", "-quality", "speed", "-rc", "cbr", *rate, "-pix_fmt", "nv12"]
    if encoder == "libx264":
        return ["-c:v", encoder, "-preset", "veryfast", *rate, "-keyint_min", gop, "-sc_threshold", "0", "-bf", "2", "-profile:v", "high",
                "-x264-params", "nal-hrd=cbr", "-pix_fmt", "yuv420p"]
    return ["-c:v", encoder, "-rate_control", "cbr", *rate, "-pix_fmt", "nv12"]


def _audio_input(device: str) -> list[str]:
    return ["-f", "dshow", "-audio_buffer_size", "50", "-thread_queue_size", "1024", "-i", f"audio={device}"]


def build_command(ffmpeg: str, *, hwnd: int, crop: Crop, quality: Quality, kbps: int, encoder: str, keyframe: int, url: str,
                  mic: str = "", extra_audio: str = "") -> list[str]:
    """창 캡처 + 소리 장치 -> H.264, AAC -> RTMP(S). 진행 상황은 표준 출력(``-progress``), 멈춤은 표준 입력의 q."""
    devices = [device for device in (mic, extra_audio) if device]
    inputs: list[str] = []
    for device in devices:
        inputs += _audio_input(device)
    pixel = "yuv420p" if encoder == "libx264" else "nv12"
    video = (f"gfxcapture=hwnd={hwnd}:capture_cursor=0:max_framerate={quality.fps},hwdownload,format=bgra,"
             f"crop=w={crop.width}:h={crop.height}:x={crop.x}:y={crop.y},scale={quality.width}:{quality.height}:flags=bicubic,"
             f"format={pixel},fps={quality.fps}[v]")
    tidy = "aresample=48000:async=1000:first_pts=0,aformat=sample_fmts=fltp:channel_layouts=stereo"
    if not devices:
        audio = "anullsrc=r=48000:cl=stereo[a]"
    elif len(devices) == 1:
        audio = f"[0:a]{tidy}[a]"
    else:
        audio = f"[0:a]{tidy}[a0];[1:a]{tidy}[a1];[a0][a1]amix=inputs=2:duration=longest:normalize=0[a]"
    return [ffmpeg, "-hide_banner", "-loglevel", "warning", "-nostats", "-progress", "pipe:1", "-stats_period", "1", *inputs,
            "-filter_complex", f"{video};{audio}", "-map", "[v]", "-map", "[a]",
            *encoder_args(encoder, kbps, quality.fps, keyframe), "-c:a", "aac", "-b:a", f"{AUDIO_KBPS}k", "-ar", "48000", "-ac", "2",
            "-rw_timeout", "15000000", "-f", "flv", "-flvflags", "no_duration_filesize", url]


NO_GPU = "failed to create d3d11va device"  # 그래픽 장치 없음(가상 머신, 원격 데스크톱, CI)
_FAILURES = (
    ((NO_GPU,), "그래픽 장치(D3D11)를 열지 못해 창을 캡처할 수 없음: 그래픽 드라이버 확인. 가상 머신, 원격 데스크톱에서는 OBS 사용"),
    (("failed to find capture source", "failed to setup graphics capture", "parsed_gfxcapture"),
     "송출 화면 창을 캡처하지 못함: 창이 열려 있는지, 최소화하지 않았는지 확인"),
    (("could not find audio", "could not run graph", "could not enumerate audio", "error opening input file audio"),
     "소리 장치를 열지 못함: 장치 연결과 Windows 설정의 마이크 접근 허용 확인"),
    (("connection refused", "connection to tcp://", "cannot open connection", "connection timed out", "failed to resolve hostname", "network is unreachable",
      "error number -138", "error number -10060", "error number -10061"), "송출 서버에 연결하지 못함: 서버 주소와 인터넷 연결 확인"),
    (("server error", "badname", "publish", "error number -10053", "error number -10054", "input/output error", "broken pipe", "end of file"),
     "송출 서버가 연결을 거부하거나 끊음: 스트림 키와 서버 주소 확인(방송 플랫폼의 방송 설정 화면)"),
    (("error while opening encoder", "openencodesessionex", "mfx", "amf", "nvenc"),
     "인코더 시작 실패: 인코더를 x264로 바꿔 다시 시작"),
)


def describe_failure(lines: list[str]) -> str:
    """ffmpeg 오류 출력(가린 뒤)을 한국어 안내 한 줄로."""
    text = "\n".join(lines).lower()
    for needles, message in _FAILURES:
        if any(needle in text for needle in needles):
            return message
    last = next((line.strip() for line in reversed(lines) if line.strip()), "")
    return f"ffmpeg 종료: {last[:200]}" if last else "ffmpeg가 예기치 않게 종료"


# --- 송출 화면 크기 보고 ----------------------------------------------------------------------

_TOKEN = re.compile(r"^[0-9a-z]{4,16}$")


class ProgramState:
    """송출 화면 페이지가 알려 준 창 안 화면 크기(``POST /program/size``). 창 표식별로 최근 값만."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._lock = threading.Lock()
        self._clock = clock
        self._reports: dict[str, dict[str, Any]] = {}

    def update(self, data: dict[str, Any]) -> bool:
        token = data.get("window")
        numbers = [data.get(name) for name in ("width", "height", "ratio")]
        if not isinstance(token, str) or not _TOKEN.match(token):
            return False
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in numbers):
            return False
        width, height, ratio = (float(value) for value in numbers)  # type: ignore[arg-type]
        if not (1 <= width <= 10000 and 1 <= height <= 10000 and 0.25 <= ratio <= 8):
            return False
        with self._lock:
            if len(self._reports) >= 8 and token not in self._reports:
                self._reports.pop(next(iter(self._reports)))
            self._reports[token] = {"width": width, "height": height, "ratio": ratio, "hidden": data.get("hidden") is True, "at": self._clock()}
        return True

    def get(self, token: str) -> dict[str, Any] | None:
        with self._lock:
            found = self._reports.get(token)
            return dict(found) if found else None


# --- 송출 관리 -----------------------------------------------------------------------------


def _find_ffmpeg() -> str | None:
    from .tools import ffmpeg_path

    return ffmpeg_path()


class Broadcaster:
    """송출 화면 창과 ffmpeg 송출 프로세스. 시작은 뒤에서 진행하고 ``status`` 로 단계를 보여 준다."""

    STATES = {"off": "방송 꺼짐", "starting": "방송 준비 중", "live": "방송 중", "retrying": "다시 연결 중", "error": "방송 실패"}

    def __init__(self, program: ProgramState, port_of: Callable[[], int], *, notify: Callable[[str], None] | None = None,
                 ffmpeg: Callable[[], str | None] = _find_ffmpeg, window: Any = program_window, popen: Callable[..., Any] = subprocess.Popen,
                 run: Runner = subprocess.run, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] | None = None,
                 platform: str | None = None, wait_window: float = 20.0, retry_delay: float = 5.0, retries: int = 5, stable: float = 20.0,
                 config_file: Path | None = None, keys_file: Path | None = None, key_reader: Callable[[str], str | None] | None = None) -> None:
        self.program = program
        self.port_of = port_of
        self.notify = notify or (lambda text: None)
        self._ffmpeg = ffmpeg
        self.window = window
        self._popen = popen
        self._run = run
        self._clock = clock
        self._platform = platform or sys.platform
        self.wait_window, self.retry_delay, self.retries, self.stable = wait_window, retry_delay, retries, stable
        self._config_file, self._keys_file = config_file, keys_file
        self._key_reader = key_reader or (lambda name: load_key(name, self._keys_file))
        self._lock = threading.RLock()
        self._halt = threading.Event()
        self._sleep = sleep or (lambda seconds: self._halt.wait(seconds) and None)
        self._worker: threading.Thread | None = None
        self._process: Any = None
        self._token = ""
        self._opened = ""
        self._launched = 0.0
        self._hwnd: int | None = None
        self._state = "off"
        self._phase = ""
        self._error = ""
        self._since = 0.0
        self._attempt = 0
        self._stats: dict[str, Any] = {}
        self._samples: deque[tuple[float, float]] = deque()
        self._log: deque[str] = deque(maxlen=30)
        self._started_geometry: dict[str, Any] | None = None
        self._encoder = ""
        self._secret = ""

    # 설정 ----------------------------------------------------------------------------------
    def config(self) -> BroadcastConfig:
        return load_config(self._config_file)

    def supported(self) -> bool:
        return self._platform == "win32"

    def update_config(self, data: dict[str, Any]) -> dict[str, Any]:
        config = from_request(data, self.config())
        save_config(config, self._config_file)
        return self.status()

    def set_key(self, key: Any, platform: Any = None) -> dict[str, Any]:
        name = check_platform(platform) if platform is not None else self.config().platform
        if key is None:
            clear_key(name, self._keys_file)
        else:
            save_key(name, key, self._keys_file)
        return self.status()

    def devices(self) -> dict[str, Any]:
        """소리 장치와 이 PC에서 되는 인코더(처음에는 시험 인코딩으로 몇 초 걸림)."""
        ffmpeg = self._ffmpeg()
        if not ffmpeg:
            return {"ffmpeg": False, "audio": [], "encoder": None}
        encoder = detect_encoder(ffmpeg, self._run)
        return {"ffmpeg": True, "audio": [asdict(item) for item in audio_devices(ffmpeg, self._run)], "encoder": encoder,
                "encoder_name": ENCODER_NAMES.get(encoder or "", "")}

    # 송출 화면 창 ------------------------------------------------------------------------------
    def _layout(self, config: BroadcastConfig) -> str:
        query = {"window": self._token, "bg": config.background}
        if config.title:
            query["title"] = config.title
        if config.camera:
            query["camera"] = "1"
        return urllib.parse.urlencode(query)

    def program_url(self, config: BroadcastConfig | None = None) -> str:
        return f"http://127.0.0.1:{self.port_of()}/program?{self._layout(config or self.config())}"

    def _current_window(self) -> int | None:
        if not self._token:
            return None
        hwnd = self.window.find(self._token)
        self._hwnd = hwnd
        return hwnd

    def _window_key(self, config: BroadcastConfig) -> str:
        return f"{self._layout(config)}|{config.size.width}x{config.size.height}"

    def open_window(self) -> dict[str, Any]:
        """송출 화면 창 열기(이미 열려 있으면 그대로, 화면 구성이 바뀌었으면 방송 중이 아닐 때 다시 연다)."""
        if not self.supported():
            raise BroadcastError("OBS 없이 방송은 현재 Windows에서만 지원")
        with self._lock:
            self._prepare_window(self.config())
        return self.status()

    def _prepare_window(self, config: BroadcastConfig) -> bool:
        """창이 이 설정으로 열려 있거나 막 뜨는 중이면 그대로, 아니면 연다(새로 열면 True)."""
        hwnd = self._current_window()
        if hwnd is not None:
            if self._window_key(config) == self._opened or self._state in ("live", "retrying"):
                return False
            self.window.close(hwnd)  # 화면 구성 변경: 다시 연다
            self._hwnd = None
        elif self._token and self._clock() - self._launched < self.wait_window:
            return False  # 방금 연 창이 아직 뜨는 중
        browser = self.window.find_browser()
        if not browser:
            raise BroadcastError("Edge 또는 Chrome 필요(송출 화면 창)")
        self._token = secrets.token_hex(4)
        self._opened = self._window_key(config)
        self._launched = self._clock()
        self.window.launch(browser, self.program_url(config), profile_path(), config.size.width, config.size.height)
        return True

    def _wait_window(self) -> int | None:
        """창이 뜨고 송출 화면 페이지가 화면 크기를 알려 줄 때까지 기다린다."""
        deadline = self._clock() + self.wait_window
        while not self._halt.is_set():
            with self._lock:
                if self._current_window() is not None and self.program.get(self._token):
                    return self._hwnd
            if self._clock() >= deadline:
                return None
            self._sleep(0.25)
        return None

    def close_window(self) -> None:
        with self._lock:
            if self._current_window() is not None:
                self.window.close(self._hwnd)
            self._hwnd = None
            self._token = ""

    # 시작, 멈춤 -------------------------------------------------------------------------------
    def start(self) -> dict[str, Any]:
        """설정과 키를 확인하고 뒤에서 송출 시작. 진행은 ``status`` 로 확인."""
        if not self.supported():
            raise BroadcastError("OBS 없이 방송은 현재 Windows에서만 지원")
        config = self.config()
        key = self._key_reader(config.platform)
        if not key:
            raise BroadcastError(f"{config.target.name} 스트림 키를 먼저 저장: {config.target.hint}")
        url = publish_url(config, key)
        with self._lock:
            if self._state in ("starting", "live", "retrying"):
                return self.status()
            if not self._ffmpeg():
                from .tools import install_hint

                raise BroadcastError(f"ffmpeg 필요: {install_hint()}")
            self._halt.clear()
            self._state, self._phase, self._error, self._attempt = "starting", "송출 화면 준비", "", 0
            self._stats, self._started_geometry = {}, None
            self._log.clear()
            self._secret = key
            self._worker = threading.Thread(target=self._run_broadcast, args=(config, url), name="broadcast", daemon=True)
            self._worker.start()
        return self.status()

    def stop(self, *, close_window: bool = False) -> dict[str, Any]:
        self._halt.set()
        process = self._process
        if process is not None:
            self._end_process(process)
        worker = self._worker
        if worker is not None and worker is not threading.current_thread():
            worker.join(10)
        with self._lock:
            self._state, self._phase = "off", ""  # 최근 오류 문장(error)은 다음 시작 전까지 남긴다
            self._worker = None
        if close_window:
            self.close_window()
        return self.status()

    def _end_process(self, process: Any) -> None:
        """q를 보내 정상 종료(서버에 끝을 알림). 5초 안에 끝나지 않으면 강제 종료."""
        try:
            if process.stdin:
                process.stdin.write(b"q")
                process.stdin.flush()
        except (OSError, ValueError):
            pass
        try:
            process.wait(5)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(5)
            except subprocess.TimeoutExpired:
                pass

    def _fail(self, message: str) -> None:
        with self._lock:
            self._state, self._phase, self._error = "error", "", mask(message, self._secret)
        self.notify(f"방송 실패: {self._error}")

    def _run_broadcast(self, config: BroadcastConfig, url: str) -> None:
        try:
            with self._lock:
                self._prepare_window(config)
                self._phase = "송출 화면 창 여는 중"
            hwnd = self._wait_window()
            if self._halt.is_set():
                return
            geometry = self.program.get(self._token)
            if hwnd is None or geometry is None:
                return self._fail("송출 화면 창이 열리지 않음: Edge 또는 Chrome 확인")
            ffmpeg = self._ffmpeg()
            if not ffmpeg:
                return self._fail("ffmpeg를 찾지 못함")
            with self._lock:
                self._phase = "인코더 확인 중"
            encoder = config.encoder if config.encoder != "auto" else detect_encoder(ffmpeg, self._run)
            if not encoder:
                return self._fail("사용할 수 있는 H.264 인코더 없음: ffmpeg 다시 받기(debutkit setup --ffmpeg)")
            self._encoder = encoder
            self._started_geometry = geometry
            command = build_command(ffmpeg, hwnd=hwnd, crop=stage_crop(geometry["width"], geometry["height"], geometry["ratio"]), quality=config.size,
                                    kbps=config.video_kbps(), encoder=encoder, keyframe=config.target.keyframe, url=url, mic=config.mic,
                                    extra_audio=config.extra_audio)
            self._loop(command, config)
        except BroadcastError as error:
            self._fail(str(error))
        except Exception as error:  # 예상 못 한 오류도 상태로 보여 준다
            self._fail(f"{type(error).__name__}: {error}")

    def _loop(self, command: list[str], config: BroadcastConfig) -> None:
        """ffmpeg를 실행하고, 방송이 한동안 이어진 뒤 끊기면 ``retries`` 번까지 다시 연결."""
        failures = 0
        retrying = False
        while not self._halt.is_set():
            with self._lock:
                self._phase = "송출 서버 연결 중"
                self._attempt += 1
            self._log.clear()
            began = self._clock()
            code = self._spawn_and_wait(command)
            if self._halt.is_set():
                return
            reason = describe_failure(list(self._log))
            if self._clock() - began >= self.stable:  # 한동안 방송한 뒤 끊김: 다시 연결
                failures = 0
            else:  # 시작하자마자 끝남: 처음이면 설정 문제, 다시 연결 중이면 횟수만큼만
                failures += 1
                if not retrying or failures > self.retries:
                    return self._fail(reason if code else "송출이 바로 끝남: 스트림 키와 서버 주소 확인")
            retrying = True
            with self._lock:
                self._state, self._phase, self._error = "retrying", f"{self.retry_delay:.0f}초 뒤 다시 연결", reason
            self.notify(f"방송 연결 끊김: {reason}. 다시 연결")
            self._sleep(self.retry_delay)

    def _spawn_and_wait(self, command: list[str]) -> int:
        process = self._popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=_NO_WINDOW)
        with self._lock:
            self._process = process
            self._samples.clear()
        errors = threading.Thread(target=self._read_errors, args=(process.stderr,), name="broadcast-log", daemon=True)
        errors.start()
        try:
            self._read_progress(process.stdout)
            code = process.wait()
        finally:
            errors.join(2)
            with self._lock:
                self._process = None
        return int(code or 0)

    def _read_errors(self, stream: IO[bytes] | None) -> None:
        if stream is None:
            return
        for raw in iter(stream.readline, b""):
            line = mask(raw.decode("utf-8", "replace").rstrip(), self._secret)
            if line:
                self._log.append(line)

    def _read_progress(self, stream: IO[bytes] | None) -> None:
        if stream is None:
            return
        block: dict[str, str] = {}
        for raw in iter(stream.readline, b""):
            name, _, value = raw.decode("utf-8", "replace").strip().partition("=")
            if name != "progress":
                block[name] = value.strip()
                continue
            self._take(block)
            block = {}

    def _take(self, block: dict[str, str]) -> None:
        def number(name: str) -> float:
            try:
                return float(re.sub(r"[^0-9.]", "", block.get(name, "")) or 0)
            except ValueError:
                return 0.0

        # ffmpeg의 speed는 시작부터의 평균(인코더 준비 시간 포함)이라 최근 10초 동안의 속도를 따로 계산
        now = self._clock()
        self._samples.append((now, number("out_time_us")))
        while len(self._samples) > 2 and now - self._samples[1][0] >= SPEED_WINDOW:
            self._samples.popleft()
        first_at, first_out = self._samples[0]
        span = now - first_at
        speed = round((number("out_time_us") - first_out) / 1e6 / span, 2) if span >= SPEED_WINDOW * 0.8 else None
        stats = {"frames": int(number("frame")), "fps": round(number("fps"), 1), "kbps": round(number("bitrate")),
                 "dropped": int(number("drop_frames")), "duplicated": int(number("dup_frames")), "speed": speed}
        with self._lock:
            self._stats = stats
            if stats["frames"] > 0 and self._state in ("starting", "retrying"):
                first = self._state == "starting"
                self._state, self._phase, self._error = "live", "", ""
                if first:
                    self._since = self._clock()
                    self.notify("방송 시작")

    # 상태 -----------------------------------------------------------------------------------
    def warnings(self) -> list[str]:
        """방송 중 알아야 할 것: 창 최소화, 창 크기 변경, 작은 창, PC 부하."""
        found: list[str] = []
        if self._state not in ("live", "retrying", "starting") or not self._token:
            return found
        geometry = self.program.get(self._token)
        hwnd = self.window.find(self._token)
        if hwnd is None:  # 준비 중에는 아직 뜨지 않았을 수 있음
            return ["송출 화면 창이 닫힘: 방송을 끝내고 다시 시작"] if self._state in ("live", "retrying") else []
        if self.window.minimized(hwnd) or (geometry and geometry["hidden"]):
            found.append("송출 화면 창이 최소화됨: 방송 화면이 멈춤. 창을 다시 띄우기(다른 창에 가려져도 됨)")
        started = self._started_geometry
        if geometry and started and (abs(geometry["width"] - started["width"]) > 1 or abs(geometry["height"] - started["height"]) > 1):
            found.append("방송 중 송출 화면 창 크기가 바뀜: 원래 크기로 되돌리거나 방송을 다시 시작")
        if started:
            crop = stage_crop(started["width"], started["height"], started["ratio"])
            quality = self.config().size
            if crop.width < quality.width * 0.75:
                found.append(f"송출 화면 창이 작아 화질이 떨어짐(창 안 화면 {crop.width}x{crop.height}, 송출 {quality.width}x{quality.height}): 창을 키우기")
        speed = self._stats.get("speed")
        if self._state == "live" and speed is not None and speed < 0.9:
            found.append("PC가 송출을 따라가지 못함: 화질을 720p 30fps로 낮추거나 다른 프로그램 닫기")
        return found

    def status(self) -> dict[str, Any]:
        config = self.config()
        with self._lock:
            state = self._state
            answer: dict[str, Any] = {
                "supported": self.supported(), "state": state, "message": self.STATES[state], "phase": self._phase, "error": self._error,
                "config": config.to_dict(), "key_saved": has_key(config.platform, self._keys_file), "server": config.server_url(),
                "video_kbps": config.video_kbps(), "encoder": self._encoder, "encoder_name": ENCODER_NAMES.get(self._encoder, ""),
                "stats": dict(self._stats), "seconds": round(self._clock() - self._since) if state == "live" else 0,
                "window": self._current_window() is not None,
                "platforms": {key: {"name": item.name, "server": item.server, "max_kbps": item.max_kbps, "hint": item.hint} for key, item in PLATFORMS.items()},
                "qualities": {key: item.name for key, item in QUALITIES.items()},
            }
        answer["warnings"] = self.warnings()
        return answer
