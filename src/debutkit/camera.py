"""휴대폰 카메라 영상: 휴대폰 앱이 SRT로 보내는 카메라 영상을 OBS 미디어 소스로 받는다(실사, 손 캠, 방 안 촬영).

- OBS 기본 미디어 소스(ffmpeg_source)를 SRT 수신(listener) 모드로 만든다. OBS 플러그인이나 추가 프로그램 불필요
- 휴대폰은 같은 Wi-Fi에서 PC 주소의 지정 포트(기본 9710)로 보낸다. 송신 앱은 Larix Broadcaster(아이폰, 안드로이드) 등 SRT 송신 앱
- 암호(SRT passphrase, AES-128)가 맞는 휴대폰만 연결된다. 암호는 설정 폴더의 ``phone-camera.json`` 에만 보관(저장 설정 파일에는 넣지 않음)
- Larix Broadcaster는 연결 정보를 가져오기 주소(``larix://set/v1``)나 그 QR 코드로 등록. 소리는 기본으로 보내지 않음(PC 마이크 사용)
"""

from __future__ import annotations

import ipaddress
import json
import secrets
import socket
import threading
import time
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from . import settings

SOURCE_NAME = "[DK] 휴대폰 카메라"
INPUT_KIND = "ffmpeg_source"
DEFAULT_PORT = 9710
DEFAULT_LATENCY = 200  # 밀리초. SRT 재전송 여유(Wi-Fi가 불안정하면 크게)
LATENCY_RANGE = (80, 2000)
PASS_CHARS = "abcdefghjkmnpqrstuvwxyz23456789"  # 휴대폰에 직접 입력할 때 헷갈리는 글자(0, o, 1, l, i) 제외
PASS_LENGTH = 12  # SRT 암호는 10에서 79자
#: 수신 대기가 아닌 OBS 미디어 상태의 안내. SRT 수신 대기 중에도 OBS는 재생 중(PLAYING)으로 표시하므로 수신 여부는 소스 크기로 판단
MEDIA_STATES = {"OBS_MEDIA_STATE_PAUSED": "일시 정지(OBS에서 재생)", "OBS_MEDIA_STATE_STOPPED": "멈춤(OBS에서 재생)",
                "OBS_MEDIA_STATE_ERROR": "오류(포트 사용 중 등)", "OBS_MEDIA_STATE_NONE": "꺼짐"}


class CameraError(ValueError):
    """잘못된 휴대폰 카메라 설정이나 OBS 작업 실패. 메시지는 한국어 안내."""


@dataclass(frozen=True)
class CameraConfig:
    port: int = DEFAULT_PORT
    latency: int = DEFAULT_LATENCY
    passphrase: str = ""


def config_path() -> Path:
    return settings.settings_path().parent / "phone-camera.json"


def new_passphrase() -> str:
    return "".join(secrets.choice(PASS_CHARS) for _ in range(PASS_LENGTH))


def check_port(port: Any) -> int:
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise CameraError("포트는 1024에서 65535 사이의 정수(기본 9710)")
    return port


def check_latency(latency: Any) -> int:
    low, high = LATENCY_RANGE
    if isinstance(latency, bool) or not isinstance(latency, int) or not low <= latency <= high:
        raise CameraError(f"지연 여유는 {low}에서 {high} 밀리초 사이의 정수(기본 {DEFAULT_LATENCY})")
    return latency


def _valid_pass(value: Any) -> bool:
    return isinstance(value, str) and 10 <= len(value) <= 79 and all(ch in PASS_CHARS for ch in value)


def load_config(path: Path | None = None) -> CameraConfig:
    """저장한 설정. 없거나 손상되었으면 새 암호로 만들어 저장."""
    path = path or config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    try:
        port = check_port(data.get("port", DEFAULT_PORT))
    except CameraError:
        port = DEFAULT_PORT
    try:
        latency = check_latency(data.get("latency", DEFAULT_LATENCY))
    except CameraError:
        latency = DEFAULT_LATENCY
    passphrase = data.get("passphrase")
    config = CameraConfig(port, latency, passphrase if _valid_pass(passphrase) else new_passphrase())
    if data != asdict(config):
        save_config(config, path)
    return config


def save_config(config: CameraConfig, path: Path | None = None) -> Path:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def update_config(port: Any = None, latency: Any = None, new_pass: bool = False) -> CameraConfig:
    """포트, 지연 여유 변경과 새 암호. 바꾼 뒤에는 OBS 소스도 다시 맞춰야 한다(``add_to_obs``)."""
    config = load_config()
    config = CameraConfig(check_port(port) if port is not None else config.port, check_latency(latency) if latency is not None else config.latency,
                          new_passphrase() if new_pass else config.passphrase)
    save_config(config)
    return config


_ADDRESSES: tuple[float, list[str]] = (0.0, [])
ADDRESS_CACHE = 10.0  # 초. 설정 화면이 자주 묻는 값
HOST_LOOKUP_TIMEOUT = 1.0  # 컴퓨터 이름 조회는 환경에 따라(macOS의 .local 등) 수십 초 걸릴 수 있음


def _host_addresses() -> list[str]:
    """컴퓨터 이름에 붙은 주소(유선, Wi-Fi가 함께 있는 경우 등). 1초 안에 끝나지 않으면 포기."""
    found: list[str] = []

    def lookup() -> None:
        try:
            found.extend(str(info[4][0]) for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
        except OSError:
            pass

    worker = threading.Thread(target=lookup, name="host-addresses", daemon=True)
    worker.start()
    worker.join(HOST_LOOKUP_TIMEOUT)
    return list(found) if not worker.is_alive() else []


def lan_addresses(extra: Iterable[str] = ()) -> list[str]:
    """이 PC의 내부 네트워크 IPv4 주소(휴대폰이 보낼 곳). 기본 경로의 주소를 앞에. 외부로 패킷을 보내지 않는다(UDP connect). 10초 동안 기억."""
    global _ADDRESSES
    moment, cached = _ADDRESSES
    if time.monotonic() - moment > ADDRESS_CACHE:
        cached = []
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("192.0.2.1", 9))  # 문서용 주소(RFC 5737): 경로만 계산
            cached.append(str(probe.getsockname()[0]))
        except OSError:
            pass
        finally:
            probe.close()
        cached += _host_addresses()
        _ADDRESSES = (time.monotonic(), cached)
    found = list(cached) + list(extra)
    result: list[str] = []
    for text in found:
        try:
            address = ipaddress.IPv4Address(text)
        except ValueError:
            continue
        if address.is_private and not address.is_loopback and not address.is_link_local and text not in result:
            result.append(text)
    return result


def obs_input(config: CameraConfig) -> str:
    """OBS 미디어 소스의 입력 주소: 모든 네트워크에서 SRT 수신, 지연 여유(마이크로초), 암호."""
    return f"srt://0.0.0.0:{config.port}?mode=listener&latency={config.latency * 1000}&passphrase={config.passphrase}&pbkeylen=16"


def source_settings(config: CameraConfig) -> dict[str, Any]:
    """미디어 소스 설정(OBS plugins/obs-ffmpeg/obs-ffmpeg-source.c 항목). 지연을 줄이도록 네트워크 버퍼 0, 끊기면 1초 뒤 다시 대기."""
    return {"is_local_file": False, "input": obs_input(config), "input_format": "mpegts", "reconnect_delay_sec": 1, "buffering_mb": 0,
            "hw_decode": True, "clear_on_media_end": True, "restart_on_activate": False, "close_when_inactive": False}


def sender_url(address: str, config: CameraConfig) -> str:
    return f"srt://{address}:{config.port}"


def larix_link(address: str, config: CameraConfig, *, audio: bool = False) -> str:
    """Larix Broadcaster 가져오기 주소(Larix Grove 형식). 같은 이름의 연결은 덮어씀. 영상만(소리는 PC 마이크)."""
    pairs = [("conn[][url]", sender_url(address, config)), ("conn[][name]", "debutkit camera"), ("conn[][overwrite]", "on"),
             ("conn[][mode]", "va" if audio else "v"), ("conn[][srtmode]", "c"), ("conn[][srtlatency]", str(config.latency)),
             ("conn[][srtpass]", config.passphrase), ("conn[][srtpbkl]", "16")]
    return "larix://set/v1?" + "&".join(f"{key}={urllib.parse.quote(value, safe=':/')}" for key, value in pairs)


def qr_svg(text: str, *, scale: int = 6, border: int = 4) -> str:
    """QR 코드 SVG(검은 칸, 흰 바탕). Nayuki QR Code generator(MIT)."""
    from .vendor.qrcodegen import QrCode

    code = QrCode.encode_text(text, QrCode.Ecc.MEDIUM)
    size = code.get_size()
    full = size + 2 * border
    cells = " ".join(f"M{x + border},{y + border}h1v1h-1z" for y in range(size) for x in range(size) if code.get_module(x, y))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {full} {full}" width="{full * scale}" height="{full * scale}" '
            f'shape-rendering="crispEdges"><rect width="100%" height="100%" fill="#ffffff"/><path d="{cells}" fill="#000000"/></svg>')


def qr_matrix(text: str) -> list[list[bool]]:
    """QR 코드 칸(설정 마법사 그림용). 가장자리 여백 제외."""
    from .vendor.qrcodegen import QrCode

    code = QrCode.encode_text(text, QrCode.Ecc.MEDIUM)
    return [[code.get_module(x, y) for x in range(code.get_size())] for y in range(code.get_size())]


def connection_info(config: CameraConfig | None = None, addresses: list[str] | None = None) -> dict[str, Any]:
    """휴대폰 앱에 입력할 정보: PC 주소(여러 개면 첫 주소 권장), 포트, 암호, 지연, Larix 가져오기 주소."""
    config = config or load_config()
    addresses = lan_addresses() if addresses is None else addresses
    address = addresses[0] if addresses else ""
    return {"addresses": addresses, "address": address, "port": config.port, "latency": config.latency, "passphrase": config.passphrase,
            "url": sender_url(address, config) if address else "", "larix": larix_link(address, config) if address else "", "source": SOURCE_NAME}


# ---------------------------------------------------------------------- OBS
def _scene_items(client: Any, scene: str) -> list[dict[str, Any]]:
    return list(client.request("GetSceneItemList", {"sceneName": scene}).get("sceneItems", []))


def _place(client: Any, scene: str, item_id: int, width: int, height: int) -> None:
    """왼쪽 위(본방송 장면의 아바타는 왼쪽 아래, 채팅은 오른쪽)에 화면 30% 폭 상자로. 채팅, 알림, 추첨 화면 아래 층으로."""
    from .scenes import PREFIX, _bounds

    margin = round(height * 0.03)
    client.request("SetSceneItemTransform", {"sceneName": scene, "sceneItemId": item_id,
                                             "sceneItemTransform": _bounds(margin, margin, width * 0.3, height * 0.4)})
    overlays = [item for item in _scene_items(client, scene)
                if str(item.get("sourceName", "")) in (f"{PREFIX}채팅", f"{PREFIX}후원 알림", f"{PREFIX}후원 추첨")]
    if overlays:
        lowest = min(int(item.get("sceneItemIndex", 0)) for item in overlays)
        client.request("SetSceneItemIndex", {"sceneName": scene, "sceneItemId": item_id, "sceneItemIndex": lowest})


def add_to_obs(client: Any, config: CameraConfig, scenes: Iterable[str] = ()) -> dict[str, Any]:
    """OBS에 미디어 소스를 만들거나(처음) 설정을 맞추고(포트, 암호 변경), 장면에 넣는다. 장면을 주지 않으면 현재 방송 장면."""
    kinds = client.request("GetInputKindList", {"unversioned": False}).get("inputKinds", [])
    if INPUT_KIND not in kinds:
        raise CameraError("이 OBS에는 미디어 소스가 없음(OBS 설치 상태 확인)")
    targets = [name for name in scenes if name]
    if not targets:
        current = client.request("GetCurrentProgramScene")
        targets = [str(current.get("sceneName") or current.get("currentProgramSceneName") or "")]
    existing_scenes = {str(scene.get("sceneName")) for scene in client.request("GetSceneList").get("scenes", [])}
    missing = [name for name in targets if name not in existing_scenes]
    if missing or not targets[0]:
        raise CameraError(f"OBS에 없는 장면: {', '.join(missing) or '현재 장면'}")
    video = client.request("GetVideoSettings")
    width, height = int(video.get("baseWidth", 1920)), int(video.get("baseHeight", 1080))
    exists = SOURCE_NAME in {str(item.get("inputName")) for item in client.request("GetInputList").get("inputs", [])}
    result: dict[str, Any] = {"source": SOURCE_NAME, "created": not exists, "updated": exists, "added": [], "kept": []}
    if exists:
        client.request("SetInputSettings", {"inputName": SOURCE_NAME, "inputSettings": source_settings(config), "overlay": True})
    for scene in targets:
        if any(str(item.get("sourceName")) == SOURCE_NAME for item in _scene_items(client, scene)):
            result["kept"].append(scene)
            continue
        if exists:
            item_id = client.request("CreateSceneItem", {"sceneName": scene, "sourceName": SOURCE_NAME})["sceneItemId"]
        else:
            item_id = client.request("CreateInput", {"sceneName": scene, "inputName": SOURCE_NAME, "inputKind": INPUT_KIND,
                                                     "inputSettings": source_settings(config), "sceneItemEnabled": True})["sceneItemId"]
            exists = True
        _place(client, scene, int(item_id), width, height)
        result["added"].append(scene)
    return result


def _source_size(client: Any) -> tuple[int, int] | None:
    """소스 영상 크기(장면 항목의 sourceWidth, sourceHeight). 받은 영상이 없거나 끊겨 지워지면 0. 어느 장면에도 없으면 None."""
    for scene in client.request("GetSceneList").get("scenes", []):
        name = str(scene.get("sceneName"))
        for item in _scene_items(client, name):
            if str(item.get("sourceName")) == SOURCE_NAME:
                transform = client.request("GetSceneItemTransform", {"sceneName": name, "sceneItemId": item.get("sceneItemId")})
                values = transform.get("sceneItemTransform", {})
                return int(values.get("sourceWidth") or 0), int(values.get("sourceHeight") or 0)
    return None


def media_state(client: Any) -> dict[str, Any]:
    """OBS 소스 상태: 없음, 휴대폰 연결 대기, 휴대폰 영상 수신 중(영상 크기 표시), 오류 등. ``receiving`` 은 영상이 오는 중인지."""
    if SOURCE_NAME not in {str(item.get("inputName")) for item in client.request("GetInputList").get("inputs", [])}:
        return {"exists": False, "state": "", "receiving": False, "size": None, "text": "OBS에 휴대폰 카메라 소스 없음"}
    state = str(client.request("GetMediaInputStatus", {"inputName": SOURCE_NAME}).get("mediaState") or "OBS_MEDIA_STATE_NONE")
    size = _source_size(client)
    receiving = bool(size and size[0] > 0 and size[1] > 0) and state != "OBS_MEDIA_STATE_ERROR"
    if state in MEDIA_STATES:
        text = MEDIA_STATES[state]
    elif size is None:
        text = "어느 장면에도 없음: OBS에 소스 만들기로 장면에 추가"
    elif receiving:
        text = f"휴대폰 영상 수신 중({size[0]}x{size[1]})"
    else:
        text = "휴대폰 연결 대기"
    return {"exists": True, "state": state, "receiving": receiving, "size": list(size) if size else None, "text": text}


def connect(host: str, port: int, password: str | None) -> Any:
    """OBS 연결(채팅 연결 모듈의 ObsClient). ``with connect(...) as client:`` 로 사용."""
    try:
        from stream2clip.obs import ObsClient
    except ImportError as error:
        raise CameraError('OBS 연결에는 채팅 연결 모듈 필요: pip install "debutkit[live]"') from error
    return ObsClient(host, port, password, events=0)


def obs_failure(error: Exception) -> str:
    """OBS 연결, 요청 실패 안내."""
    text = str(error)
    lowered = text.lower()
    if "password" in lowered or "authenticat" in lowered or "4009" in lowered:
        return f"OBS WebSocket 비밀번호가 필요하거나 맞지 않음: OBS 도구 메뉴의 WebSocket 서버 설정에서 확인({text})"
    if isinstance(error, (ConnectionError, OSError, TimeoutError)) or any(word in lowered for word in ("refused", "cannot reach", "timed out")):
        return f"OBS에 연결하지 못함: OBS 실행과 도구 메뉴의 WebSocket 서버 설정(켬, 포트, 비밀번호) 확인({text})"
    return f"OBS 요청 실패: {text}"
