import http.client
import json
import math
import socket
import time

import pytest

from debutkit import settings
from debutkit.overlay import vmc
from debutkit.overlay.server import OverlayServer
from debutkit.overlay.tracking import TrackingState


def test_osc_round_trip_and_padding():
    message = vmc.osc_message("/VMC/Ext/Blend/Val", "Blink_L", 0.5)
    assert len(message) % 4 == 0 and vmc.parse_osc(message) == [("/VMC/Ext/Blend/Val", ["Blink_L", 0.5])]
    bundle = vmc.osc_bundle([vmc.osc_message("/VMC/Ext/OK", 1), vmc.osc_message("/VMC/Ext/Blend/Apply"), vmc.osc_message("/a", "한글")])
    assert bundle.startswith(b"#bundle\0") and vmc.parse_osc(bundle) == [("/VMC/Ext/OK", [1]), ("/VMC/Ext/Blend/Apply", []), ("/a", ["한글"])]


def test_head_quaternion_is_unit_and_signs():
    assert vmc.head_quaternion(0, 0, 0) == (0.0, 0.0, 0.0, 1.0)
    for angles in ((0.4, -0.2, 0.1), (-1.1, 0.9, -0.7)):
        q = vmc.head_quaternion(*angles)
        assert math.isclose(sum(value * value for value in q), 1.0, abs_tol=1e-5)
    yaw = vmc.head_quaternion(0.5, 0, 0)
    pitch = vmc.head_quaternion(0, 0.5, 0)
    roll = vmc.head_quaternion(0, 0, 0.5)
    assert yaw[1] < 0 and yaw[0] == yaw[2] == 0  # 고개 돌림은 y축(왼손 좌표라 부호 반대)
    assert pitch[0] > 0 and pitch[1] == pitch[2] == 0
    assert roll[2] < 0 and roll[0] == roll[1] == 0
    assert vmc.head_quaternion(0.5, 0, 0.3, mirror=True) == vmc.head_quaternion(-0.5, 0, -0.3)


def test_frame_contains_head_blends_and_perfect_sync():
    values = {"found": True, "yaw": 0.2, "pitch": 0.1, "roll": 0.0, "mouth": 0.7, "blinkLeft": 1.0, "blinkRight": 0.0, "smile": 0.3,
              "arkit": {"jawOpen": 0.6, "eyeBlinkLeft": 0.9}}
    parsed = vmc.parse_osc(vmc.frame(values, clock=12.5))
    addresses = [address for address, _ in parsed]
    assert addresses[0] == "/VMC/Ext/OK" and addresses[-1] == "/VMC/Ext/Blend/Apply" and ("/VMC/Ext/T", [12.5]) in parsed
    head = next(args for address, args in parsed if address == "/VMC/Ext/Bone/Pos")
    assert head[0] == "Head" and head[1:4] == [0.0, 0.0, 0.0]
    blends = {args[0]: round(args[1], 3) for address, args in parsed if address == "/VMC/Ext/Blend/Val"}
    assert blends == {"A": 0.7, "Blink_L": 1.0, "Blink_R": 0.0, "Joy": 0.3, "jawOpen": 0.6, "eyeBlinkLeft": 0.9}
    mirrored = {args[0]: round(args[1], 3) for address, args in vmc.parse_osc(vmc.frame(values, mirror=True, perfect_sync=False))
                if address == "/VMC/Ext/Blend/Val"}
    assert mirrored == {"A": 0.7, "Blink_R": 1.0, "Blink_L": 0.0, "Joy": 0.3}
    swapped = {args[0] for address, args in vmc.parse_osc(vmc.frame(values, mirror=True)) if address == "/VMC/Ext/Blend/Val"}
    assert "eyeBlinkRight" in swapped and "eyeBlinkLeft" not in swapped


@pytest.mark.parametrize("host, port, message", [("8.8.8.8", 39539, "내부 주소만"), ("vseeface.local", 39539, "IP 주소"), ("127.0.0.1", 80, "포트"),
                                                 ("0.0.0.0", 39539, "내부 주소만"), ("224.0.0.1", 39539, "내부 주소만")])
def test_target_must_stay_local(host, port, message):
    with pytest.raises(vmc.VmcError, match=message):
        vmc.check_target(host, port)
    assert vmc.check_target("localhost", 39539) == ("127.0.0.1", 39539) and vmc.check_target("192.168.0.20", 39540)[0] == "192.168.0.20"


def receiver():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(3)
    return sock


def test_sender_sends_latest_found_values_only():
    tracking = TrackingState()
    sock = receiver()
    sender = vmc.VmcSender(tracking)
    try:
        sender.start("127.0.0.1", sock.getsockname()[1], rate=120)
        tracking.publish({"found": False, "yaw": 0.3})
        tracking.publish({"found": True, "yaw": 0.3, "mouth": 0.4})
        packet, _ = sock.recvfrom(65536)
        assert ("/VMC/Ext/Blend/Val", ["A", pytest.approx(0.4)]) in vmc.parse_osc(packet)
        deadline = time.time() + 2
        while sender.sent < 1 and time.time() < deadline:
            time.sleep(0.01)
        assert sender.status()["running"] and sender.status()["sent"] >= 1
        with pytest.raises(vmc.VmcError, match="초당"):
            sender.start("127.0.0.1", 39539, rate=500)
    finally:
        sender.stop()
        sock.close()
    assert not sender.running and tracking._subscribers == []


def request(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    return response.status, json.loads(response.read() or b"{}")


def test_overlay_routes_save_and_restart(capsys):
    sock = receiver()
    target = sock.getsockname()[1]
    server = OverlayServer([], port=0).start()
    try:
        status, body = request(server.port, "GET", "/vmc/status")
        assert status == 200 and body["running"] is False
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        conn.request("GET", "/vmc")
        page = conn.getresponse().read().decode()
        assert "VMC 송신" in page and "/vmc/start" in page
        status, body = request(server.port, "POST", "/vmc/start", {"host": "8.8.8.8", "port": target})
        assert status == 400 and "내부 주소만" in body["error"]
        status, body = request(server.port, "POST", "/vmc/start", {"host": "127.0.0.1", "port": target, "mirror": True})
        assert status == 200 and body["running"] and body["mirror"] and settings.load_data("vmc.json")["enabled"] is True
        server.tracking.publish({"found": True, "yaw": 0.1})
        assert vmc.parse_osc(sock.recvfrom(65536)[0])[0][0] == "/VMC/Ext/OK"
    finally:
        server.stop()
    again = OverlayServer([], port=0).start()  # 저장한 설정으로 자동 시작
    try:
        assert request(again.port, "GET", "/vmc/status")[1]["running"] is True
        from debutkit.cli import main

        assert main(["vmc", "--port", str(again.port), "status"]) == 0 and "VMC 송신 중" in capsys.readouterr().out
        assert main(["vmc", "--port", str(again.port), "stop"]) == 0 and "꺼짐" in capsys.readouterr().out
        assert settings.load_data("vmc.json")["enabled"] is False
    finally:
        again.stop()
        sock.close()


# --------------------------------------------------------------------------- 자세 보내기(캐릭터 그림 만들기의 포즈 그림)


def rotate(q, v):
    """사원수 q(x, y, z, w)로 벡터 v 회전(좌표계와 관계없이 같은 식)."""
    x, y, z, w = q
    u = (x, y, z)
    cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    cross2 = (u[1] * cross[2] - u[2] * cross[1], u[2] * cross[0] - u[0] * cross[2], u[0] * cross[1] - u[1] * cross[0])
    return tuple(v[i] + 2 * (w * cross[i] + cross2[i]) for i in range(3))


def arm_up(angle):  # three.js 왼팔(+X)을 z축으로 angle만큼 올린 회전과 위치
    return [0.0, 0.0, math.sin(angle / 2), math.cos(angle / 2), 0.09, 0.0, 0.0]


POSE_BODY = {"bones": {"hips": [0, 0, 0, 1, 0, 1.0, 0.01], "head": [0.1, 0, 0, 0.995, 0, 0.08, 0.01], "leftUpperArm": arm_up(1.1),
                       "leftThumbMetacarpal": [0, 0, 0, 1, 0.02, 0, 0.02]}, "expression": "happy"}


def test_unity_bone_names_follow_humanbodybones():
    names = vmc.UNITY_BONES
    assert len(names) == 52 and names["upperChest"] == "UpperChest" and names["leftToes"] == "LeftToes"
    # VRM 1.0 엄지는 Metacarpal부터라 Unity(Proximal부터)와 한 칸씩 밀림
    assert names["leftThumbMetacarpal"] == "LeftThumbProximal" and names["leftThumbProximal"] == "LeftThumbIntermediate"
    assert names["rightThumbDistal"] == "RightThumbDistal" and names["rightLittleIntermediate"] == "RightLittleIntermediate"


def test_unity_bone_mirrors_x_axis():
    raised = vmc.unity_bone(arm_up(1.1))
    assert raised[:3] == (-0.09, 0.0, 0.0)  # Unity에서 캐릭터 왼쪽은 -X
    direction = rotate(raised[3:], (-1.0, 0.0, 0.0))
    assert direction[1] > 0.8 and direction[0] < 0  # 올린 왼팔은 Unity에서도 위로
    turned = vmc.unity_bone([0.0, math.sin(0.25), 0.0, math.cos(0.25), 0, 0, 0])
    assert turned[4] == -math.sin(0.25)  # y축 회전은 부호 반대(얼굴 추적 머리 회전과 같은 규칙)
    nod = vmc.unity_bone([math.sin(0.1), 0.0, 0.0, math.cos(0.1), 0, 0, 0])
    assert nod[3] == math.sin(0.1) and rotate(nod[3:], (0, 0, 1))[1] == pytest.approx(rotate((math.sin(0.1), 0, 0, math.cos(0.1)), (0, 0, 1))[1])


@pytest.mark.parametrize("body, message", [
    ({}, "보낼 자세가 없음"),
    ({"bones": {}}, "보낼 자세가 없음"),
    ({"bones": {"tail": [0, 0, 0, 1, 0, 0, 0]}}, "올바르지 않음"),
    ({"bones": {"hips": [0, 0, 0, 1]}}, "올바르지 않음"),
    ({"bones": {"hips": [0, 0, 2, 1, 0, 0, 0]}}, "올바르지 않음"),
    ({"bones": {"hips": [0, 0, 0, 1, 0, 50, 0]}}, "올바르지 않음"),
    ({"bones": {"hips": [0, 0, 0, True, 0, 0, 0]}}, "올바르지 않음"),
    ({"bones": {"hips": [0, 0, 0, 1, 0, 1, 0]}, "expression": "wink"}, "표정 이름"),
])
def test_pose_values_are_checked(body, message):
    with pytest.raises(vmc.VmcError, match=message):
        vmc.check_pose(body)


def test_pose_packets_stay_small_and_leave_face_to_tracking():
    bones, expression = vmc.check_pose({"bones": {bone: [0, 0, 0, 1, 0, 0.1, 0] for bone in vmc.UNITY_BONES}, "expression": "aa"})
    packets = vmc.pose_packets(bones, expression, clock=3.0)
    assert len(packets) > 1 and all(len(packet) <= vmc.PACKET for packet in packets)
    parsed = [item for packet in packets for item in vmc.parse_osc(packet)]
    assert parsed[0] == ("/VMC/Ext/OK", [1]) and ("/VMC/Ext/T", [3.0]) in parsed and parsed[-1] == ("/VMC/Ext/Blend/Apply", [])
    assert ("/VMC/Ext/Root/Pos", ["root", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]) in parsed
    assert sum(address == "/VMC/Ext/Bone/Pos" for address, _ in parsed) == 52
    blends = {args[0]: args[1] for address, args in parsed if address == "/VMC/Ext/Blend/Val"}
    assert blends == {"Joy": 0.0, "Angry": 0.0, "Sorrow": 0.0, "Fun": 0.0, "A": 1.0, "Blink": 0.0}  # 다른 표정은 0으로
    face = [item for packet in vmc.pose_packets(bones, expression, skip_face=True) for item in vmc.parse_osc(packet)]
    names = [args[0] for address, args in face if address == "/VMC/Ext/Bone/Pos"]
    assert "Head" not in names and "Neck" in names and not any(address.startswith("/VMC/Ext/Blend") for address, _ in face)
    plain = [address for packet in vmc.pose_packets(bones, None) for address, _ in vmc.parse_osc(packet)]
    assert "/VMC/Ext/Blend/Val" not in plain  # 표정 끄기


class FakeFace:
    running = False


def test_pose_sender_repeats_until_the_page_goes_quiet(monkeypatch):
    sock = receiver()
    face = FakeFace()
    sender = vmc.PoseSender(face)
    try:
        sender.update("127.0.0.1", sock.getsockname()[1], POSE_BODY)
        parsed = [item for _ in range(2) for item in vmc.parse_osc(sock.recvfrom(65536)[0])]
        bones = {args[0]: args[1:] for address, args in parsed if address == "/VMC/Ext/Bone/Pos"}
        assert bones["LeftUpperArm"][:3] == [pytest.approx(-0.09), 0.0, 0.0] and "LeftThumbProximal" in bones
        assert sender.status()["running"] and sender.status()["bones"] == 4 and sender.status()["expression"] == "happy"
        face.running = True  # 얼굴 추적 송신이 켜지면 머리와 표정은 빠짐
        deadline = time.time() + 2
        while time.time() < deadline:
            names = [args[0] for address, args in vmc.parse_osc(sock.recvfrom(65536)[0]) if address == "/VMC/Ext/Bone/Pos"]
            if names and "Head" not in names:
                break
        assert "Head" not in names and sender.status()["face"] is True
        monkeypatch.setattr(vmc, "POSE_HOLD", 0.2)
        sender.update("127.0.0.1", sock.getsockname()[1], POSE_BODY)  # 새 자세가 없으면 잠시 뒤 멈춤
        deadline = time.time() + 3
        while sender.running and time.time() < deadline:
            time.sleep(0.02)
        assert not sender.running and "새 자세가 없어" in sender.status()["error"]
        sender.update("127.0.0.1", sock.getsockname()[1], POSE_BODY)  # 다시 보내면 다시 시작
        assert sender.running and sender.status()["error"] == ""
    finally:
        sender.stop()
        sock.close()
    assert not sender.running


def test_pose_routes_over_http():
    sock = receiver()
    server = OverlayServer([], port=0).start()
    try:
        big = {"bones": {bone: [0.12345, -0.12345, 0.12345, 0.97531, 0.12345, 1.2345, -0.01234] for bone in vmc.UNITY_BONES}, "expression": None}
        status, body = request(server.port, "POST", "/vmc/pose", {"host": "127.0.0.1", "port": sock.getsockname()[1], **big})
        assert status == 200 and body["running"] and body["bones"] == 52  # 뼈 52개(약 6KB)도 본문 제한 안
        assert any(address == "/VMC/Ext/Bone/Pos" for address, _ in vmc.parse_osc(sock.recvfrom(65536)[0]))
        status, body = request(server.port, "GET", "/vmc/status")
        assert body["pose"]["running"] and body["pose"]["port"] == sock.getsockname()[1] and body["running"] is False
        status, body = request(server.port, "POST", "/vmc/pose", {"host": "8.8.8.8", **big})
        assert status == 400 and "내부 주소만" in body["error"]
        status, body = request(server.port, "POST", "/vmc/pose/stop", {})
        assert status == 200 and body["running"] is False
    finally:
        server.stop()
        sock.close()
