"""휴대폰 얼굴 추적 수신(overlay/phone.py): iFacialMocap, VTube Studio 아이폰 앱 형식, 정면 맞추기, 서버 경로."""

from __future__ import annotations

import http.client
import json
import math
import re
import socket
import threading
import time
from pathlib import Path

import pytest

from debutkit import settings
from debutkit.overlay import phone as phones
from debutkit.overlay import tracking
from debutkit.overlay.server import OverlayServer
from debutkit.overlay.tracking import TrackingState

IFM_FRAME = ("eyeBlink_L-80|eyeBlink_R-10|jawOpen-50|mouthSmile_L-40|mouthSmile_R-60|mouthLeft-20|tongueOut-0|"
             "=head#10.0,-20.0,5.0,0.01,0.02,0.03|rightEye#1.0,2.0,3.0|leftEye#4.0,5.0,6.0|")
VTS_FRAME = {"Timestamp": 1700000000000, "Hotkey": 3, "FaceFound": True, "Rotation": {"x": 20.0, "y": 10.0, "z": 5.0},
             "Position": {"x": 0.0, "y": 0.0, "z": 0.0}, "EyeLeft": {"x": 0, "y": 0, "z": 0}, "EyeRight": {"x": 0, "y": 0, "z": 0},
             "BlendShapes": [{"k": "EyeBlinkLeft", "v": 0.8}, {"k": "JawOpen", "v": 0.5}, {"k": "MouthSmileRight", "v": 0.6}, {"k": "Unknown", "v": 1}],
             "NewField": "무시"}


def test_arkit_names_accept_each_app_spelling():
    assert len(phones.ARKIT_NAMES) == 52 == len(set(phones.ARKIT_NAMES))
    assert phones.arkit_name("eyeBlink_L") == "eyeBlinkLeft"  # iFacialMocap, ARKit 원래 문자열
    assert phones.arkit_name("EyeBlinkLeft") == "eyeBlinkLeft"  # VTube Studio
    assert phones.arkit_name("mouthSmile_R") == "mouthSmileRight"
    assert phones.arkit_name("mouthLeft") == "mouthLeft" and phones.arkit_name("jawOpen") == "jawOpen"
    assert phones.arkit_name("mouth_L") is None and phones.arkit_name("smile") is None


def test_ifacialmocap_frames_v1_and_v2():
    frame = phones.parse_ifacialmocap(IFM_FRAME.encode())
    assert frame["found"] is True and frame["rotation"] == (10.0, -20.0, 5.0)
    assert frame["shapes"]["eyeBlinkLeft"] == 0.8 and frame["shapes"]["mouthLeft"] == 0.2 and frame["shapes"]["tongueOut"] == 0.0
    v2 = phones.parse_ifacialmocap("eyeBlink_L&80|mouthSmile_R&-25|=head#1,2,3,0,0,0|")  # FaceMotion3D 음수 값
    assert v2["shapes"] == {"eyeBlinkLeft": 0.8, "mouthSmileRight": -0.25}
    v1_negative = phones.parse_ifacialmocap("mouthSmile_R--25|=head#1,2,3,0,0,0|")
    assert v1_negative["shapes"] == {"mouthSmileRight": -0.25}
    tcp = phones.parse_ifacialmocap(IFM_FRAME + "___iFacialMocap")
    assert tcp["rotation"] == (10.0, -20.0, 5.0)
    assert phones.parse_ifacialmocap(b"hello") is None and phones.parse_ifacialmocap("=|") is None
    assert phones.parse_ifacialmocap("eyeBlink_L-x|=head#a,b,c|") is None


def test_vts_frames():
    frame = phones.parse_vts(json.dumps(VTS_FRAME).encode())
    assert frame == {"found": True, "shapes": {"eyeBlinkLeft": 0.8, "jawOpen": 0.5, "mouthSmileRight": 0.6}, "rotation": (20.0, 10.0, 5.0), "hotkey": 3}
    assert phones.parse_vts(b"not json") is None and phones.parse_vts(b"[1]") is None and phones.parse_vts(b'{"a": 1}') is None
    lost = phones.parse_vts(json.dumps({"FaceFound": False, "BlendShapes": [], "Hotkey": -1}))
    assert lost == {"found": False, "shapes": {}, "rotation": None, "hotkey": None}
    assert phones.to_values(lost, "vts") == {"found": False, "source": "phone"}


def test_values_follow_debutkit_axes_mirror_and_center():
    frame = phones.parse_ifacialmocap(IFM_FRAME)
    plain = phones.to_values(frame, "ifacialmocap", mirror=False)
    # iFacialMocap(Unity 오일러): yaw = -y, pitch = x, roll = -z
    assert plain["yaw"] == round(math.radians(20), 4) and plain["pitch"] == round(math.radians(10), 4) and plain["roll"] == round(math.radians(-5), 4)
    assert plain["blinkLeft"] == 0.8 and plain["blinkRight"] == 0.1 and plain["mouth"] == 0.5 and plain["smile"] == 0.5
    assert plain["source"] == "phone" and plain["arkit"]["mouthLeft"] == 0.2 and len(plain["arkit"]) == 7
    mirrored = phones.to_values(frame, "ifacialmocap", mirror=True)
    assert mirrored["yaw"] == -plain["yaw"] and mirrored["roll"] == -plain["roll"] and mirrored["pitch"] == plain["pitch"]
    assert mirrored["blinkLeft"] == 0.1 and mirrored["blinkRight"] == 0.8
    assert mirrored["arkit"]["mouthRight"] == 0.2 and "mouthLeft" not in mirrored["arkit"]
    flipped = phones.to_values(frame, "ifacialmocap", mirror=False, flip_pitch=True)
    assert flipped["pitch"] == -plain["pitch"]
    centered = phones.to_values(frame, "ifacialmocap", mirror=False, center=phones.head_angles("ifacialmocap", frame["rotation"]))
    assert centered["yaw"] == centered["pitch"] == centered["roll"] == 0
    vts = phones.to_values(phones.parse_vts(json.dumps(VTS_FRAME)), "vts", mirror=False)
    # VTube Studio(Live2D 각도): yaw = x, pitch = -y, roll = -z
    assert vts["yaw"] == round(math.radians(20), 4) and vts["pitch"] == round(math.radians(-10), 4) and vts["roll"] == round(math.radians(-5), 4)
    huge = phones.to_values({"found": True, "shapes": {"jawOpen": 3.0, "eyeBlinkLeft": -1.0}, "rotation": (500.0, 0.0, 0.0)}, "ifacialmocap")
    assert huge["pitch"] == 1.2 and huge["mouth"] == 1.0 and huge["arkit"]["eyeBlinkRight"] == 0.0


def test_only_lan_phone_addresses():
    for good in ("192.168.0.12", "10.0.0.5", "172.16.3.4", "169.254.1.2", "127.0.0.1"):
        assert phones.check_ip(f" {good} ") == good
    for bad in ("8.8.8.8", "abc", "", None, "0.0.0.0", "224.0.0.1", "255.255.255.255", "192.168.0.300", "::1"):
        with pytest.raises(phones.PhoneError):
            phones.check_ip(bad)


def test_tracking_clean_keeps_arkit_shapes():
    cleaned = tracking.clean({"found": True, "arkit": {"eyeBlink_L": 0.5, "JawOpen": 2, "bad": 1, "mouthLeft": "x", "cheekPuff": float("nan")}})
    assert cleaned == {"found": True, "arkit": {"eyeBlinkLeft": 0.5, "jawOpen": 1.0}}
    assert "arkit" not in tracking.clean({"found": True, "arkit": [1, 2]})


def test_character_page_uses_same_arkit_names():
    script = Path(__file__).parents[1].joinpath("src", "debutkit", "overlay", "static", "character.js").read_text(encoding="utf-8")
    block = re.search(r"export const ARKIT = \[(.*?)\];", script, re.S).group(1)
    assert tuple(re.findall(r'"(\w+)"', block)) == phones.ARKIT_NAMES


class FakePhone:
    """아이폰 앱 흉내: 요청을 받으면 iFacialMocap은 보낸 곳으로, VTube Studio는 요청에 적힌 포트로 프레임을 계속 보낸다."""

    def __init__(self, app: str, frame: bytes) -> None:
        self.app, self.frame = app, frame
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.02)
        self.port = self.sock.getsockname()[1]
        self.requests: list[bytes] = []
        self.target: tuple[str, int] | None = None
        self.sending = True
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                data, address = self.sock.recvfrom(4096)
                self.requests.append(data)
                if self.app == "vts":
                    self.target = (address[0], json.loads(data)["ports"][0])
                else:
                    self.target = address
            except (socket.timeout, OSError):
                pass
            if self.target and self.sending:
                try:
                    self.sock.sendto(self.frame, self.target)
                except OSError:
                    pass

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self.sock.close()


@pytest.fixture
def fake_ports(monkeypatch):
    def use(app: str, frame: bytes) -> FakePhone:
        fake = FakePhone(app, frame)
        monkeypatch.setattr(phones, "IFM_PORT", fake.port)
        monkeypatch.setattr(phones, "IFM_LISTEN_PORT", 0)  # 시험: PC 쪽은 비어 있는 번호
        monkeypatch.setattr(phones, "VTS_PORT", fake.port)
        made.append(fake)
        return fake

    made: list[FakePhone] = []
    yield use
    for fake in made:
        fake.close()


def wait(predicate, seconds: float = 3.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


@pytest.mark.parametrize("app", ["ifacialmocap", "vts"])
def test_receiver_requests_and_publishes_phone_values(fake_ports, app):
    fake = fake_ports(app, IFM_FRAME.encode() if app == "ifacialmocap" else json.dumps(VTS_FRAME).encode())
    state = TrackingState()
    receiver = phones.PhoneTracker(state)
    queue_, _ = state.subscribe()
    status = receiver.start(app, "127.0.0.1", mirror=False)
    assert status["running"] and status["local"] == "127.0.0.1"
    assert wait(receiver.receiving)
    request = fake.requests[0].decode()
    if app == "vts":
        assert json.loads(request) == {"messageType": "iOSTrackingDataRequest", "time": phones.VTS_REQUEST_SECONDS, "sentBy": "debutkit", "ports": [receiver.port]}
    else:
        assert request == phones.IFM_START
    values = queue_.get(timeout=2)
    assert values["found"] is True and values["source"] == "phone" and values["blinkLeft"] == 0.8 and values["arkit"]["jawOpen"] == 0.5
    assert wait(lambda: receiver.status()["fps"] > 3)
    status = receiver.status()
    assert status["receiving"] and status["found"] and status["shapes"] >= 3 and status["app"] == app
    if app == "vts":
        assert receiver.hotkey == 3
    saved = settings.load()
    assert saved["phone_enabled"] is True and saved["phone_app"] == app and saved["phone_ip"] == "127.0.0.1" and saved["phone_mirror"] is False

    receiver.calibrate()
    assert receiver.center == tuple(round(value, 4) for value in phones.head_angles(app, (10.0, -20.0, 5.0) if app == "ifacialmocap" else (20.0, 10.0, 5.0)))
    assert settings.load()["phone_center_yaw"] == receiver.center[0]
    assert wait(lambda: state.current.get("yaw") == 0 and state.current.get("pitch") == 0)

    receiver.calibrate(reset=True)
    assert receiver.center == (0.0, 0.0, 0.0)
    receiver.options(mirror=True)
    assert wait(lambda: state.current.get("blinkRight") == 0.8)  # 거울처럼: 왼눈 값이 오른눈으로

    receiver.stop()
    assert not receiver.running and state.current["found"] is False
    assert settings.load()["phone_enabled"] is False
    with pytest.raises(phones.PhoneError):
        receiver.calibrate()


def test_values_from_other_devices_are_ignored(fake_ports):
    fake_ports("ifacialmocap", IFM_FRAME.encode())
    state = TrackingState()
    receiver = phones.PhoneTracker(state)
    receiver.start("ifacialmocap", "127.0.0.1")
    assert wait(receiver.receiving)
    receiver.ip = "127.0.0.9"  # 지정한 휴대폰이 아닌 주소에서 오는 것처럼
    assert wait(lambda: receiver.dropped > 3)
    assert wait(lambda: not receiver.receiving())
    receiver.stop()


def test_lost_phone_is_requested_again(fake_ports):
    fake = fake_ports("ifacialmocap", IFM_FRAME.encode())
    receiver = phones.PhoneTracker(TrackingState())
    receiver.start("ifacialmocap", "127.0.0.1")
    assert wait(receiver.receiving)
    fake.sending = False  # 휴대폰 앱을 껐다 켬
    assert wait(lambda: not receiver.receiving())
    count = len(fake.requests)
    assert wait(lambda: len(fake.requests) > count, seconds=4)  # 값이 끊기면 2초마다 다시 시작 요청
    fake.sending = True
    assert wait(receiver.receiving)
    receiver.stop()


def test_busy_port_and_bad_requests(monkeypatch):
    blocker = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    blocker.bind(("127.0.0.1", 0))
    monkeypatch.setattr(phones, "IFM_LISTEN_PORT", blocker.getsockname()[1])
    receiver = phones.PhoneTracker(TrackingState())
    try:
        with pytest.raises(phones.PhoneError, match="다른 프로그램"):
            receiver.start("ifacialmocap", "127.0.0.1")
        assert "다른 프로그램" in receiver.status()["error"] and not receiver.running
    finally:
        blocker.close()
    with pytest.raises(phones.PhoneError):
        receiver.start("android", "127.0.0.1")
    with pytest.raises(phones.PhoneError):
        receiver.start("vts", "8.8.8.8")


def request(srv, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json", **(headers or {})})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, data


def test_server_routes_and_webcam_yields_to_phone(fake_ports):
    fake_ports("ifacialmocap", IFM_FRAME.encode())
    srv = OverlayServer([], port=0).start()
    try:
        status, page = request(srv, "GET", "/phone")
        assert status == 200 and "휴대폰 얼굴 추적".encode() in page and b"/phone/status" in page
        status, body = request(srv, "GET", "/phone/status")
        assert status == 200 and json.loads(body)["running"] is False and "vts" in json.loads(body)["apps"]
        status, body = request(srv, "POST", "/phone/start", {"app": "ifacialmocap", "ip": "8.8.8.8"})
        assert status == 400 and "내부 주소" in json.loads(body)["error"]
        status, body = request(srv, "POST", "/phone/start", {"app": "ifacialmocap", "ip": "127.0.0.1", "mirror": False})
        assert status == 200 and json.loads(body)["running"] is True
        assert wait(srv.phone.receiving)
        status, body = request(srv, "POST", "/tracking", {"found": True, "yaw": 0.9})
        assert status == 200 and body == b"phone"  # 휴대폰 값을 받는 중에는 웹캠 값을 쓰지 않음
        assert srv.tracking.current["source"] == "phone"
        status, body = request(srv, "POST", "/phone/options", {"mirror": True, "flip_pitch": "yes"})
        assert status == 200 and json.loads(body)["mirror"] is True and json.loads(body)["flip_pitch"] is False
        status, body = request(srv, "POST", "/phone/calibrate", {})
        assert status == 200 and json.loads(body)["center"] != [0, 0, 0]
        status, _ = request(srv, "POST", "/phone/start", {"app": "ifacialmocap", "ip": "127.0.0.1"}, {"Origin": "https://evil.example"})
        assert status == 403
        status, body = request(srv, "POST", "/phone/stop", {})
        assert status == 200 and json.loads(body)["running"] is False
        status, body = request(srv, "POST", "/tracking", {"found": True, "yaw": 0.9})
        assert body == b"ok" and srv.tracking.current["source"] == "webcam" and srv.tracking.current["yaw"] == 0.9
        status, body = request(srv, "POST", "/phone/calibrate", {})
        assert status == 400
    finally:
        srv.stop()


def test_overlay_starts_saved_phone_tracking_and_keeps_setting(fake_ports):
    fake_ports("vts", json.dumps(VTS_FRAME).encode())
    settings.save({"phone_enabled": True, "phone_app": "vts", "phone_ip": "127.0.0.1", "phone_mirror": False})
    srv = OverlayServer([], port=0).start()
    try:
        assert srv.phone.running and srv.phone.app == "vts" and srv.phone.mirror is False
        assert wait(srv.phone.receiving)
    finally:
        srv.stop()
    assert not srv.phone.running and settings.load()["phone_enabled"] is True  # 다음 실행에도 시작


def test_overlay_reports_saved_phone_errors():
    settings.save({"phone_enabled": True, "phone_app": "vts", "phone_ip": "8.8.8.8"})
    srv = OverlayServer([], port=0)
    try:
        assert srv.start_phone() is False and not srv.phone.running
        assert any("휴대폰 얼굴 추적" in event.text for event in srv.hub.history)
    finally:
        srv.stop()
