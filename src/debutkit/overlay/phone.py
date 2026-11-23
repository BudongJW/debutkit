"""휴대폰 얼굴 추적 수신: 아이폰 앱(iFacialMocap, VTube Studio)이 보내는 ARKit 표정 값을 받아 캐릭터 화면으로 보낸다.

- 같은 Wi-Fi의 휴대폰 IP를 지정하면 debutkit이 휴대폰에 송신 요청을 보내고, 그 휴대폰에서 온 값만 받는다
- iFacialMocap(FaceMotion3D의 iFacialMocap 호환 포함): 휴대폰 UDP 49983으로 시작 문자열, PC UDP 49983에서 수신(공개 형식 v1, v2)
- VTube Studio(아이폰, 아이패드): 앱 설정의 3rd Party PC Clients 켬. 휴대폰 UDP 21412로 JSON 요청을 1초마다 보내고 PC 포트에서 수신
- 머리 회전, 눈 깜빡임, 입, 웃음은 웹캠 추적과 같은 값으로, ARKit 52개 표정은 ``arkit`` 으로 보낸다(퍼펙트 싱크 모델)
- 값은 메모리에서만 처리하고 저장하거나 외부로 보내지 않는다. 기본 꺼짐. 수신 창구는 휴대폰과 연결된 네트워크 주소 하나에만 연다
"""

from __future__ import annotations

import ipaddress
import json
import math
import socket
import threading
import time
from typing import Any

from .. import settings
from .tracking import ARKIT_NAMES, TrackingState, arkit_name  # noqa: F401 (ARKIT_NAMES 다시 내보냄)

APPS = {"ifacialmocap": "iFacialMocap(아이폰, FaceMotion3D 호환 모드 포함)", "vts": "VTube Studio(아이폰, 아이패드)"}
IFM_PORT = 49983  # 휴대폰 쪽(시작 문자열을 받는 곳)
IFM_LISTEN_PORT = 49983  # PC 쪽(휴대폰이 값을 보내는 곳). 두 번호 모두 앱에 고정
IFM_START = "iFacialMocap_sahuasouryya9218sauhuiayeta91555dy3719"
VTS_PORT = 21412  # 휴대폰 쪽. PC 쪽은 비어 있는 번호를 요청에 담아 알림
VTS_REQUEST_SECONDS = 3.0  # 요청 1회당 받는 시간(0.5에서 10초). 1초마다 다시 요청
RATE = 30.0  # 캐릭터 화면으로 보내는 최대 횟수(초당). 휴대폰은 초당 60회 보냄
STALE = 1.0  # 이 시간 넘게 값이 없으면 수신 끊김으로 표시


def _side_swapped(name: str) -> str:
    """좌우 반전: Left와 Right가 붙은 표정을 반대쪽으로(jawLeft, mouthLeft 같은 움직임 방향도 반대)."""
    if name.endswith("Left"):
        return name[:-4] + "Right"
    if name.endswith("Right"):
        return name[:-5] + "Left"
    return name


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_ifacialmocap(data: bytes | str) -> dict[str, Any] | None:
    """iFacialMocap 한 프레임. ``이름-값|...|=head#rx,ry,rz,px,py,pz|rightEye#...|leftEye#...|``

    값은 0에서 100(v2는 ``이름&값``), 각도는 도. 형식이 아니면 None.
    """
    text = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
    text = text.replace(" ", "").replace("___iFacialMocap", "")
    shapes_part, equal, pose_part = text.partition("=")
    if not equal:
        return None
    shapes: dict[str, float] = {}
    for item in shapes_part.split("|"):
        separator = "&" if "&" in item else "-"
        name, found, value = item.partition(separator)  # 첫 구분자 기준: 음수 값(FaceMotion3D)도 읽음
        canonical, number = arkit_name(name), _number(value)
        if found and canonical and number is not None:
            shapes[canonical] = number / 100.0
    rotation = None
    for item in pose_part.split("|"):
        if item.startswith("head#"):
            numbers = [_number(part) for part in item[5:].split(",")[:6]]
            if len(numbers) >= 3 and all(number is not None for number in numbers[:3]):
                rotation = (numbers[0], numbers[1], numbers[2])
    if not shapes and rotation is None:
        return None
    return {"found": True, "shapes": shapes, "rotation": rotation}


def parse_vts(data: bytes | str) -> dict[str, Any] | None:
    """VTube Studio 아이폰 앱의 추적 값(JSON). ``FaceFound``, ``Rotation``, ``BlendShapes`` [{k, v}], ``Hotkey``. 형식이 아니면 None."""
    try:
        payload = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or "BlendShapes" not in payload:
        return None
    shapes: dict[str, float] = {}
    for entry in payload.get("BlendShapes") or []:
        if isinstance(entry, dict):
            canonical, number = arkit_name(str(entry.get("k", ""))), _number(entry.get("v"))
            if canonical and number is not None:
                shapes[canonical] = number
    raw = payload.get("Rotation")
    rotation = None
    if isinstance(raw, dict):
        numbers = [_number(raw.get(axis)) for axis in ("x", "y", "z")]
        if all(number is not None for number in numbers):
            rotation = (numbers[0], numbers[1], numbers[2])
    hotkey = payload.get("Hotkey")
    return {"found": payload.get("FaceFound") is True, "shapes": shapes, "rotation": rotation,
            "hotkey": hotkey if isinstance(hotkey, int) and not isinstance(hotkey, bool) and 1 <= hotkey <= 8 else None}


def head_angles(app: str, rotation: tuple[float, float, float] | None) -> tuple[float, float, float]:
    """앱의 머리 회전(도)을 debutkit 기준(라디안 yaw, pitch, roll)으로.

    debutkit 기준(웹캠 추적과 같음): yaw 양수는 얼굴 기준 왼쪽으로 돌림, pitch 양수는 아래를 봄, roll 양수는 얼굴 기준 오른쪽 어깨로 기울임.
    - iFacialMocap: Unity 오일러 각(x 위아래, y 좌우, z 기울기, 왼손 좌표계)이라 y, z 부호를 바꿈
    - VTube Studio: Live2D 얼굴 각도 순서(x 좌우, y 위아래, z 기울기)
    방향이 반대로 보이면 좌우 반전, 위아래 반전 선택이나 휴대폰 앱의 축 설정으로 맞춘다.
    """
    if rotation is None:
        return 0.0, 0.0, 0.0
    x, y, z = (math.radians(value) for value in rotation)
    if app == "vts":
        return x, -y, -z
    return -y, x, -z


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def to_values(frame: dict[str, Any], app: str, *, mirror: bool = True, flip_pitch: bool = False,
              center: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> dict[str, Any]:
    """수신한 프레임을 캐릭터 화면 값으로(웹캠 추적 값과 같은 항목에 ``arkit`` 추가).

    ``mirror`` 거울처럼(좌우 회전, 기울기, 왼쪽과 오른쪽 표정 반대로). ``center`` 정면 맞추기로 저장한 정면 각도(라디안).
    """
    if not frame.get("found"):
        return {"found": False, "source": "phone"}
    yaw, pitch, roll = head_angles(app, frame.get("rotation"))
    yaw, pitch, roll = yaw - center[0], pitch - center[1], roll - center[2]
    if flip_pitch:
        pitch = -pitch
    shapes = {name: round(_clamp(value, 0.0, 1.0), 3) for name, value in frame.get("shapes", {}).items()}
    if mirror:
        yaw, roll = -yaw, -roll
        shapes = {_side_swapped(name): value for name, value in shapes.items()}
    get = shapes.get
    return {"found": True, "source": "phone", "yaw": round(_clamp(yaw, -1.2, 1.2), 4), "pitch": round(_clamp(pitch, -1.2, 1.2), 4),
            "roll": round(_clamp(roll, -1.2, 1.2), 4), "blinkLeft": get("eyeBlinkLeft", 0.0), "blinkRight": get("eyeBlinkRight", 0.0),
            "mouth": get("jawOpen", 0.0), "smile": round((get("mouthSmileLeft", 0.0) + get("mouthSmileRight", 0.0)) / 2, 3), "arkit": shapes}


class PhoneError(ValueError):
    """잘못된 휴대폰 추적 설정. 메시지는 한국어 안내."""


def check_ip(ip: Any) -> str:
    """같은 네트워크의 휴대폰 IPv4 주소만 허용(공인 주소, 브로드캐스트 등 거부). 시험용으로 이 PC(127.0.0.1)도 허용."""
    text = str(ip or "").strip()
    try:
        address = ipaddress.IPv4Address(text)
    except ValueError:
        raise PhoneError("휴대폰 IP는 휴대폰 앱 화면에 표시된 숫자 주소(예: 192.168.0.12)") from None
    if address.is_unspecified or address.is_multicast or address == ipaddress.IPv4Address("255.255.255.255") \
            or not (address.is_private or address.is_loopback or address.is_link_local):
        raise PhoneError("같은 Wi-Fi(공유기)에 연결된 휴대폰의 내부 주소만 사용 가능(예: 192.168.0.12, 10.0.0.5)")
    return text


def local_address(phone_ip: str) -> str:
    """휴대폰으로 가는 이 PC의 네트워크 주소(수신 창구를 그 주소 하나에만 연다). UDP connect는 패킷을 보내지 않음."""
    if ipaddress.IPv4Address(phone_ip).is_loopback:
        return "127.0.0.1"
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((phone_ip, 9))
        return str(probe.getsockname()[0])
    except OSError as error:
        raise PhoneError(f"휴대폰 주소로 가는 네트워크를 찾지 못함: PC의 Wi-Fi나 유선 연결 확인({error})") from None
    finally:
        probe.close()


def saved_options(saved: dict[str, Any] | None = None) -> dict[str, Any]:
    """저장한 휴대폰 추적 설정. 다음 실행에도 같은 앱과 주소로 시작."""
    saved = settings.load() if saved is None else saved
    app = saved.get("phone_app") if saved.get("phone_app") in APPS else "ifacialmocap"
    center = tuple(float(saved.get(f"phone_center_{axis}", 0.0)) for axis in ("yaw", "pitch", "roll"))
    return {"enabled": saved.get("phone_enabled") is True, "app": app, "ip": str(saved.get("phone_ip") or ""),
            "mirror": saved.get("phone_mirror", True) is not False, "flip_pitch": saved.get("phone_flip_pitch") is True, "center": center}


class PhoneTracker:
    """휴대폰 얼굴 추적 수신기. ``start`` 로 시작(설정 저장), ``stop`` 으로 멈춤, ``calibrate`` 로 정면 맞추기, ``status`` 로 상태."""

    def __init__(self, tracking: TrackingState, *, rate: float = RATE) -> None:
        """포트는 모듈 상수(IFM_PORT, IFM_LISTEN_PORT, VTS_PORT)를 시작할 때 읽는다(시험에서 바꿀 수 있음)."""
        self.tracking = tracking
        self._interval = 1.0 / rate
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._socket: socket.socket | None = None
        options = saved_options()
        self.app: str = options["app"]
        self.ip: str = options["ip"]
        self.mirror: bool = options["mirror"]
        self.flip_pitch: bool = options["flip_pitch"]
        self.center: tuple[float, float, float] = options["center"]
        self.error = ""
        self.local = ""
        self.port = 0
        self._phone_port = 0
        self._last_packet = 0.0
        self._last_frame: dict[str, Any] | None = None
        self._last_values: dict[str, Any] = {"found": False}
        self._counter: list[float] = []
        self.dropped = 0
        self.hotkey: int | None = None

    # ------------------------------------------------------------------ 상태
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def receiving(self) -> bool:
        """최근(1초 안) 휴대폰 값을 받는 중인지. 받는 중이면 웹캠 추적 화면의 값은 쓰지 않는다."""
        return self.running and time.monotonic() - self._last_packet < STALE

    def status(self) -> dict[str, Any]:
        with self._lock:
            now = time.monotonic()
            fps = sum(1 for moment in self._counter if now - moment < 1.0)
            values = dict(self._last_values)
        receiving = self.receiving()
        return {"running": self.running, "receiving": receiving, "app": self.app, "ip": self.ip, "mirror": self.mirror,
                "flip_pitch": self.flip_pitch, "center": [round(value, 4) for value in self.center], "local": self.local, "port": self.port,
                "fps": fps if receiving else 0, "found": bool(values.get("found")) and receiving, "shapes": len(values.get("arkit", {})),
                "dropped": self.dropped, "error": self.error, "apps": APPS}

    # ------------------------------------------------------------------ 시작, 멈춤
    def start(self, app: Any = None, ip: Any = None, mirror: Any = None, flip_pitch: Any = None, *, save: bool = True) -> dict[str, Any]:
        """수신 시작(이미 실행 중이면 새 설정으로 다시). 주지 않은 항목은 이전 설정. 설정은 저장해 다음 실행에도 사용."""
        app = self.app if app is None else str(app)
        if app not in APPS:
            raise PhoneError("휴대폰 앱은 ifacialmocap(iFacialMocap) 또는 vts(VTube Studio)")
        ip = check_ip(self.ip if ip is None else ip)
        local = local_address(ip)
        self.stop(save=False)
        port = IFM_LISTEN_PORT if app == "ifacialmocap" else 0
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((local, port))
        except OSError as error:
            sock.close()
            busy = f"포트 {port}을(를) 다른 프로그램이 사용 중: VSeeFace, Warudo, VMagicMirror 등을 끈 뒤 다시 시작" if port else str(error)
            self.error = busy
            raise PhoneError(busy) from None
        sock.settimeout(0.2)
        with self._lock:
            self.app, self.ip, self.local, self.port = app, ip, local, int(sock.getsockname()[1])
            self._phone_port = IFM_PORT if app == "ifacialmocap" else VTS_PORT
            if mirror is not None:
                self.mirror = bool(mirror)
            if flip_pitch is not None:
                self.flip_pitch = bool(flip_pitch)
            self.error, self.dropped, self.hotkey = "", 0, None
            self._counter.clear()
            self._last_packet, self._last_frame = 0.0, None
            self._socket = sock
            self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(sock, self._stop), name="phone-tracking", daemon=True)
        self._thread.start()
        if save:
            self._save(enabled=True)
        return self.status()

    def stop(self, *, save: bool = True) -> dict[str, Any]:
        thread, sock = self._thread, self._socket
        self._stop.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)
        if sock is not None:
            sock.close()
        was_running = thread is not None
        self._thread, self._socket = None, None
        if was_running:
            self._publish({"found": False, "source": "phone"})
        if save:
            self._save(enabled=False)
        return self.status()

    def options(self, mirror: Any = None, flip_pitch: Any = None) -> dict[str, Any]:
        """실행 중에도 바꿀 수 있는 선택(거울처럼, 위아래 반전). 저장."""
        with self._lock:
            if mirror is not None:
                self.mirror = bool(mirror)
            if flip_pitch is not None:
                self.flip_pitch = bool(flip_pitch)
        self._save()
        return self.status()

    def calibrate(self, reset: bool = False) -> dict[str, Any]:
        """정면 맞추기: 지금 머리 각도를 정면으로 저장(휴대폰을 비스듬히 둔 경우). ``reset`` 은 되돌리기."""
        if reset:
            center = (0.0, 0.0, 0.0)
        else:
            frame = self._last_frame
            if not self.receiving() or frame is None or not frame.get("found"):
                raise PhoneError("휴대폰 값을 받는 중일 때 정면을 보고 다시 누르기")
            center = head_angles(self.app, frame.get("rotation"))
        with self._lock:
            self.center = tuple(round(value, 4) for value in center)  # type: ignore[assignment]
        self._save()
        return self.status()

    def _save(self, enabled: bool | None = None) -> None:
        saved = settings.load()
        saved.update(phone_app=self.app, phone_mirror=self.mirror, phone_flip_pitch=self.flip_pitch, phone_center_yaw=self.center[0],
                     phone_center_pitch=self.center[1], phone_center_roll=self.center[2])
        if self.ip:
            saved["phone_ip"] = self.ip
        if enabled is not None:
            saved["phone_enabled"] = enabled
        settings.save(saved)

    # ------------------------------------------------------------------ 수신
    def _request(self, sock: socket.socket) -> None:
        """휴대폰에 송신 요청. iFacialMocap은 시작 문자열, VTube Studio는 일정 시간 보내 달라는 JSON."""
        if self.app == "vts":
            message = json.dumps({"messageType": "iOSTrackingDataRequest", "time": VTS_REQUEST_SECONDS, "sentBy": "debutkit", "ports": [self.port]})
        else:
            message = IFM_START
        try:
            sock.sendto(message.encode("utf-8"), (self.ip, self._phone_port))
        except OSError as error:  # 네트워크가 바뀜, 휴대폰 꺼짐 등. 다음 요청 때 다시 시도
            self.error = f"휴대폰으로 요청을 보내지 못함: {error}"

    def _run(self, sock: socket.socket, stop: threading.Event) -> None:
        last_request = 0.0
        last_publish = 0.0
        pending: dict[str, Any] | None = None
        parse = parse_vts if self.app == "vts" else parse_ifacialmocap
        while not stop.is_set():
            now = time.monotonic()
            # VTube Studio는 1초마다 요청해야 계속 보냄. iFacialMocap은 한 번 시작하면 계속 보내므로 값이 끊겼을 때만 2초마다 다시 요청
            due = 1.0 if self.app == "vts" else (2.0 if now - self._last_packet > STALE else None)
            if due is not None and now - last_request >= due:
                self._request(sock)
                last_request = now
            try:
                data, address = sock.recvfrom(65535)
            except socket.timeout:
                data, address = b"", ("", 0)
            except OSError:
                if stop.is_set():
                    break
                time.sleep(0.2)
                continue
            if data:
                if address[0] != self.ip:  # 지정한 휴대폰이 아닌 곳에서 온 값은 버린다
                    self.dropped += 1
                else:
                    frame = parse(data)
                    if frame is not None:
                        now = time.monotonic()
                        with self._lock:
                            self._last_packet = now
                            self._last_frame = frame
                            self._counter = [moment for moment in self._counter if now - moment < 1.0] + [now]
                            if frame.get("hotkey"):
                                self.hotkey = frame["hotkey"]
                            self.error = ""
                        pending = to_values(frame, self.app, mirror=self.mirror, flip_pitch=self.flip_pitch, center=self.center)
            if pending is not None and time.monotonic() - last_publish >= self._interval:
                self._publish(pending)
                last_publish, pending = time.monotonic(), None

    def _publish(self, values: dict[str, Any]) -> None:
        with self._lock:
            self._last_values = values
        self.tracking.publish(values)
