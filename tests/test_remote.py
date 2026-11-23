"""휴대폰 조작 화면(overlay/remote.py): 기기 등록과 승인, 요청 서명, 재사용과 실패 제한, 별도 창구, 서버 관리 경로, 명령줄."""

from __future__ import annotations

import http.client
import json
import secrets
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

from debutkit import camera, settings
from debutkit.cli import main
from debutkit.draw import DrawState
from debutkit.motion import MotionState
from debutkit.overlay import remote as remotes
from debutkit.overlay.server import OverlayServer
from debutkit.raffle import Raffle

STATIC = Path(__file__).parents[1] / "src" / "debutkit" / "overlay" / "static"


def free_port() -> int:
    """TCP와 UDP 모두 열 수 있는 번호(Windows는 UDP만 예약된 번호대가 있음: Hyper-V, WSL)."""
    for _ in range(50):
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind(("127.0.0.1", 0))
        port = udp.getsockname()[1]
        tcp = socket.socket()
        try:
            tcp.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
        finally:
            tcp.close()
            udp.close()
    raise RuntimeError("free port not found")


@pytest.fixture(autouse=True)
def loopback(monkeypatch):
    """시험: 127.0.0.1을 이 PC의 내부 네트워크 주소로 간주."""
    monkeypatch.setattr(camera, "lan_addresses", lambda extra=(): ["127.0.0.1"])


def headers_for(device, method, path, body=b"", *, stamp=None, nonce=None, secret=None):
    stamp = stamp or str(int(time.time() * 1000))
    nonce = nonce or secrets.token_hex(8)
    return {"X-Debutkit-Device": device.id, "X-Debutkit-Time": stamp, "X-Debutkit-Nonce": nonce,
            "X-Debutkit-Sign": remotes.sign(secret or device.secret, method, path, stamp, nonce, body)}


def test_sign_and_confirm_code_are_stable():
    signature = remotes.sign("s" * 40, "post", "/remote/api/hello", "1700000000000", "abcdef0123456789", b'{"a":1}')
    assert signature == remotes.sign("s" * 40, "POST", "/remote/api/hello", "1700000000000", "abcdef0123456789", b'{"a":1}')
    assert signature != remotes.sign("s" * 40, "POST", "/remote/api/hello", "1700000000000", "abcdef0123456789", b'{"a":2}')
    code = remotes.confirm_code("s" * 40)
    assert len(code) == 4 and code.isdigit() and code == remotes.confirm_code("s" * 40) and code != remotes.confirm_code("t" * 40)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
def test_browser_signing_matches_python(tmp_path):
    """휴대폰 화면의 SHA-256, HMAC(remote-sign.js)이 서버와 같은 결과(패딩 경계, 긴 키, 한국어)."""
    script = tmp_path / "check.js"
    script.write_text("""
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8").replace(/^export /gm, "");
const api = new Function(src + "; return { sha256, hex, hmacSha256, sign, confirmCode };")();
const enc = new TextEncoder();
const out = {};
for (const text of ["", "abc", "a".repeat(55), "a".repeat(56), "a".repeat(64), "a".repeat(1000), "한글 시험"]) out[text] = api.hex(api.sha256(enc.encode(text)));
out.hmac = api.hex(api.hmacSha256("k".repeat(100), "message"));
out.sign = api.sign("secret-value-0123456789-abcdefghijkl", "POST", "/remote/api/raffle/draw", "1700000000000", "0123456789abcdef", '{"mode":"pick","count":2}');
out.code = api.confirmCode("secret-value-0123456789-abcdefghijkl");
console.log(JSON.stringify(out));
""", encoding="utf-8")
    result = json.loads(subprocess.run(["node", str(script), str(STATIC / "remote-sign.js")], capture_output=True, text=True, encoding="utf-8",
                                       check=True).stdout)
    import hashlib
    import hmac

    for text in ["", "abc", "a" * 55, "a" * 56, "a" * 64, "a" * 1000, "한글 시험"]:
        assert result[text] == hashlib.sha256(text.encode()).hexdigest()
    assert result["hmac"] == hmac.new(b"k" * 100, b"message", hashlib.sha256).hexdigest()
    assert result["sign"] == remotes.sign("secret-value-0123456789-abcdefghijkl", "POST", "/remote/api/raffle/draw", "1700000000000",
                                          "0123456789abcdef", b'{"mode":"pick","count":2}')
    assert result["code"] == remotes.confirm_code("secret-value-0123456789-abcdefghijkl")


class Headers(dict):
    def get(self, key, default=None):
        return super().get(key, default)


def test_store_pairing_approval_and_persistence(monkeypatch):
    store = remotes.DeviceStore()
    first = store.pair()
    assert not first.approved and not first.claimed and len(first.secret) >= 40
    second = store.pair()  # 쓰지 않은 QR은 새 QR로 교체
    assert store.get(first.id) is None and store.get(second.id) is second
    with pytest.raises(remotes.RemoteError, match="QR을 먼저"):
        store.approve(second.id)
    assert store.claim(second, "iPhone") is True and store.claim(second, "iPhone") is False
    store.approve(second.id)
    saved = json.loads(remotes.devices_path().read_text(encoding="utf-8"))
    assert [item["id"] for item in saved["devices"]] == [second.id] and saved["devices"][0]["secret"] == second.secret
    assert "remote" not in json.dumps(settings.load())  # 비밀값은 저장 설정 파일에 넣지 않음
    again = remotes.DeviceStore()
    assert again.get(second.id).approved and again.get(second.id).name == "iPhone"
    # 5분 지난 QR은 사라짐
    pending = again.pair()
    real = time.time
    monkeypatch.setattr(remotes.time, "time", lambda: real() + remotes.PAIR_SECONDS + 1)
    assert again.get(pending.id) is None and again.get(second.id) is not None
    monkeypatch.setattr(remotes.time, "time", real)
    for _ in range(remotes.MAX_DEVICES - 1):
        device = again.pair()
        again.claim(device, "")
    with pytest.raises(remotes.RemoteError, match="최대"):
        again.pair()
    assert again.remove(second.id) and not again.remove(second.id)
    assert second.id not in remotes.devices_path().read_text(encoding="utf-8")
    remotes.devices_path().write_text("[broken", encoding="utf-8")
    assert remotes.DeviceStore().all() == []


def test_verify_rejects_forgery_skew_replay_and_blocks():
    store = remotes.DeviceStore()
    device = store.pair()
    path = "/remote/api/status"
    good = headers_for(device, "GET", path)
    found, status, _ = store.verify("GET", path, Headers(good), b"", "10.0.0.7")
    assert found is device and status == 0
    found, status, message = store.verify("GET", path, Headers(good), b"", "10.0.0.7")
    assert found is None and status == 401 and "다시 보냄" in message  # 같은 일회용 값
    old = headers_for(device, "GET", path, stamp=str(int((time.time() - 600) * 1000)))
    found, status, message = store.verify("GET", path, Headers(old), b"", "10.0.0.7")
    assert found is None and "시각" in message
    body_changed = headers_for(device, "POST", "/remote/api/raffle/draw", b'{"count":1}')
    assert store.verify("POST", "/remote/api/raffle/draw", Headers(body_changed), b'{"count":30}', "10.0.0.7")[1] == 401
    for _ in range(remotes.FAIL_LIMIT):
        store.verify("GET", path, Headers(headers_for(device, "GET", path, secret="x" * 43)), b"", "10.0.0.9")
    assert store.blocked("10.0.0.9") and not store.blocked("10.0.0.7")
    found, status, _ = store.verify("GET", path, Headers(headers_for(device, "GET", path)), b"", "10.0.0.9")
    assert found is None and status == 429


def call(port, method, path, device=None, body=None, *, host=None, origin=None, raw_headers=None):
    payload = json.dumps(body).encode() if body is not None else b""
    headers = {"Host": host or f"127.0.0.1:{port}"}
    if origin:
        headers["Origin"] = origin
    if payload:
        headers["Content-Type"] = "application/json"
    if device is not None:
        headers.update(headers_for(device, method, path, payload))
    headers.update(raw_headers or {})
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, body=payload or None, headers=headers)
    response = conn.getresponse()
    data = response.read()
    answer = (response.status, data, dict(response.getheaders()))
    conn.close()
    return answer


@pytest.fixture
def control():
    raffle = Raffle()
    for name in ("하늘", "바다", "구름"):
        raffle.add(name, "chzzk", "manual")
    notes: list[str] = []
    made = remotes.RemoteControl(raffle, MotionState(), DrawState(), notify=notes.append)
    made.notes = notes
    yield made
    made.stop(save=False)


def test_listener_flow_pair_approve_control_and_revoke(control):
    port = free_port()
    status = control.start("127.0.0.1", port)
    assert status["running"] and status["url"] == f"http://127.0.0.1:{port}/remote"
    assert settings.load()["remote_enabled"] is True and settings.load()["remote_port"] == port
    code, page, headers = call(port, "GET", "/remote")
    assert code == 200 and "휴대폰 조작".encode() in page and "default-src 'none'" in headers["Content-Security-Policy"]
    assert headers["Referrer-Policy"] == "no-referrer"
    assert call(port, "GET", "/remote-sign.js")[0] == 200 and call(port, "GET", "/draw/control")[0] == 404
    assert call(port, "GET", "/remote", host="evil.example:80")[0] == 403  # DNS 리바인딩
    pairing = control.pair()
    assert pairing["url"].startswith(f"http://127.0.0.1:{port}/remote#d={pairing['id']}&k=")
    device = control.devices.get(pairing["id"])
    assert call(port, "POST", "/remote/api/hello", body={})[0] == 401  # 서명 없음
    code, body, _ = call(port, "POST", "/remote/api/hello", device, {"name": "iPhone"})
    answer = json.loads(body)
    assert code == 200 and answer == {"approved": False, "code": remotes.confirm_code(device.secret), "name": "iPhone"}
    assert any("승인 대기" in note for note in control.notes)
    code, body, _ = call(port, "GET", "/remote/api/status", device)
    assert code == 403 and json.loads(body)["approved"] is False
    assert call(port, "POST", "/remote/api/hello", device, {}, origin="https://evil.example")[0] == 403
    control.approve(device.id)
    code, body, _ = call(port, "GET", "/remote/api/status", device)
    snapshot = json.loads(body)
    assert code == 200 and snapshot["raffle"]["count"] == 3 and snapshot["motions"] == [] and snapshot["draws"] == []
    code, body, _ = call(port, "POST", "/remote/api/raffle/start", device, {})
    assert code == 200 and json.loads(body)["raffle"]["open"] is True and json.loads(body)["raffle"]["count"] == 0
    control.raffle.add("별빛", "soop", "chat")
    control.raffle.add("노을", "chzzk", "chat")
    code, body, _ = call(port, "POST", "/remote/api/raffle/draw", device, {"mode": "pick", "count": 1})
    result = json.loads(body)["raffle"]
    assert code == 200 and result["open"] is False and len(result["last_result"]["winners"]) == 1
    code, body, _ = call(port, "POST", "/remote/api/raffle/draw", device, {"mode": "pick", "count": 99})
    assert code == 400 and "당첨 인원" in json.loads(body)["error"]
    code, body, _ = call(port, "POST", "/remote/api/motion", device, {"id": "없음"})
    assert code == 400 and "동작" in json.loads(body)["error"]
    assert call(port, "POST", "/remote/api/motion", device, {"stop": True})[0] == 200 and control.motion.current["stop"] is True
    assert call(port, "POST", "/remote/api/unknown", device, {})[0] == 400
    control.remove(device.id)
    assert call(port, "GET", "/remote/api/status", device)[0] == 401  # 삭제 즉시 차단
    control.stop()
    assert not control.running and settings.load()["remote_enabled"] is False


def test_start_checks_address_port_and_busy(control):
    with pytest.raises(remotes.RemoteError, match="내부 네트워크 주소"):
        control.start("8.8.8.8", 8792)
    with pytest.raises(remotes.RemoteError, match="포트"):
        control.start("127.0.0.1", 80)
    with pytest.raises(remotes.RemoteError, match="먼저 켜기"):
        control.pair()
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    try:
        with pytest.raises(remotes.RemoteError, match="열기 실패"):
            control.start("127.0.0.1", blocker.getsockname()[1])
    finally:
        blocker.close()


def local(srv, method, path, body=None, origin=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    headers = {"Content-Type": "application/json", **({"Origin": origin} if origin else {})}
    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=headers)
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, data


def test_overlay_admin_routes_and_saved_start():
    srv = OverlayServer([], port=0).start()
    try:
        status, body = local(srv, "GET", "/remote/admin")
        assert status == 200 and json.loads(body)["running"] is False and json.loads(body)["addresses"] == ["127.0.0.1"]
        assert local(srv, "POST", "/remote/admin/pair", {})[0] == 400
        assert local(srv, "POST", "/remote/admin/start", {"address": "8.8.8.8"})[0] == 400
        port = free_port()
        status, body = local(srv, "POST", "/remote/admin/start", {"address": "127.0.0.1", "port": port})
        assert status == 200 and json.loads(body)["url"] == f"http://127.0.0.1:{port}/remote"
        status, body = local(srv, "POST", "/remote/admin/pair", {})
        pairing = json.loads(body)
        assert status == 200 and "#d=" in pairing["url"] and len(pairing["code"]) == 4
        status, body = local(srv, "GET", f"/remote/admin/qr.svg?id={pairing['id']}")
        assert status == 200 and body.startswith(b"<svg")
        assert local(srv, "GET", "/remote/admin/qr.svg?id=nope")[0] == 404
        assert local(srv, "POST", "/remote/admin/approve", {"id": pairing["id"]})[0] == 400  # 휴대폰이 아직 열지 않음
        assert local(srv, "POST", "/remote/admin/pair", {}, origin="https://evil.example")[0] == 403
        status, body = local(srv, "POST", "/remote/admin/remove", {"id": pairing["id"]})
        assert status == 200 and json.loads(body)["devices"] == []
    finally:
        srv.stop()
    assert settings.load()["remote_enabled"] is True  # 오버레이를 멈춰도 다음 실행에 켬
    srv = OverlayServer([], port=0).start()
    try:
        assert srv.remote.running and srv.remote.port == port
        assert any("휴대폰 조작 화면" in event.text for event in srv.hub.history)
        status, page = local(srv, "GET", "/phone")
        assert "휴대폰 조작 화면" in page.decode() and "/remote/admin/qr.svg" in page.decode()
    finally:
        srv.stop()
    settings.save({**settings.load(), "remote_address": "10.9.9.9"})  # 공유기가 바뀌어 주소가 없어진 경우
    srv = OverlayServer([], port=0).start()
    try:
        assert not srv.remote.running and any("내부 네트워크 주소" in event.text for event in srv.hub.history)
    finally:
        srv.stop()


def test_cli_remote(capsys):
    srv = OverlayServer([], port=0).start()
    try:
        port = free_port()
        assert main(["remote", "--port", str(srv.port), "status"]) == 0 and "꺼짐" in capsys.readouterr().out
        assert main(["remote", "--port", str(srv.port), "start", "--address", "127.0.0.1", "--listen-port", str(port)]) == 0
        assert f"http://127.0.0.1:{port}/remote" in capsys.readouterr().out
        assert main(["remote", "--port", str(srv.port), "pair"]) == 0
        out = capsys.readouterr().out
        assert "#d=" in out and "debutkit remote approve" in out
        device_id = out.split("debutkit remote approve ")[1].split()[0]
        assert main(["remote", "--port", str(srv.port), "approve", device_id]) == 1 and "QR을 먼저" in capsys.readouterr().err
        assert main(["remote", "--port", str(srv.port), "remove", device_id]) == 0
        assert main(["remote", "--port", str(srv.port), "stop"]) == 0 and "꺼짐" in capsys.readouterr().out
    finally:
        srv.stop()


def app_packet(device, stamp=None, *, found=True, rotation=(0.1, -0.2, 0.05), shapes=None, secret=None, raw=None):
    """debutkit 휴대폰 앱(mobile/android Packets)과 같은 형식의 추적 패킷."""
    from debutkit.overlay.tracking import ARKIT_NAMES

    stamp = stamp if stamp is not None else int(time.time() * 1000)
    if raw is None:
        values = shapes if shapes is not None else [0.0] * len(ARKIT_NAMES)
        raw = {"v": 1, "d": device.id, "t": stamp, "f": found}
        if found:
            raw.update(r=list(rotation), b=values)
    payload = json.dumps(raw, separators=(",", ":")).encode()
    return payload + b"\n" + remotes.sign_packet(secret or device.secret, payload).encode()


def test_app_packets_are_verified(control):
    from debutkit.overlay.tracking import ARKIT_NAMES

    device = control.devices.pair()
    control.devices.claim(device, "Pixel")
    shapes = [0.0] * len(ARKIT_NAMES)
    shapes[ARKIT_NAMES.index("eyeBlinkLeft")] = 0.8
    shapes[ARKIT_NAMES.index("jawOpen")] = 0.5
    assert control.accept(app_packet(device, shapes=shapes)) is None  # 승인 전
    control.devices.approve(device.id)
    stamp = int(time.time() * 1000)
    values = control.accept(app_packet(device, stamp, shapes=shapes))
    # 거울처럼(기본): 좌우 회전과 기울기 반대, 왼눈 값이 오른눈으로
    assert values["found"] is True and values["source"] == "phone" and values["yaw"] == -0.1 and values["pitch"] == -0.2 and values["roll"] == -0.05
    assert values["blinkRight"] == 0.8 and values["mouth"] == 0.5 and len(values["arkit"]) == 52
    assert control.accept(app_packet(device, stamp, shapes=shapes)) is None  # 같은 시각(재전송)
    assert control.accept(app_packet(device, stamp - 5)) is None  # 이전 시각
    assert control.accept(app_packet(device, stamp + 10, secret="x" * 43)) is None  # 서명 불일치
    assert control.accept(app_packet(device, int((time.time() - 600) * 1000))) is None  # 시각 차이
    assert control.accept(app_packet(device, stamp + 20, rotation=(0.1, 0.2))) is None  # 형식
    assert control.accept(app_packet(device, stamp + 30, raw={"v": 1, "d": device.id, "t": stamp + 30, "f": True, "r": [0, 0, "NaN"], "b": shapes})) is None
    assert control.accept(app_packet(device, stamp + 40, found=False)) == {"found": False, "source": "phone"}
    assert control.accept(b"garbage") is None and control.accept(b"{}\nabc") is None


class FakeOptions:
    mirror, flip_pitch, center = False, True, (0.1, 0.0, 0.0)


def test_app_tracking_over_udp_and_webcam_yields(control):
    port = free_port()
    control.phone = FakeOptions()  # 휴대폰 얼굴 추적 설정(거울 끔, 위아래 반전, 정면 맞추기)을 따른다
    control.start("127.0.0.1", port)
    device = control.devices.pair()
    control.devices.claim(device, "Pixel")
    control.devices.approve(device.id)
    subscriber, _ = control.tracking.subscribe()
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for index in range(5):
            sender.sendto(app_packet(device, int(time.time() * 1000) + index), ("127.0.0.1", port))
            time.sleep(0.04)
        values = subscriber.get(timeout=3)
        assert values["found"] is True and values["yaw"] == 0.0 and values["pitch"] == 0.2 and values["roll"] == 0.05
        deadline = time.monotonic() + 3
        while not control.receiving() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert control.receiving() and control.status()["receiving"] is True
        assert control.status()["devices"][0]["tracking"] >= 3
        sender.sendto(b"not a packet", ("127.0.0.1", port))
        deadline = time.monotonic() + 2
        while control.dropped == 0 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert control.dropped >= 1
    finally:
        sender.close()
    control.stop(save=False)
    assert control.tracking.current["found"] is False and not control.receiving()


def test_overlay_uses_app_tracking_before_webcam():
    srv = OverlayServer([], port=0).start()
    try:
        port = free_port()
        srv.remote.start("127.0.0.1", port)
        device = srv.remote.devices.pair()
        srv.remote.devices.claim(device, "iPhone")
        srv.remote.devices.approve(device.id)
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sender.sendto(app_packet(device), ("127.0.0.1", port))
        sender.close()
        deadline = time.monotonic() + 3
        while not srv.remote.receiving() and time.monotonic() < deadline:
            time.sleep(0.05)
        status, body = local(srv, "POST", "/tracking", {"found": True, "yaw": 0.9})
        assert status == 200 and body == b"phone"  # 앱 값을 받는 중에는 웹캠 값을 쓰지 않음
        assert srv.tracking.current["source"] == "phone" and srv.phone is srv.remote.phone
    finally:
        srv.stop()
