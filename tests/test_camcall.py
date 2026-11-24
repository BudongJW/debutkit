"""휴대폰 앱 카메라 영상(WebRTC) 연결 중계(overlay/camcall.py): SDP 확인, 감춘 주소 바꾸기, 처음 응답만, 서버와 앱 요청, OBS 소스."""

from __future__ import annotations

import http.client
import json
import secrets
import time

import pytest
from ports import free_port

from debutkit import camera
from debutkit.draw import DrawState
from debutkit.motion import MotionState
from debutkit.overlay import camcall
from debutkit.overlay import remote as remotes
from debutkit.overlay.server import OverlayServer
from debutkit.raffle import Raffle

OFFER = "v=0\r\no=- 1 2 IN IP4 127.0.0.1\r\ns=-\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\na=candidate:1 1 udp 2122260223 10.0.2.15 41000 typ host\r\n"
ANSWER = ("v=0\r\no=- 3 2 IN IP4 127.0.0.1\r\ns=-\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\n"
          "a=candidate:7 1 udp 2122260223 2f3b9c1e-1111-2222-3333-444455556666.local 53285 typ host generation 0\r\n"
          "a=candidate:8 1 tcp 1518280447 2f3b9c1e-1111-2222-3333-444455556666.local 9 typ host tcptype active\r\n"
          "a=candidate:9 1 udp 2122260223 192.168.0.9 53300 typ host\r\na=end-of-candidates\r\n")


def test_sdp_check_and_candidate_rewrite():
    assert camcall.check_sdp(OFFER) == OFFER
    for bad in ("", None, "hello", "v=0\r\nm=audio 9", "v=0 m=video" + "x" * camcall.MAX_SDP):
        with pytest.raises(camcall.CallError):
            camcall.check_sdp(bad)
    rewritten = camcall.rewrite_candidates(ANSWER, ["192.168.0.5", "", "10.0.0.7", "192.168.0.5"])
    lines = rewritten.split("\r\n")
    assert "a=candidate:7 1 udp 2122260223 192.168.0.5 53285 typ host generation 0" in lines
    assert "a=candidate:7 1 udp 2122260223 10.0.0.7 53285 typ host generation 0" in lines
    assert "a=candidate:8 1 tcp 1518280447 192.168.0.5 9 typ host tcptype active" in lines
    assert "a=candidate:9 1 udp 2122260223 192.168.0.9 53300 typ host" in lines  # 감추지 않은 후보는 그대로
    assert ".local" not in rewritten and rewritten.endswith("a=end-of-candidates\r\n")
    assert camcall.rewrite_candidates(ANSWER, []) == ANSWER  # 바꿀 주소가 없으면 그대로
    assert "\n" in camcall.rewrite_candidates(ANSWER.replace("\r\n", "\n"), ["10.1.1.1"]) and "\r" not in camcall.rewrite_candidates(
        ANSWER.replace("\r\n", "\n"), ["10.1.1.1"])


def test_call_flow_first_answer_wins_and_ends(monkeypatch):
    call = camcall.CameraCall()
    subscriber, current = call.subscribe()
    assert current["type"] == "idle" and call.status()["state"] == "idle"
    call_id = call.offer("dev1", "Pixel 9", OFFER)
    event = subscriber.get(timeout=1)
    assert event["type"] == "offer" and event["id"] == call_id and event["sdp"] == OFFER and event["name"] == "Pixel 9"
    assert call.poll(call_id, "dev1") == {"state": "waiting"} and call.status()["state"] == "connecting"
    assert call.poll(call_id, "other") == {"state": "ended"}  # 다른 기기는 볼 수 없음
    assert call.answer(call_id, ANSWER, ["192.168.0.5"]) is True
    assert call.answer(call_id, ANSWER, ["192.168.0.5"]) is False  # 두 번째 수신 화면
    assert call.answer("other", ANSWER, ["192.168.0.5"]) is False
    assert subscriber.get(timeout=1)["type"] == "answered" and call.status() == {"state": "connected", "name": "Pixel 9", "since": call.current["time"]}
    answered = call.poll(call_id, "dev1")
    assert answered["state"] == "answered" and "192.168.0.5 53285" in answered["sdp"]
    second = call.offer("dev1", "Pixel 9", OFFER)  # 다시 연결(수신 화면을 다시 불러온 경우): 이전 통화 끝
    assert call.poll(call_id, "dev1") == {"state": "ended"} and call.poll(second, "dev1") == {"state": "waiting"}
    assert call.stop(second, "other") is False and call.stop(second, "dev1") is True and call.status()["state"] == "idle"
    assert call.stop(second) is False
    monkeypatch.setattr(camcall, "OFFER_SECONDS", 0.05)
    third = call.offer("dev1", "Pixel 9", OFFER)
    time.sleep(0.1)
    ended = call.poll(third, "dev1")
    assert ended["state"] == "ended" and "수신 화면 응답 없음" in ended["reason"] and call.status()["state"] == "idle"
    with pytest.raises(camcall.CallError):
        call.offer("dev1", "x", "not sdp")
    with pytest.raises(camcall.CallError):
        call.answer(third, "not sdp", [])
    call.unsubscribe(subscriber)


def signed(port, device, path, body):
    payload = json.dumps(body).encode()
    stamp, nonce = str(int(time.time() * 1000)), secrets.token_hex(8)
    headers = {"Host": f"127.0.0.1:{port}", "Content-Type": "application/json", "X-Debutkit-Device": device.id, "X-Debutkit-Time": stamp,
               "X-Debutkit-Nonce": nonce, "X-Debutkit-Sign": remotes.sign(device.secret, "POST", path, stamp, nonce, payload)}
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", path, body=payload, headers=headers)
    response = conn.getresponse()
    data = json.loads(response.read() or b"{}")
    conn.close()
    return response.status, data


def local(srv, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, data


@pytest.fixture
def loopback(monkeypatch):
    monkeypatch.setattr(camera, "lan_addresses", lambda extra=(): ["127.0.0.1", "192.168.0.5"])


def test_app_offer_through_remote_and_receiver_answer(loopback):
    srv = OverlayServer([], port=0).start()
    try:
        port = free_port()
        srv.remote.start("127.0.0.1", port)
        device = srv.remote.devices.pair()
        srv.remote.devices.claim(device, "Pixel 9")
        assert signed(port, device, "/remote/api/camera/offer", {"sdp": OFFER})[0] == 403  # 승인 전
        srv.remote.devices.approve(device.id)
        status, answer = signed(port, device, "/remote/api/camera/offer", {"sdp": "nope"})
        assert status == 400 and "SDP" in answer["error"]
        status, offered = signed(port, device, "/remote/api/camera/offer", {"sdp": OFFER})
        call_id = offered["id"]
        assert status == 200 and srv.camera_call.current["type"] == "offer"
        status, body = local(srv, "GET", "/camera/call")
        assert json.loads(body)["state"] == "connecting"
        assert signed(port, device, "/remote/api/camera/answer", {"id": call_id})[1] == {"state": "waiting"}
        status, body = local(srv, "POST", "/camera/answer", {"id": call_id, "sdp": ANSWER})
        assert status == 200 and json.loads(body) == {"accepted": True}
        status, body = local(srv, "POST", "/camera/answer", {"id": call_id, "sdp": ANSWER})
        assert status == 409 and "다른 화면" in json.loads(body)["error"]
        status, answer = signed(port, device, "/remote/api/camera/answer", {"id": call_id})
        # 감춘 주소를 조작 화면 주소(127.0.0.1)와 내부 주소 순서로
        assert answer["state"] == "answered" and answer["sdp"].index("127.0.0.1 53285") < answer["sdp"].index("192.168.0.5 53285")
        assert json.loads(local(srv, "GET", "/camera/call")[1])["state"] == "connected"
        assert signed(port, device, "/remote/api/camera/stop", {"id": call_id})[1] == {"stopped": True}
        assert json.loads(local(srv, "GET", "/camera/call")[1])["state"] == "idle"
        # 수신 화면이 오래 끊김을 알림, 기기 삭제 시 통화 끝
        call_id = signed(port, device, "/remote/api/camera/offer", {"sdp": OFFER})[1]["id"]
        assert json.loads(local(srv, "POST", "/camera/ended", {"id": call_id})[1]) == {"stopped": True}
        call_id = signed(port, device, "/remote/api/camera/offer", {"sdp": OFFER})[1]["id"]
        srv.remote.remove(device.id)
        assert srv.camera_call.status()["state"] == "idle"
        status, page = local(srv, "GET", "/camera/view")
        assert status == 200 and b"/camera-view.js" in page and local(srv, "GET", "/camera-view.js")[0] == 200
        assert local(srv, "POST", "/camera/answer", {"id": "x", "sdp": "bad"})[0] == 400
    finally:
        srv.stop()


def test_live_feed_carries_camera_offers():
    srv = OverlayServer([], port=0).start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
        conn.request("GET", "/live?feeds=camera")
        response = conn.getresponse()
        first = response.fp.readline() + response.fp.readline()
        assert b"event: camera" in first and b'"idle"' in first
        response.fp.readline()
        srv.camera_call.offer("dev", "Pixel", OFFER)
        lines = response.fp.readline() + response.fp.readline()
        assert b"event: camera" in lines and b'"offer"' in lines and b"m=video" in lines
        conn.close()
    finally:
        srv.stop()


class FakeObs:
    def __init__(self):
        self.calls = []
        self.inputs = set()
        self.items = {"본방송": ["[DK] 채팅"]}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def request(self, kind, data=None):
        data = data or {}
        self.calls.append((kind, data))
        if kind == "GetInputKindList":
            return {"inputKinds": ["browser_source", "ffmpeg_source"]}
        if kind == "GetCurrentProgramScene":
            return {"sceneName": "본방송"}
        if kind == "GetSceneList":
            return {"scenes": [{"sceneName": "본방송"}]}
        if kind == "GetVideoSettings":
            return {"baseWidth": 1920, "baseHeight": 1080}
        if kind == "GetInputList":
            return {"inputs": [{"inputName": name} for name in self.inputs]}
        if kind == "GetSceneItemList":
            return {"sceneItems": [{"sourceName": name, "sceneItemIndex": index, "sceneItemId": index + 1} for index, name in enumerate(self.items[data["sceneName"]])]}
        if kind == "CreateInput":
            self.inputs.add(data["inputName"])
            self.items[data["sceneName"]].append(data["inputName"])
            return {"sceneItemId": len(self.items[data["sceneName"]])}
        return {}


def test_app_source_in_obs(monkeypatch):
    obs = FakeObs()
    result = camera.add_app_to_obs(obs, 8790)
    created = [data for kind, data in obs.calls if kind == "CreateInput"][0]
    assert result["created"] and result["source"] == camera.APP_SOURCE_NAME and created["inputKind"] == "browser_source"
    assert created["inputSettings"]["url"] == "http://127.0.0.1:8790/camera/view" and created["inputSettings"]["shutdown"] is False
    again = camera.add_app_to_obs(obs, 8800)
    assert again["kept"] == ["본방송"] and [data for kind, data in obs.calls if kind == "SetInputSettings"][-1]["inputSettings"]["url"].endswith(":8800/camera/view")
    srv = OverlayServer([], port=0).start()
    try:
        monkeypatch.setattr(camera, "connect", lambda *target: FakeObs())
        srv.obs_target = ("127.0.0.1", 4455, None)
        status, body = local(srv, "POST", "/camera/obs", {"kind": "app"})
        answer = json.loads(body)
        assert status == 200 and answer["source"] == camera.APP_SOURCE_NAME and answer["state"] == "idle"
    finally:
        srv.stop()


def test_remote_control_without_server_uses_its_own_call():
    control = remotes.RemoteControl(Raffle(), MotionState(), DrawState())
    assert isinstance(control.call, camcall.CameraCall)
