"""VMC 프로토콜 송신: debutkit 얼굴 추적 값(웹캠, 휴대폰)을 Warudo, VSeeFace, VMagicMirror 등 VMC를 받는 프로그램으로 보낸다.

- VMC 프로토콜(OSC over UDP): ``/VMC/Ext/OK``, ``/VMC/Ext/T``, ``/VMC/Ext/Bone/Pos Head``(머리 회전 사원수, Unity 좌표),
  ``/VMC/Ext/Blend/Val``(VRM 표정 A, Blink_L, Blink_R, Joy와 퍼펙트 싱크 ARKit 52개), ``/VMC/Ext/Blend/Apply`` 를 묶음(bundle) 하나로
- 받는 곳은 이 PC(127.0.0.1)나 같은 네트워크의 내부 주소만. 얼굴 추적 값이 인터넷으로 나가지 않게 공인 주소는 거부
- 초당 최대 ``rate`` 번(기본 60). 얼굴을 찾지 못하면 보내지 않음(받는 프로그램이 마지막 자세 유지)
- 설정은 설정 폴더의 ``vmc.json``. 켜 두면 다음 오버레이 실행 때도 자동 시작
- 자세 보내기(캐릭터 그림 만들기의 포즈 그림): 화면이 보낸 VRM 정규화 뼈 회전을 Unity 좌표의 ``/VMC/Ext/Bone/Pos`` 로 초당 30번.
  얼굴 추적 송신이 켜져 있으면 머리와 표정은 얼굴 추적 값에 맡김. 화면에서 20초 동안 새 자세가 없으면 멈춤(화면을 닫은 경우)
"""

from __future__ import annotations

import ipaddress
import math
import queue
import socket
import struct
import threading
import time
from typing import Any

from .. import settings
from . import feature

DATA = "vmc.json"
DEFAULT_PORT = 39539  # VMC 프로토콜 기본 수신 포트(VSeeFace, Warudo, VMagicMirror)
RATE = (10, 120)
#: debutkit 추적 값 -> VRM 0.x 표정 이름(VMC 수신 프로그램 공통)
BLENDS = {"mouth": "A", "blinkLeft": "Blink_L", "blinkRight": "Blink_R", "smile": "Joy"}
_IMMEDIATELY = struct.pack(">II", 0, 1)
POSE_RATE = 30
POSE_HOLD = 20.0  # 화면이 이 시간 동안 새 자세를 보내지 않으면 멈춤
PACKET = 1400  # 묶음 하나의 최대 바이트(네트워크에서 쪼개지지 않게)
#: 포즈 그림의 표정 -> VRM 0.x 표정 이름(VMC 수신 프로그램 공통). 바꿀 때 다른 표정은 0으로
POSE_BLENDS = {"happy": "Joy", "angry": "Angry", "sad": "Sorrow", "relaxed": "Fun", "aa": "A", "blink": "Blink"}
_FINGERS = {"Thumb": ("Metacarpal", "Proximal", "Distal"), "Index": ("Proximal", "Intermediate", "Distal"),
            "Middle": ("Proximal", "Intermediate", "Distal"), "Ring": ("Proximal", "Intermediate", "Distal"),
            "Little": ("Proximal", "Intermediate", "Distal")}
_UNITY_JOINTS = ("Proximal", "Intermediate", "Distal")


def _unity_bones() -> dict[str, str]:
    """VRM 1.0 사람 모양 뼈 이름 -> Unity HumanBodyBones 이름(VMC). 엄지는 VRM 1.0이 한 칸 앞(Metacarpal)부터라 하나씩 밀림."""
    names = {bone: bone[0].upper() + bone[1:] for bone in ("hips", "spine", "chest", "upperChest", "neck", "head")}
    for side in ("left", "right"):
        upper = side.capitalize()
        for part in ("Shoulder", "UpperArm", "LowerArm", "Hand", "UpperLeg", "LowerLeg", "Foot", "Toes"):
            names[side + part] = upper + part
        for finger, joints in _FINGERS.items():
            for joint, unity in zip(joints, _UNITY_JOINTS, strict=True):
                names[f"{side}{finger}{joint}"] = f"{upper}{finger}{unity}"
    return names


UNITY_BONES = _unity_bones()


class VmcError(feature.FeatureError):
    pass


# --------------------------------------------------------------------------- OSC


def _pad(data: bytes) -> bytes:
    return data + b"\0" * (4 - len(data) % 4)


def osc_message(address: str, *args: Any) -> bytes:
    """OSC 메시지 하나. 인수는 str, int, float(32비트)."""
    tags = ","
    body = b""
    for value in args:
        if isinstance(value, str):
            tags += "s"
            body += _pad(value.encode("utf-8"))
        elif isinstance(value, bool) or isinstance(value, int):
            tags += "i"
            body += struct.pack(">i", int(value))
        else:
            tags += "f"
            body += struct.pack(">f", float(value))
    return _pad(address.encode("ascii")) + _pad(tags.encode("ascii")) + body


def osc_bundle(messages: list[bytes]) -> bytes:
    return _pad(b"#bundle") + _IMMEDIATELY + b"".join(struct.pack(">i", len(message)) + message for message in messages)


def parse_osc(packet: bytes) -> list[tuple[str, list[Any]]]:
    """시험과 확인용 OSC 해석(묶음 안의 메시지들)."""
    def string(data: bytes, offset: int) -> tuple[str, int]:
        end = data.index(b"\0", offset)
        return data[offset:end].decode("utf-8"), (end // 4 + 1) * 4

    if packet.startswith(b"#bundle\0"):
        found: list[tuple[str, list[Any]]] = []
        offset = 16
        while offset < len(packet):
            (size,) = struct.unpack(">i", packet[offset:offset + 4])
            found += parse_osc(packet[offset + 4:offset + 4 + size])
            offset += 4 + size
        return found
    address, offset = string(packet, 0)
    tags, offset = string(packet, offset)
    values: list[Any] = []
    for tag in tags[1:]:
        if tag == "s":
            value, offset = string(packet, offset)
            values.append(value)
        elif tag == "i":
            values.append(struct.unpack(">i", packet[offset:offset + 4])[0])
            offset += 4
        elif tag == "f":
            values.append(struct.unpack(">f", packet[offset:offset + 4])[0])
            offset += 4
    return [(address, values)]


# --------------------------------------------------------------------------- 추적 값 -> VMC


def head_quaternion(yaw: float, pitch: float, roll: float, *, mirror: bool = False) -> tuple[float, float, float, float]:
    """머리 회전(라디안)을 Unity 좌표 사원수(x, y, z, w)로. Unity 오일러 순서(Z, X, Y). 왼손 좌표라 고개 돌림, 기울임 부호를 바꾼다."""
    if mirror:
        yaw, roll = -yaw, -roll
    yaw, pitch, roll = -yaw, pitch, -roll
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    # q = qY * qX * qZ
    x = cy * sp * cr + sy * cp * sr
    y = sy * cp * cr - cy * sp * sr
    z = cy * cp * sr - sy * sp * cr
    w = cy * cp * cr + sy * sp * sr
    return (round(x, 6), round(y, 6), round(z, 6), round(w, 6))


def frame(values: dict[str, Any], *, perfect_sync: bool = True, mirror: bool = False, clock: float | None = None) -> bytes:
    """추적 값 하나를 VMC 묶음으로."""
    messages = [osc_message("/VMC/Ext/OK", 1), osc_message("/VMC/Ext/T", float(clock if clock is not None else time.monotonic()))]
    qx, qy, qz, qw = head_quaternion(float(values.get("yaw", 0.0)), float(values.get("pitch", 0.0)), float(values.get("roll", 0.0)), mirror=mirror)
    messages.append(osc_message("/VMC/Ext/Bone/Pos", "Head", 0.0, 0.0, 0.0, qx, qy, qz, qw))
    blends = dict(BLENDS)
    if mirror:
        blends["blinkLeft"], blends["blinkRight"] = "Blink_R", "Blink_L"
    for key, name in blends.items():
        if key in values:
            messages.append(osc_message("/VMC/Ext/Blend/Val", name, float(values[key])))
    if perfect_sync:
        for name, value in (values.get("arkit") or {}).items():
            if mirror:
                name = name.replace("Left", "\0").replace("Right", "Left").replace("\0", "Right")
            messages.append(osc_message("/VMC/Ext/Blend/Val", name, float(value)))
    messages.append(osc_message("/VMC/Ext/Blend/Apply"))
    return osc_bundle(messages)


def unity_bone(values: list[float]) -> tuple[float, ...]:
    """VRM 1.0 방향(three.js 오른손 좌표, 모델이 +Z를 봄)의 [회전 x, y, z, w, 위치 x, y, z] -> Unity(왼손 좌표, x축 거울)의 위치와 회전."""
    qx, qy, qz, qw, px, py, pz = values
    return (-px, py, pz, qx, -qy, -qz, qw)


def check_pose(data: dict[str, Any]) -> tuple[dict[str, tuple[float, ...]], str | None]:
    """화면이 보낸 자세 확인: ``{"bones": {VRM 뼈: [qx, qy, qz, qw, px, py, pz]}, "expression": "happy" | null}``."""
    bones = data.get("bones")
    if not isinstance(bones, dict) or not bones or len(bones) > len(UNITY_BONES):
        raise VmcError("보낼 자세가 없음")
    found: dict[str, tuple[float, ...]] = {}
    for bone, values in bones.items():
        if bone not in UNITY_BONES or not isinstance(values, list) or len(values) != 7:
            raise VmcError("자세 값이 올바르지 않음")
        for index, value in enumerate(values):
            limit = 1.001 if index < 4 else 10.0  # 사원수 성분, 위치(m)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > limit:
                raise VmcError("자세 값이 올바르지 않음")
        found[UNITY_BONES[bone]] = unity_bone([float(value) for value in values])
    expression = data.get("expression")
    if expression is not None and expression != "neutral" and expression not in POSE_BLENDS:
        raise VmcError("표정 이름이 올바르지 않음")
    return found, expression


def pose_packets(bones: dict[str, tuple[float, ...]], expression: str | None, *, skip_face: bool = False,
                 clock: float | None = None) -> list[bytes]:
    """자세 하나를 VMC 묶음들로(묶음마다 PACKET 바이트 이하). skip_face면 머리와 표정은 빼고(얼굴 추적 송신 몫)."""
    messages = [osc_message("/VMC/Ext/OK", 1), osc_message("/VMC/Ext/T", float(clock if clock is not None else time.monotonic())),
                osc_message("/VMC/Ext/Root/Pos", "root", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)]
    for name, values in bones.items():
        if not (skip_face and name == "Head"):
            messages.append(osc_message("/VMC/Ext/Bone/Pos", name, *values))
    if expression is not None and not skip_face:
        for key, name in POSE_BLENDS.items():
            messages.append(osc_message("/VMC/Ext/Blend/Val", name, 1.0 if key == expression else 0.0))
        messages.append(osc_message("/VMC/Ext/Blend/Apply"))
    packets: list[bytes] = []
    chunk: list[bytes] = []
    for message in messages:
        if chunk and len(osc_bundle([*chunk, message])) > PACKET:
            packets.append(osc_bundle(chunk))
            chunk = []
        chunk.append(message)
    packets.append(osc_bundle(chunk))
    return packets


def check_target(host: Any, port: Any) -> tuple[str, int]:
    """받는 곳 확인: 이 PC나 내부 네트워크 주소, 포트 1024~65535."""
    text = str(host or "").strip() or "127.0.0.1"
    if text == "localhost":
        text = "127.0.0.1"
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        raise VmcError("받는 곳은 IP 주소(예: 127.0.0.1, 192.168.0.20)") from None
    if not (address.is_loopback or address.is_private) or address.is_unspecified or address.is_multicast:
        raise VmcError("받는 곳은 이 PC(127.0.0.1)나 같은 네트워크의 내부 주소만(얼굴 추적 값과 자세가 인터넷으로 나가지 않게)")
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise VmcError("포트는 1024에서 65535 사이(VMC 기본 39539)")
    return str(address), port


class VmcSender:
    """추적 상태를 구독해 VMC 묶음을 보낸다. ``start`` 후 ``stop``."""

    def __init__(self, tracking: Any, *, sock: Any = None) -> None:
        self.tracking = tracking
        self._sock = sock
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._subscriber: Any = None
        self.host, self.port = "127.0.0.1", DEFAULT_PORT
        self.perfect_sync, self.mirror, self.rate = True, False, 60
        self.sent = 0
        self.error = ""
        self.last_sent = 0.0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, host: Any = None, port: Any = DEFAULT_PORT, *, perfect_sync: bool = True, mirror: bool = False, rate: Any = 60) -> None:
        host, port = check_target(host, port)
        if isinstance(rate, bool) or not isinstance(rate, int) or not RATE[0] <= rate <= RATE[1]:
            raise VmcError(f"초당 보내는 횟수는 {RATE[0]}에서 {RATE[1]} 사이")
        self.stop()
        with self._lock:
            self.host, self.port, self.perfect_sync, self.mirror, self.rate = host, port, perfect_sync, mirror, rate
            self.sent, self.error = 0, ""
            self._stop = threading.Event()
            self._subscriber, _ = self.tracking.subscribe(queue.Queue(maxsize=240))
            self._thread = threading.Thread(target=self._loop, name="debutkit-vmc", daemon=True)
            self._thread.start()

    def _loop(self) -> None:
        sock = self._sock or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        interval = 1.0 / self.rate
        try:
            while not self._stop.is_set():
                try:
                    latest = self._subscriber.get(timeout=0.25)
                except queue.Empty:
                    continue
                while True:  # 밀린 값은 건너뛰고 마지막 값만
                    try:
                        latest = self._subscriber.get_nowait()
                    except queue.Empty:
                        break
                if not latest.get("found"):
                    continue
                wait = self.last_sent + interval - time.monotonic()
                if wait > 0 and self._stop.wait(wait):
                    break
                try:
                    sock.sendto(frame(latest, perfect_sync=self.perfect_sync, mirror=self.mirror), (self.host, self.port))
                    self.sent += 1
                    self.error = ""
                except OSError as error:
                    self.error = f"보내기 실패: {error}"
                self.last_sent = time.monotonic()
        finally:
            if self._sock is None:
                sock.close()

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if self._subscriber is not None:
            self.tracking.unsubscribe(self._subscriber)
            self._subscriber = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1)

    def status(self) -> dict[str, Any]:
        return {"running": self.running, "host": self.host, "port": self.port, "perfect_sync": self.perfect_sync, "mirror": self.mirror,
                "rate": self.rate, "sent": self.sent, "error": self.error, "receiving": bool(self.tracking.current.get("found"))}


class PoseSender:
    """포즈 그림의 자세를 초당 POSE_RATE번 다시 보낸다(받는 프로그램이 마지막 자세를 유지하도록). ``update`` 로 시작과 갱신, ``stop``."""

    def __init__(self, face: VmcSender | None = None, *, sock: Any = None) -> None:
        self.face = face
        self._sock = sock
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._active = False  # 보내는 중(멈추기로 한 순간 바로 False라 바로 다음 갱신이 새로 시작)
        remembered = saved()
        self.host = str(remembered.get("host") or "127.0.0.1")
        self.port = remembered.get("port") if isinstance(remembered.get("port"), int) else DEFAULT_PORT
        self.bones: dict[str, tuple[float, ...]] = {}
        self.expression: str | None = None
        self.until = 0.0
        self.sent = 0
        self.error = ""

    @property
    def running(self) -> bool:
        return self._active

    def _face_running(self) -> bool:
        return self.face is not None and self.face.running

    def update(self, host: Any, port: Any, data: dict[str, Any]) -> None:
        host, port = check_target(host, port)
        bones, expression = check_pose(data)
        with self._lock:
            if (host, port) != (self.host, self.port):
                self.sent = 0
            self.host, self.port, self.bones, self.expression = host, port, bones, expression
            self.until = time.monotonic() + POSE_HOLD
            self.error = ""
            if not self._active:
                self._active = True
                self._stop = threading.Event()
                self._thread = threading.Thread(target=self._loop, name="debutkit-vmc-pose", daemon=True)
                self._thread.start()

    def _loop(self) -> None:
        sock = self._sock or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        stop = self._stop
        try:
            while not stop.is_set():
                with self._lock:
                    if stop.is_set():
                        break
                    if time.monotonic() > self.until:
                        self.error = "화면에서 새 자세가 없어 멈춤"
                        self._active = False
                        break
                    target, packets = (self.host, self.port), pose_packets(self.bones, self.expression, skip_face=self._face_running())
                try:
                    for packet in packets:
                        sock.sendto(packet, target)
                    self.sent += 1
                except OSError as error:
                    self.error = f"보내기 실패: {error}"
                stop.wait(1.0 / POSE_RATE)
        finally:
            if self._sock is None:
                sock.close()

    def stop(self) -> None:
        with self._lock:
            self._stop.set()
            self._active = False
            thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1)

    def status(self) -> dict[str, Any]:
        return {"running": self.running, "host": self.host, "port": self.port, "bones": len(self.bones), "expression": self.expression,
                "sent": self.sent, "error": self.error, "face": self._face_running()}


def saved() -> dict[str, Any]:
    return settings.load_data(DATA)


def make_feature(context: feature.Context) -> feature.Feature:
    """``/vmc`` 설정 화면, ``/vmc/status``, ``POST /vmc/start`` (``{"host", "port", "perfect_sync", "mirror", "rate"}``), ``POST /vmc/stop``.

    자세 보내기: ``POST /vmc/pose`` (``{"host", "port", "bones", "expression"}``, 시작과 갱신), ``POST /vmc/pose/stop``.
    """
    sender = VmcSender(context.tracking)
    poser = PoseSender(sender)

    def pose(data: dict[str, Any]) -> dict[str, Any]:
        poser.update(data.get("host") or poser.host, data.get("port", poser.port), data)
        return poser.status()

    def pose_stop(data: dict[str, Any]) -> dict[str, Any]:
        poser.stop()
        return poser.status()

    def stop_all() -> None:
        sender.stop()
        poser.stop()

    def start(data: dict[str, Any]) -> dict[str, Any]:
        options = {"host": data.get("host"), "port": data.get("port", DEFAULT_PORT), "perfect_sync": data.get("perfect_sync") is not False,
                   "mirror": data.get("mirror") is True, "rate": data.get("rate", 60)}
        sender.start(options.pop("host"), options.pop("port"), **options)
        settings.save_data(DATA, {"enabled": True, "host": sender.host, "port": sender.port, "perfect_sync": sender.perfect_sync,
                                  "mirror": sender.mirror, "rate": sender.rate})
        return sender.status()

    def stop(data: dict[str, Any]) -> dict[str, Any]:
        sender.stop()
        settings.save_data(DATA, {**saved(), "enabled": False})
        return sender.status()

    remembered = saved()
    if remembered.get("enabled") and context.tracking is not None:
        try:
            sender.start(remembered.get("host"), remembered.get("port", DEFAULT_PORT), perfect_sync=remembered.get("perfect_sync") is not False,
                         mirror=remembered.get("mirror") is True, rate=remembered.get("rate", 60))
        except VmcError as error:
            context.notify(f"VMC 송신: {error}")
    return feature.Feature(name="vmc", static={"/vmc": "vmc.html"}, get={"/vmc/status": lambda query: {**sender.status(), "pose": poser.status()}},
                           post={"/vmc/start": start, "/vmc/stop": stop, "/vmc/pose": pose, "/vmc/pose/stop": pose_stop},
                           body_limit={"/vmc/pose": 65536}, stop=stop_all)
