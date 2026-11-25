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
