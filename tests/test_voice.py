"""캐릭터 음성 반응과 캐릭터 화면 서버: 음량 계산, 말하기 판단, OBS 마이크 선택, 화면과 파일 제공."""

import http.client
import json
import time
import urllib.parse
from pathlib import Path

import pytest

from debutkit import character
from debutkit.overlay import voice
from debutkit.overlay.server import OverlayServer


def test_level_and_talk_detector_with_hold():
    assert voice.level_db([[1.0, 1.0, 1.0]]) == 0.0
    assert round(voice.level_db([[0.01, 0.2, 0.2], [0.1, 0.3, 0.3]])) == -20  # 가장 큰 채널
    assert voice.level_db([]) == -120.0
    detector = voice.TalkDetector(-40, gap=6, hold=0.25)
    assert detector.update(-30, 0.0) is True
    assert detector.update(-43, 0.1) is True  # 기준보다 6 dB 낮아지기 전에는 유지
    assert detector.update(-50, 0.2) is True  # 조용해진 직후는 유지
    assert detector.update(-50, 0.5) is False  # 0.25초 지난 뒤 멈춤
    assert detector.update(-41, 0.6) is False


class FakeObs:
    def __init__(self, special=None, inputs=(), events=()):
        self.special, self.inputs, self.batches = special or {}, list(inputs), [list(batch) for batch in events]
        self.requests = []

    def request(self, kind, data=None):
        self.requests.append(kind)
        if kind == "GetSpecialInputs":
            return self.special
        if kind == "GetInputList":
            return {"inputs": self.inputs}
        return {}

    def poll(self, wait):
        return self.batches.pop(0) if self.batches else []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def meters(name, magnitude):
    return {"eventType": "InputVolumeMeters", "eventData": {"inputs": [{"inputName": "다른 소스", "inputLevelsMul": [[1.0, 1.0, 1.0]]},
                                                                      {"inputName": name, "inputLevelsMul": [[magnitude, magnitude, magnitude]]}]}}


def test_choose_input_prefers_obs_mic_then_capture_inputs():
    assert voice.choose_input(FakeObs({"mic1": "마이크/AUX"})) == "마이크/AUX"
    assert voice.choose_input(FakeObs({}, [{"inputName": "게임", "inputKind": "game_capture"},
                                           {"inputName": "USB 마이크", "inputKind": "wasapi_input_capture"}])) == "USB 마이크"
    assert voice.choose_input(FakeObs({"mic1": "x"}), preferred="지정") == "지정"
    assert voice.choose_input(FakeObs({}, [])) is None


def test_meter_publishes_talking_from_the_chosen_input():
    state = voice.VoiceState()
    subscriber, first = state.subscribe()
    assert first["talking"] is False
    notes = []
    times = iter([0.0, 0.1, 0.2, 0.6])
    obs = FakeObs({"mic1": "마이크"}, events=[[meters("마이크", 0.1)], [meters("마이크", 0.001)], [meters("마이크", 0.001)], [meters("마이크", 0.001)]])
    meter = voice.VoiceMeter(state, notify=notes.append, clock=lambda: next(times))
    meter.run_once(obs, until=lambda: not obs.batches)
    published = []
    while not subscriber.empty():
        published.append(subscriber.get_nowait())
    assert published[0]["talking"] is True and published[0]["source"] == "마이크" and published[0]["db"] == -20.0
    assert published[-1]["talking"] is False
    assert "OBS 마이크 '마이크' 사용" in notes[0]
    with pytest.raises(RuntimeError, match="마이크 입력 없음"):
        voice.VoiceMeter(voice.VoiceState()).run_once(FakeObs({}, []))


def test_test_mode_holds_talking_against_real_levels():
    state = voice.VoiceState()
    state.test(True)
    state.publish(False, -120.0, "마이크")
    assert state.current["talking"] is True and state.current["source"] == "시험"
    state.test(False)
    assert state.current["talking"] is False


def test_test_mode_ends_by_itself_without_obs():
    """OBS 음량이 들어오지 않아도 시험이 끝나면 입을 다문다(시험 중 들어온 실제 값이 있으면 그 값)."""
    state = voice.VoiceState()
    state.test(True, seconds=0.1)
    assert state.current["talking"] is True
    deadline = time.monotonic() + 3
    while state.current["talking"] and time.monotonic() < deadline:
        time.sleep(0.02)
    assert state.current == {"talking": False, "level": 0.0, "db": -120.0, "source": ""}
    state.test(True, seconds=0.1)
    state.publish(True, -25.0, "마이크")  # 시험 중 실제로 말하는 중
    state.test(True, seconds=1.0)  # 새 시험: 앞 시험의 종료가 끝내지 않음(느린 실행 환경도 여유 있게)
    time.sleep(0.3)
    assert state.current["source"] == "시험"
    deadline = time.monotonic() + 3
    while state.current["source"] == "시험" and time.monotonic() < deadline:
        time.sleep(0.02)
    assert state.current["talking"] is True and state.current["source"] == "마이크"


@pytest.fixture
def server():
    srv = OverlayServer([], port=0).start()
    yield srv
    srv.stop()


def get(srv, path):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    conn.request("GET", path)
    response = conn.getresponse()
    return response.status, response.getheader("Content-Type"), response.read()


def test_character_page_info_files_and_vendor(server):
    status, _, body = get(server, "/character")
    assert status == 200 and b"importmap" in body and b"/character.js" in body
    status, kind, body = get(server, "/character/info")
    info = json.loads(body)
    assert status == 200 and info["id"] == character.SAMPLE_ID and info["kind"] == "png" and info["renders"]
    status, kind, body = get(server, info["files"]["talk"])
    assert status == 200 and kind == "image/svg+xml" and b"<svg" in body
    assert get(server, "/vendor/three/build/three.module.js")[0] == 200
    assert get(server, "/vendor/three-vrm/three-vrm.module.min.js")[0] == 200
    for bad in ("/vendor/../server.py", "/vendor/three/../../server.py", "/character/files/debutkit/../../server.py", "/character/files/debutkit/README.txt",
                "/character/files/nobody/idle.svg", "/character/info?id=nobody"):
        assert get(server, bad)[0] == 404, bad


def test_voice_stream_and_test_endpoint(server):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.request("GET", "/voice")
    stream = conn.getresponse()
    assert stream.status == 200 and json.loads(stream.fp.readline().decode().removeprefix("data: "))["talking"] is False
    stream.fp.readline()
    post = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    post.request("POST", "/voice/test", body=b'{"talking": true}', headers={"Content-Type": "application/json"})
    assert post.getresponse().status == 200
    state = json.loads(stream.fp.readline().decode().removeprefix("data: "))
    assert state["talking"] is True and state["source"] == "시험"


def test_live_stream_carries_voice_and_tracking_on_one_connection(server):
    """캐릭터 화면, 설정 화면은 /live 연결 하나만 연다(브라우저 같은 주소 동시 연결 6개 제한)."""
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.request("GET", "/live")
    stream = conn.getresponse()
    assert stream.status == 200 and stream.getheader("Content-Type").startswith("text/event-stream")

    def event():
        name = stream.fp.readline().decode().strip().removeprefix("event: ")
        data = json.loads(stream.fp.readline().decode().removeprefix("data: "))
        stream.fp.readline()
        return name, data

    assert event() == ("voice", {"talking": False, "level": 0.0, "db": -120.0, "source": ""})
    assert event()[0] == "tracking"
    assert event()[0] == "motion"
    post = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    post.request("POST", "/voice/test", body=b'{"talking": true}', headers={"Content-Type": "application/json"})
    assert post.getresponse().status == 200
    name, data = event()
    assert name == "voice" and data["talking"] is True
    post = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    post.request("POST", "/tracking", body=b'{"found": true, "yaw": 0.2}', headers={"Content-Type": "application/json"})
    assert post.getresponse().status == 200
    name, data = event()
    assert name == "tracking" and data["found"] is True and data["yaw"] == 0.2
    stream.close()
    conn.close()
    deadline = time.monotonic() + 5  # 연결을 닫으면 세 상태 모두 구독 해제
    while (server.voice._subscribers or server.tracking._subscribers or server.motion._subscribers) and time.monotonic() < deadline:
        server.voice.publish(False, -90.0, "x", force=True)
        server.tracking.publish({"found": False})
        server.motion.play("x")
        time.sleep(0.05)
    assert not server.voice._subscribers and not server.tracking._subscribers and not server.motion._subscribers


def test_stopping_the_server_ends_open_streams():
    """오버레이를 멈추면 열린 연결을 끝내서 OBS 화면이 다시 시작한 서버에 새로 연결한다."""
    srv = OverlayServer([], port=0).start()
    streams = []
    for path in ("/events", "/live", "/voice"):
        conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
        conn.request("GET", path)
        response = conn.getresponse()
        assert response.status == 200
        streams.append(response)
    streams[1].fp.readline()
    started = time.monotonic()
    srv.stop()
    for response in streams:
        while response.fp.readline():  # 서버가 끝내면 빈 줄(연결 종료)
            pass
    assert time.monotonic() - started < 3 and srv.hub.listeners == 0 and not srv.voice._subscribers


def test_port_in_use_is_refused():
    """같은 포트에 두 번째 서버가 열리지 않는다(Windows 기본 동작은 함께 열어 줌)."""
    first = OverlayServer([], port=0)
    try:
        with pytest.raises(OSError):
            OverlayServer([], port=first.port)
    finally:
        first.stop()


def test_bad_post_bodies_get_answers(server):
    for body, headers, path, status in ((b"x", {"Content-Length": "abc"}, "/test", 400), (b"[1, 2]", {}, "/test", 200),
                                        (b"[1, 2]", {}, "/voice/test", 200), (b"[1, 2]", {}, "/tracking", 400)):
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        conn.putrequest("POST", path)
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", headers.get("Content-Length", str(len(body))))
        conn.endheaders(body)
        assert conn.getresponse().status == status, (path, body)


def test_settings_page_uses_one_stream():
    """설정 화면은 연결 1개, 미리보기(채팅, 알림, 캐릭터)는 공유 연결(live.js) 1개: 브라우저 제한(6개) 안."""
    static = Path(character.__file__).parent / "overlay" / "static"
    page = (static / "index.html").read_text(encoding="utf-8")
    assert page.count("new EventSource(") == 1 and 'new EventSource("/live")' in page
    script = (static / "character.js").read_text(encoding="utf-8")
    assert "new EventSource(" not in script and "debutkitLive.subscribe" in script


def test_korean_character_ids_are_url_encoded(server, tmp_path):
    from test_character import png

    added = character.add_png(png(tmp_path / "a.png"), png(tmp_path / "b.png"), name="고양이 캐릭터")
    status, _, body = get(server, "/character/info?id=" + urllib.parse.quote(added.id))
    info = json.loads(body)
    assert status == 200 and info["id"] == "고양이-캐릭터" and "%EA%B3%A0" in info["files"]["idle"]
    status, kind, image = get(server, info["files"]["idle"])
    assert status == 200 and kind == "image/png" and image.startswith(b"\x89PNG")


def test_vrm_file_names_with_spaces_and_korean_are_served(server, tmp_path):
    from test_character import vrm1

    for name in ("My Model #2.vrm", "모델.vrm"):
        added = character.add(vrm1(tmp_path / name))
        info = json.loads(get(server, "/character/info?id=" + urllib.parse.quote(added.id))[2])
        assert " " not in info["files"]["model"] and "#" not in info["files"]["model"]
        status, kind, body = get(server, info["files"]["model"])
        assert status == 200 and kind == "model/gltf-binary" and body.startswith(b"glTF"), name
        assert get(server, info["thumbnail"])[0] == 200


def test_tracking_values_are_cleaned():
    from debutkit.overlay import tracking

    assert tracking.clean({"found": True, "yaw": 3.0, "blinkLeft": -1, "mouth": 0.5, "extra": 1, "pitch": float("nan"), "roll": True}) == \
        {"found": True, "yaw": 1.2, "blinkLeft": 0.0, "mouth": 0.5}
    assert tracking.clean({"found": "yes"}) == {"found": False}
    assert tracking.clean([1, 2]) is None


def test_tracker_page_policy_and_tracking_stream(server):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.request("GET", "/tracker")
    page = conn.getresponse()
    body = page.read()
    policy = page.getheader("Content-Security-Policy") or ""
    assert page.status == 200 and b"/tracker.js" in body
    assert "connect-src 'self'" in policy and "default-src 'self'" in policy and "wasm-unsafe-eval" in policy
    assert get(server, "/character")[0] == 200 and "Content-Security-Policy" not in dict(get_headers(server, "/character"))
    for path, kind in (("/vendor/mediapipe/vision_bundle.mjs", "text/javascript"), ("/vendor/mediapipe/wasm/vision_wasm_internal.wasm", "application/wasm"),
                       ("/vendor/mediapipe/face_landmarker.task", "application/octet-stream")):
        status, content_type, _ = get(server, path)
        assert status == 200 and content_type.startswith(kind), path
    stream_conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    stream_conn.request("GET", "/tracking")
    stream = stream_conn.getresponse()
    assert json.loads(stream.fp.readline().decode().removeprefix("data: "))["found"] is False
    stream.fp.readline()
    post = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    post.request("POST", "/tracking", body=json.dumps({"found": True, "yaw": 0.3, "blinkLeft": 0.9}).encode(), headers={"Content-Type": "application/json"})
    assert post.getresponse().status == 200
    state = json.loads(stream.fp.readline().decode().removeprefix("data: "))
    assert state["found"] is True and state["yaw"] == 0.3 and state["blinkLeft"] == 0.9 and state["time"] > 0
    bad = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    bad.request("POST", "/tracking", body=b"[1]", headers={"Content-Type": "application/json"})
    assert bad.getresponse().status == 400
    foreign = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    foreign.request("POST", "/tracking", body=b'{"found": true}', headers={"Origin": "https://evil.example", "Content-Type": "application/json"})
    assert foreign.getresponse().status == 403


def get_headers(srv, path):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    conn.request("GET", path)
    response = conn.getresponse()
    response.read()
    return response.getheaders()
