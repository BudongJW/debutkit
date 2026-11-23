"""휴대폰 카메라 영상(camera.py): SRT 수신 OBS 미디어 소스, 암호 보관, Larix 가져오기 주소, QR, 서버 경로, 명령줄."""

from __future__ import annotations

import http.client
import json
import re
import time
from pathlib import Path

import pytest

from debutkit import camera, settings
from debutkit.cli import main
from debutkit.overlay.server import OverlayServer


class FakeObs:
    """obs-websocket 요청을 기록하고 장면, 입력 목록을 흉내 낸다."""

    def __init__(self, *, kinds=("ffmpeg_source", "browser_source"), scenes=("본방송", "토크"), current="본방송", inputs=(), items=None,
                 state="OBS_MEDIA_STATE_PLAYING", size=(0, 0)):
        self.kinds, self.scenes, self.current, self.state, self.size = list(kinds), list(scenes), current, state, size
        self.inputs = set(inputs)
        self.items = {name: list((items or {}).get(name, [])) for name in self.scenes}
        self.calls: list[tuple[str, dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def request(self, kind, data=None):
        data = data or {}
        self.calls.append((kind, data))
        if kind == "GetInputKindList":
            return {"inputKinds": self.kinds}
        if kind == "GetCurrentProgramScene":
            return {"sceneName": self.current, "currentProgramSceneName": self.current}
        if kind == "GetSceneList":
            return {"scenes": [{"sceneName": name} for name in self.scenes]}
        if kind == "GetVideoSettings":
            return {"baseWidth": 1920, "baseHeight": 1080}
        if kind == "GetInputList":
            return {"inputs": [{"inputName": name} for name in sorted(self.inputs)]}
        if kind == "GetSceneItemList":
            return {"sceneItems": [{"sourceName": name, "sceneItemIndex": index, "sceneItemId": index + 1}
                                   for index, name in enumerate(self.items[data["sceneName"]])]}
        if kind == "CreateInput":
            self.inputs.add(data["inputName"])
            self.items[data["sceneName"]].append(data["inputName"])
            return {"sceneItemId": len(self.items[data["sceneName"]])}
        if kind == "CreateSceneItem":
            self.items[data["sceneName"]].append(data["sourceName"])
            return {"sceneItemId": len(self.items[data["sceneName"]])}
        if kind == "GetMediaInputStatus":
            return {"mediaState": self.state}
        if kind == "GetSceneItemTransform":
            return {"sceneItemTransform": {"sourceWidth": self.size[0], "sourceHeight": self.size[1]}}
        return {}

    def named(self, kind):
        return [data for name, data in self.calls if name == kind]


CONFIG = camera.CameraConfig(9710, 200, "abcdefghjkmn")


def test_config_keeps_passphrase_outside_settings():
    first = camera.load_config()
    assert first.port == 9710 and first.latency == 200 and len(first.passphrase) == 12 and set(first.passphrase) <= set(camera.PASS_CHARS)
    assert camera.load_config() == first and camera.config_path().name == "phone-camera.json"
    assert "passphrase" not in json.dumps(settings.load())  # 저장 설정 파일에는 넣지 않음
    changed = camera.update_config(port=9800, latency=300)
    assert changed.port == 9800 and changed.latency == 300 and changed.passphrase == first.passphrase
    renewed = camera.update_config(new_pass=True)
    assert renewed.passphrase != first.passphrase and camera.load_config() == renewed
    for bad in ({"port": 80}, {"port": "9000"}, {"port": True}, {"latency": 10}, {"latency": 5000}, {"latency": 1.5}):
        with pytest.raises(camera.CameraError):
            camera.update_config(**bad)
    camera.config_path().write_text('{"port": 1, "latency": "x", "passphrase": "short"}', encoding="utf-8")
    repaired = camera.load_config()
    assert repaired.port == 9710 and repaired.latency == 200 and len(repaired.passphrase) == 12
    camera.config_path().write_text("[broken", encoding="utf-8")
    assert len(camera.load_config().passphrase) == 12


def test_obs_input_and_sender_links():
    assert camera.obs_input(CONFIG) == "srt://0.0.0.0:9710?mode=listener&latency=200000&passphrase=abcdefghjkmn&pbkeylen=16"
    settings_ = camera.source_settings(CONFIG)
    assert settings_["is_local_file"] is False and settings_["input_format"] == "mpegts" and settings_["buffering_mb"] == 0
    assert settings_["restart_on_activate"] is False and settings_["close_when_inactive"] is False and settings_["reconnect_delay_sec"] == 1
    link = camera.larix_link("192.168.0.5", CONFIG)
    assert link.startswith("larix://set/v1?conn[][url]=srt://192.168.0.5:9710&conn[][name]=debutkit%20camera&conn[][overwrite]=on")
    assert "&conn[][mode]=v&conn[][srtmode]=c&conn[][srtlatency]=200&conn[][srtpass]=abcdefghjkmn&conn[][srtpbkl]=16" in link
    assert "conn[][mode]=va" in camera.larix_link("192.168.0.5", CONFIG, audio=True)
    info = camera.connection_info(CONFIG, ["192.168.0.5", "10.0.0.2"])
    assert info["url"] == "srt://192.168.0.5:9710" and info["passphrase"] == "abcdefghjkmn" and info["source"] == camera.SOURCE_NAME
    assert camera.connection_info(CONFIG, [])["url"] == ""


def test_lan_addresses_and_qr(monkeypatch):
    slow = []

    def hang(*args):
        slow.append(1)
        time.sleep(5)
        return []

    monkeypatch.setattr(camera, "_ADDRESSES", (0.0, []))
    monkeypatch.setattr(camera.socket, "getaddrinfo", hang)
    started = time.monotonic()
    camera.lan_addresses()
    assert slow and time.monotonic() - started < 2  # 컴퓨터 이름 조회가 늦어도 1초 뒤 포기
    camera.lan_addresses()
    assert len(slow) == 1  # 10초 동안 기억
    monkeypatch.undo()
    found = camera.lan_addresses(extra=["192.168.0.77", "8.8.8.8", "127.0.0.1", "169.254.1.1", "bad", "192.168.0.77"])
    assert "192.168.0.77" in found and found.count("192.168.0.77") == 1
    assert not any(address in found for address in ("8.8.8.8", "127.0.0.1", "169.254.1.1", "bad"))
    link = camera.larix_link("192.168.0.5", CONFIG)
    matrix = camera.qr_matrix(link)
    assert len(matrix) == len(matrix[0]) and (len(matrix) - 17) % 4 == 0 and len(matrix) >= 33  # QR 버전 크기(4n + 17)
    svg = camera.qr_svg(link)
    assert svg.startswith("<svg") and f'viewBox="0 0 {len(matrix) + 8} {len(matrix) + 8}"' in svg
    assert svg.count("h1v1h-1z") == sum(cell for line in matrix for cell in line)


def test_add_to_obs_creates_places_and_reuses():
    obs = FakeObs(items={"본방송": ["[DK] 배경", "[DK] 게임 화면", "[DK] 채팅", "[DK] 후원 알림", "[DK] 후원 추첨"]})
    result = camera.add_to_obs(obs, CONFIG)
    assert result == {"source": camera.SOURCE_NAME, "created": True, "updated": False, "added": ["본방송"], "kept": []}
    created = obs.named("CreateInput")[0]
    assert created["sceneName"] == "본방송" and created["inputKind"] == "ffmpeg_source" and created["inputSettings"] == camera.source_settings(CONFIG)
    transform = obs.named("SetSceneItemTransform")[0]["sceneItemTransform"]
    assert transform["positionX"] == 32 and transform["positionY"] == 32 and transform["boundsWidth"] == 576 and transform["alignment"] == 5
    assert obs.named("SetSceneItemIndex")[0]["sceneItemIndex"] == 2  # 채팅, 알림, 추첨 아래 층
    # 두 번째: 설정만 맞추고 이미 있는 장면은 그대로, 지정한 다른 장면에는 추가
    again = camera.add_to_obs(obs, camera.CameraConfig(9800, 300, "zzzzzzzzzzzz"), ["본방송", "토크"])
    assert again["created"] is False and again["updated"] is True and again["kept"] == ["본방송"] and again["added"] == ["토크"]
    assert obs.named("SetInputSettings")[0]["inputSettings"]["input"].startswith("srt://0.0.0.0:9800?")
    assert obs.named("CreateSceneItem")[0] == {"sceneName": "토크", "sourceName": camera.SOURCE_NAME}
    assert len(obs.named("CreateInput")) == 1
    # SRT 수신 대기 중에도 OBS는 PLAYING: 영상 크기로 수신 여부 판단
    assert camera.media_state(obs) == {"exists": True, "state": "OBS_MEDIA_STATE_PLAYING", "receiving": False, "size": [0, 0], "text": "휴대폰 연결 대기"}
    obs.size = (1280, 720)
    assert camera.media_state(obs)["receiving"] is True and camera.media_state(obs)["text"] == "휴대폰 영상 수신 중(1280x720)"
    obs.state = "OBS_MEDIA_STATE_ERROR"
    assert camera.media_state(obs)["receiving"] is False and "오류" in camera.media_state(obs)["text"]
    lonely = FakeObs(inputs=[camera.SOURCE_NAME])
    assert camera.media_state(lonely)["size"] is None and "어느 장면에도 없음" in camera.media_state(lonely)["text"]
    with pytest.raises(camera.CameraError, match="없는 장면"):
        camera.add_to_obs(obs, CONFIG, ["엔딩"])
    with pytest.raises(camera.CameraError, match="미디어 소스"):
        camera.add_to_obs(FakeObs(kinds=("browser_source",)), CONFIG)
    assert camera.media_state(FakeObs())["exists"] is False


def test_obs_failure_messages():
    assert "연결하지 못함" in camera.obs_failure(RuntimeError("Cannot reach OBS at ws://127.0.0.1:4455"))
    assert "연결하지 못함" in camera.obs_failure(ConnectionRefusedError("refused"))
    assert "비밀번호" in camera.obs_failure(RuntimeError("OBS asks for a WebSocket password"))
    assert "요청 실패" in camera.obs_failure(RuntimeError("CreateInput failed"))


def request(srv, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json", **(headers or {})})
    response = conn.getresponse()
    data = response.read()
    content_type = response.getheader("Content-Type")
    conn.close()
    return response.status, data, content_type


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(camera, "lan_addresses", lambda extra=(): ["192.168.0.5", "10.0.0.2"])
    srv = OverlayServer([], port=0).start()
    yield srv
    srv.stop()


def test_server_camera_routes(server, monkeypatch):
    status, body, _ = request(server, "GET", "/camera")
    info = json.loads(body)
    assert status == 200 and info["obs"] is False and info["url"] == "srt://192.168.0.5:9710" and info["addresses"] == ["192.168.0.5", "10.0.0.2"]
    status, body, kind = request(server, "GET", "/camera/qr.svg?address=10.0.0.2")
    assert status == 200 and kind == "image/svg+xml" and body.startswith(b"<svg")
    assert request(server, "GET", "/camera/qr.svg?address=8.8.8.8")[0] == 404
    status, body, _ = request(server, "GET", "/camera/status")
    assert status == 400 and "OBS 연결 정보 없음" in json.loads(body)["error"]

    obs = FakeObs(items={"본방송": ["[DK] 채팅"]})
    opened = []
    monkeypatch.setattr(camera, "connect", lambda *target: opened.append(target) or obs)
    server.obs_target = ("127.0.0.1", 4455, "pw")
    status, body, _ = request(server, "POST", "/camera/obs", {})
    answer = json.loads(body)
    assert status == 200 and answer["created"] and answer["added"] == ["본방송"] and answer["text"] == "휴대폰 연결 대기"
    assert opened[-1] == ("127.0.0.1", 4455, "pw")
    obs.size = (1080, 1920)  # 세로 영상
    status, body, _ = request(server, "GET", "/camera/status")
    assert status == 200 and json.loads(body)["receiving"] is True and json.loads(body)["text"] == "휴대폰 영상 수신 중(1080x1920)"
    old = info["passphrase"]
    status, body, _ = request(server, "POST", "/camera/config", {"new_passphrase": True, "latency": 400})
    answer = json.loads(body)
    assert status == 200 and answer["passphrase"] != old and answer["latency"] == 400 and answer["obs_updated"] is True
    assert "latency=400000" in obs.named("SetInputSettings")[-1]["inputSettings"]["input"]
    status, body, _ = request(server, "POST", "/camera/config", {"port": 22})
    assert status == 400 and "포트" in json.loads(body)["error"]
    status, body, _ = request(server, "POST", "/camera/obs", {"scenes": ["없는 장면"]})
    assert status == 400 and "없는 장면" in json.loads(body)["error"]

    def offline(*target):
        raise RuntimeError("Cannot reach OBS at ws://127.0.0.1:4455")

    monkeypatch.setattr(camera, "connect", offline)
    status, body, _ = request(server, "GET", "/camera/status")
    assert status == 502 and "연결하지 못함" in json.loads(body)["error"]
    assert request(server, "POST", "/camera/obs", {}, {"Origin": "https://evil.example"})[0] == 403
    status, body, _ = request(server, "GET", "/phone")
    assert status == 200 and "휴대폰 카메라 영상".encode() in body and b"/camera/qr.svg" in body


def test_cli_camera(monkeypatch, capsys):
    monkeypatch.setattr(camera, "lan_addresses", lambda extra=(): ["192.168.0.5"])
    assert main(["camera", "info"]) == 0
    out = capsys.readouterr().out
    passphrase = camera.load_config().passphrase
    assert "srt://192.168.0.5:9710" in out and passphrase in out and "larix://set/v1?" in out
    obs = FakeObs()
    monkeypatch.setattr(camera, "connect", lambda *target: obs)
    assert main(["camera", "setup", "--latency", "300", "--scene", "토크"]) == 0
    out = capsys.readouterr().out
    assert "만듦" in out and "토크 장면에 추가" in out and "휴대폰 연결 대기" in out and camera.load_config().latency == 300
    assert main(["camera", "status", "--obs-port", "4456"]) == 0 and "휴대폰 연결 대기" in capsys.readouterr().out
    assert main(["camera", "setup", "--port", "80"]) == 1 and "포트" in capsys.readouterr().err
    monkeypatch.setattr(camera, "connect", lambda *target: (_ for _ in ()).throw(RuntimeError("Cannot reach OBS")))
    assert main(["camera", "status"]) == 1 and "연결하지 못함" in capsys.readouterr().err


def test_phone_page_has_no_outside_addresses():
    """휴대폰 연결 화면은 이 PC 서버에만 요청(암호, 주소를 외부로 보내지 않음)."""
    page = (Path(__file__).parents[1] / "src" / "debutkit" / "overlay" / "static" / "phone.html").read_text(encoding="utf-8")
    assert not re.search(r"https?://(?!127\.0\.0\.1)", page)


def test_vendored_qr_library_is_unmodified_and_noticed():
    import hashlib

    root = Path(__file__).parents[1] / "src" / "debutkit" / "vendor"
    readme = (root / "README.txt").read_text(encoding="utf-8")
    assert hashlib.sha256((root / "qrcodegen.py").read_bytes()).hexdigest() in readme  # 원본 그대로(.gitattributes 줄 끝 변환 없음)
    assert "Permission is hereby granted" in readme and "Project Nayuki" in readme
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert '"vendor/README.txt"' in pyproject and 'extend-exclude = ["src/debutkit/vendor"]' in pyproject
