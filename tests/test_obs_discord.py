"""OBS에 넣기(/obs/add), 디스코드 합방(음성 위젯 꾸미기, 웹훅), 초보자 화면(시작하기 목록, 메뉴, 용어 풀이)."""

import base64
import http.client
import io
import json
import urllib.error
from pathlib import Path

import pytest

from debutkit.overlay import discord, feature, obs_add
from debutkit.overlay.events import DemoChat, OverlayEvent
from debutkit.overlay.server import OverlayServer

STATIC = Path(__file__).resolve().parent.parent / "src" / "debutkit" / "overlay" / "static"
PNG = b"\x89PNG\r\n\x1a\n" + bytes(32)


class FakeObs:
    """OBS WebSocket 흉내: 받은 요청을 기록."""

    def __init__(self, *, inputs=(), items=(), kinds=("browser_source",), scene="본방송"):
        self.calls = []
        self.inputs = list(inputs)
        self.items = list(items)
        self.kinds = list(kinds)
        self.scene = scene

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def request(self, name, data=None):
        self.calls.append((name, data))
        if name == "GetInputKindList":
            return {"inputKinds": self.kinds}
        if name == "GetCurrentProgramScene":
            return {"sceneName": self.scene}
        if name == "GetVideoSettings":
            return {"baseWidth": 2560, "baseHeight": 1440}
        if name == "GetInputList":
            return {"inputs": [{"inputName": name_} for name_ in self.inputs]}
        if name == "GetSceneItemList":
            return {"sceneItems": self.items}
        if name in ("CreateInput", "CreateSceneItem"):
            return {"sceneItemId": 7}
        return {}


def names(fake):
    return [name for name, _ in fake.calls]


def test_add_creates_browser_source_with_size_place_and_alert_sound():
    fake = FakeObs()
    done = obs_add.add(fake, "alerts", "http://127.0.0.1:8790")
    assert done == {"source": "[DK] 후원 알림", "scene": "본방송", "created": True, "added": True, "url": "http://127.0.0.1:8790/alerts"}
    create = dict(fake.calls)["CreateInput"]
    assert create["inputKind"] == "browser_source" and create["inputSettings"]["width"] == 1920 and create["inputSettings"]["reroute_audio"] is True
    transform = dict(fake.calls)["SetSceneItemTransform"]["sceneItemTransform"]
    assert (transform["boundsWidth"], transform["boundsHeight"]) == (2560, 1440)  # 캔버스 크기에 맞춤
    assert dict(fake.calls)["SetInputAudioMonitorType"]["monitorType"] == "OBS_MONITORING_TYPE_MONITOR_AND_OUTPUT"
    # 이미 있으면 주소만 맞추고, 장면에 있으면 다시 넣지 않음. 채팅은 고른 표시 값을 주소에
    chat = FakeObs(inputs=["[DK] 채팅"], items=[{"sourceName": "[DK] 채팅", "sceneItemId": 3, "sceneItemEnabled": False}])
    done = obs_add.add(chat, "chat", "http://127.0.0.1:8790", query="theme=card&font=26")
    assert done["created"] is False and done["added"] is False and done["url"].endswith("/chat?theme=card&font=26")
    assert "SetInputSettings" in names(chat) and "CreateInput" not in names(chat) and "SetSceneItemEnabled" in names(chat)
    assert "SetInputAudioMonitorType" not in names(chat)
    frame = obs_add.add(FakeObs(), "frame-cam", "http://127.0.0.1:8790", query="look=neon")
    assert frame["url"].endswith("/frame?kind=cam&look=neon")


def test_add_refuses_bad_input_and_explains_obs_errors():
    with pytest.raises(obs_add.ObsAddError, match="브라우저 소스가 없음"):
        obs_add.add(FakeObs(kinds=()), "chat", "http://x")
    with pytest.raises(obs_add.ObsAddError, match="쓸 수 없는 글자"):
        obs_add.add(FakeObs(), "chat", "http://x", query="a=<script>")
    with pytest.raises(obs_add.ObsAddError, match="streamkit"):
        obs_add.add(FakeObs(), "discord", "http://x", url="https://evil.example/overlay")
    assert "WebSocket 서버 설정" in obs_add.explain(RuntimeError("Cannot reach OBS at ws://127.0.0.1:4455. Is OBS running"))
    assert "비밀번호" in obs_add.explain(RuntimeError("Authentication failed"))
    fake = FakeObs(items=[{"sourceName": "[DK] 채팅"}, {"sourceName": "[DK] 후원 알림"}])
    assert obs_add.check(fake) == {"connected": True, "scene": "본방송", "inside": ["chat", "alerts"]}


def request(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, data


def test_obs_routes_use_the_overlay_obs_target(monkeypatch):
    fake = FakeObs()
    monkeypatch.setattr("debutkit.camera.connect", lambda host, port, password: fake)
    server = OverlayServer([], port=0).start()
    try:
        status, body = request(server.port, "GET", "/obs/status")
        assert json.loads(body)["ready"] is False and "설정 마법사" in json.loads(body)["error"]
        server.obs_target = ("127.0.0.1", 4455, None)
        assert json.loads(request(server.port, "GET", "/obs/status?fresh=1")[1]) == {"ready": True, "connected": True, "scene": "본방송", "inside": []}
        status, body = request(server.port, "POST", "/obs/add", {"kind": "chat", "query": "theme=card"})
        answer = json.loads(body)
        assert status == 200 and answer["source"] == "[DK] 채팅" and "본방송 장면에 넣음" in answer["message"]
        assert answer["url"] == f"http://127.0.0.1:{server.port}/chat?theme=card"
        assert request(server.port, "POST", "/obs/add", {"kind": "nope"})[0] == 400
    finally:
        server.stop()


# --------------------------------------------------------------------------- 디스코드


def test_widget_css_follows_style_and_swaps_pictures(tmp_path):
    config = discord.load()
    assert config["widget"] == "" and config["layout"] == "column"
    with pytest.raises(discord.DiscordError, match="streamkit"):
        discord.check_widget("https://evil.example/overlay/voice/1/2")
    widget = discord.check_widget("https://streamkit.discord.com/overlay/voice/123456789012345678/223456789012345678?icon=true")
    assert widget == "https://streamkit.discord.com/overlay/voice/123456789012345678/223456789012345678"
    config.update(widget=widget, speaking_only=True, layout="row")
    tokens = {"primary": "#19b8b0", "surface": "#000", "on-surface": "#fff", "line-width": "2px", "line-style": "solid", "line": "#fff",
              "radius": "8px", "display": "x", "glow": "none", "shadow": "none"}
    css = discord.css(config, tokens)
    assert "flex-direction: row" in css and "#19b8b0" in css and ":has(" not in css  # OBS(Chromium 103)에 :has 없음
    assert '[class*="Voice_avatarSpeaking"]' in css and "background-color: rgba(0, 0, 0, 0)" in css
    assert "hide_names=false" in discord.widget_url(config) and discord.widget_url({**config, "widget": ""}) == ""


def test_webhook_checks_url_blocks_mentions_and_retries_once():
    with pytest.raises(discord.DiscordError, match="웹훅 주소"):
        discord.check_webhook("https://evil.example/api/webhooks/1/abc")
    url = discord.check_webhook("https://discord.com/api/webhooks/123456789012345678/" + "a" * 68)
    sent = []

    class Answer(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def opener(request, timeout=0):
        sent.append(json.loads(request.data))
        if len(sent) == 1:  # 처음은 속도 제한, 알려 준 시간 뒤 한 번 더
            raise urllib.error.HTTPError(url, 429, "slow", {}, io.BytesIO(b'{"retry_after": 0.01}'))
        return Answer(b"")

    discord.post_webhook(url, "@everyone 방송 시작", opener=opener)
    assert len(sent) == 2 and sent[1]["allowed_mentions"] == {"parse": []} and sent[1]["username"] == "debutkit"
    with pytest.raises(discord.DiscordError, match="웹훅이 지워졌"):
        discord.post_webhook(url, "x", opener=lambda request, timeout=0: (_ for _ in ()).throw(urllib.error.HTTPError(url, 404, "no", {}, io.BytesIO(b""))))


def test_webhook_posts_start_once_and_summary_at_stop(monkeypatch):
    posted = []
    hook = discord.Webhook(poster=lambda url, text: posted.append(text))
    monkeypatch.setattr(discord.Webhook, "url", lambda self: "https://discord.com/api/webhooks/1/x")
    monkeypatch.setattr(discord.threading, "Thread", lambda target, args, daemon: type("T", (), {"start": lambda self: target(*args)})())
    config = discord.load()
    config.update(channel_name="도토리", channel_url="https://chzzk.naver.com/live/x")
    discord.save(config)
    hook.tap(DemoChat(seed=3).make())  # 데모 채팅은 방송 시작으로 치지 않음
    hook.tap(OverlayEvent("demo", "chat", "시험", (("text", "hi"),)))
    assert posted == [] and hook.started is False
    hook.tap(OverlayEvent("chzzk", "chat", "a", (("text", "hi"),), user="1"))
    hook.tap(OverlayEvent("soop", "donation", "b", (), amount=10, unit="별풍선", user="2"))
    hook.tap(OverlayEvent("chzzk", "donation", "c", (), amount=5000, unit="원", user="3"))
    assert posted == ["도토리 방송 시작! https://chzzk.naver.com/live/x"]
    hook.stop()
    assert posted[1].startswith("도토리 방송 끝") and "채팅 1개, 후원 2번, 약 6,000원" in posted[1]


def test_discord_routes_people_and_pictures():
    sent = []
    server = OverlayServer([], port=0).start()
    try:
        port = server.port
        status, body = request(port, "POST", "/discord/config", {"widget": "https://streamkit.discord.com/overlay/voice/123456789012345678/223456789012345678",
                                                                  "size": 96, "names": False})
        info = json.loads(body)
        assert status == 200 and info["size"] == 96 and "display: none" in info["css"] and info["obs_url"].startswith("https://streamkit.discord.com/")
        data = "data:image/png;base64," + base64.b64encode(PNG).decode()
        status, body = request(port, "POST", "/discord/person", {"id": "312345678901234567", "name": "숲속토끼", "idle": data, "talk": data})
        info = json.loads(body)
        assert status == 200 and info["people"][0]["idle"].endswith(".png") and 'img[src*="/avatars/312345678901234567/"]' in info["css"]
        assert "data:image/png;base64," in info["css"]
        assert request(port, "POST", "/discord/person", {"id": "abc"})[0] == 400
        assert request(port, "POST", "/discord/webhook", {"url": "https://example.com/x"})[0] == 400
        assert request(port, "POST", "/discord/send", {"text": "x"})[0] == 400  # 웹훅 없음
        status, body = request(port, "POST", "/discord/person/remove", {"id": "312345678901234567"})
        assert json.loads(body)["people"] == [] and not list(discord.settings.data_path(discord.FOLDER).glob("*"))
        status, body = request(port, "GET", "/discord/control")
        assert status == 200 and b"/obs/add" in body and b"Voice_avatarSpeaking" in body
    finally:
        server.stop()
    assert sent == []


# --------------------------------------------------------------------------- 초보자 화면


def test_beginner_pages_have_checklist_menu_and_help():
    ui = (STATIC / "ui.js").read_text(encoding="utf-8")
    for group in ("시작하기", "꾸미기", "방송 중 놀이", "팬과 함께", "더 보기"):
        assert f'["{group}"' in ui, group
    assert "dk-subnav" in ui and "data-obs" in ui and "layer-width" in ui and "GLOSSARY" in ui and '"/discord/control"' in ui
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    for step in ("run", "obs", "add", "test", "look"):
        assert f'data-step="{step}"' in page, step
    assert page.index('src="/ui.js"') < page.index("debutkitUi.onObs")  # ui.js를 먼저 불러야 목록이 OBS 상태를 받음
    assert 'data-obs="chat" data-obs-from="chat-url"' in page and 'data-help="브라우저 소스"' in page
    assert "debutkit scenes" not in page and "debutkit motion add" not in page and "debutkit character use" not in page
    for name in ("draw-control.html", "pick-control.html", "wall-control.html", "race-control.html", "alerts-control.html", "community-control.html"):
        assert 'data-obs="' in (STATIC / name).read_text(encoding="utf-8"), name
    stage = (STATIC / "stage.html").read_text(encoding="utf-8")
    assert stage.index("추천 조합") < stage.index("방송 화면에 놓을 것") and "COMBOS" in stage
    assert feature.Context(notify=print).obs() is None
