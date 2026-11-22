"""캐릭터 음성 반응과 캐릭터 화면 서버: 음량 계산, 말하기 판단, OBS 마이크 선택, 화면과 파일 제공."""

import http.client
import json
import urllib.parse

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


def test_korean_character_ids_are_url_encoded(server, tmp_path):
    from test_character import png

    added = character.add_png(png(tmp_path / "a.png"), png(tmp_path / "b.png"), name="고양이 캐릭터")
    status, _, body = get(server, "/character/info?id=" + urllib.parse.quote(added.id))
    info = json.loads(body)
    assert status == 200 and info["id"] == "고양이-캐릭터" and "%EA%B3%A0" in info["files"]["idle"]
    status, kind, image = get(server, info["files"]["idle"])
    assert status == 200 and kind == "image/png" and image.startswith(b"\x89PNG")
