import json

import pytest

from debutkit.scenes import PREFIX, SceneOptions, apply, build_scenes, default_kinds, format_plan, resolve_kinds

WINDOWS_KINDS = ["browser_source", "color_source_v3", "game_capture", "image_source", "monitor_capture", "text_gdiplus_v3", "wasapi_input_capture", "window_capture"]


def test_resolve_kinds_prefers_first_candidate():
    kinds = resolve_kinds(WINDOWS_KINDS)
    assert kinds == {"color": "color_source_v3", "text": "text_gdiplus_v3", "browser": "browser_source", "game": "game_capture", "window": "game_capture"}
    linux = resolve_kinds(["browser_source", "color_source_v3", "text_ft2_source_v2", "xcomposite_input", "pipewire-screen-capture-source"])
    assert linux["text"] == "text_ft2_source_v2" and linux["game"] == "pipewire-screen-capture-source" and linux["window"] == "xcomposite_input"


def test_five_scenes_with_overlay_everywhere():
    scenes = build_scenes(1920, 1080, resolve_kinds(WINDOWS_KINDS), SceneOptions(os_name="Windows"))
    assert [scene.name for scene in scenes] == ["대기 화면", "본방송", "토크", "자리 비움", "엔딩"]
    for scene in scenes:
        names = [item.source for item in scene.items]
        assert names[0] == f"{PREFIX}배경"  # 가장 아래
        assert f"{PREFIX}채팅" in names
        assert all(name.startswith(PREFIX) for name in names)
    main = scenes[1]
    assert [item.role for item in main.items] == ["color", "game", "browser", "window"] + ["browser"] * 8
    hidden = [item.source for item in main.items if not item.enabled]  # 방송 연출은 숨긴 채로 넣고 필요할 때 켬, 후원 벽은 캐릭터 뒤
    assert hidden == [f"{PREFIX}{name}" for name in ("후원 벽", "뽑기판", "참여 레이스", "주사위 판", "목표 게이지", "후원 순위")]
    assert [item.settings["url"].rsplit("/", 1)[-1] for item in main.items if not item.enabled] == ["wall", "pick", "race", "board", "goal", "rank"]
    assert all(item.settings["shutdown"] for item in main.items if not item.enabled)  # 숨긴 동안 멈춤
    goal = next(item for item in main.items if item.source.endswith("목표 게이지"))
    assert (goal.settings["width"], goal.settings["height"]) == (1280, 240) and goal.transform["positionX"] + goal.transform["boundsWidth"] < 1920 * 0.33
    assert all(item.enabled for item in scenes[0].items) and "숨김" in format_plan(scenes, resolve_kinds(WINDOWS_KINDS))


def test_items_stay_on_canvas():
    for width, height in ((1920, 1080), (1280, 720), (2560, 1440)):
        for scene in build_scenes(width, height, resolve_kinds(WINDOWS_KINDS)):
            for item in scene.items:
                t = item.transform
                assert 1 <= t["boundsWidth"] <= width and 1 <= t["boundsHeight"] <= height
                assert 0 <= t["positionX"] <= width and 0 <= t["positionY"] <= height


def test_avatar_uses_transparent_window_capture_on_windows():
    scenes = build_scenes(1920, 1080, resolve_kinds(WINDOWS_KINDS), SceneOptions(avatar="vseeface"))
    avatar = next(item for item in scenes[1].items if item.role == "window")
    assert avatar.settings == {"capture_mode": "window", "window": "VSeeFace:UnityWndClass:VSeeFace.exe", "allow_transparency": True}
    talk = next(item for item in scenes[2].items if item.role == "window")
    assert talk.source == avatar.source  # 같은 소스를 장면마다 다른 위치에
    assert talk.transform != avatar.transform


def test_no_avatar_and_missing_kinds_are_skipped():
    scenes = build_scenes(1920, 1080, {"color": "color_source_v3", "browser": "browser_source"}, SceneOptions(avatar="none"))
    for scene in scenes:
        assert {item.role for item in scene.items} <= {"color", "browser"}


def test_text_settings_follow_text_kind():
    gdi = build_scenes(1920, 1080, resolve_kinds(WINDOWS_KINDS), SceneOptions(os_name="Windows"))[0]
    text = next(item for item in gdi.items if item.role == "text")
    assert text.settings["font"]["face"] == "Malgun Gothic" and "color" in text.settings
    ft2 = build_scenes(1920, 1080, default_kinds("Linux"), SceneOptions(os_name="Linux"))[0]
    text = next(item for item in ft2.items if item.role == "text")
    assert "color1" in text.settings


class FakeObs:
    """``request`` 만 흉내 낸다. 받은 요청을 순서대로 기록."""

    def __init__(self, scenes=(), inputs=()):
        self.scenes = list(scenes)
        self.inputs = list(inputs)
        self.calls = []
        self._next_id = 1

    def request(self, kind, data=None):
        self.calls.append((kind, data or {}))
        if kind == "GetSceneList":
            return {"scenes": [{"sceneName": name} for name in self.scenes]}
        if kind == "GetInputList":
            return {"inputs": [{"inputName": name} for name in self.inputs]}
        if kind == "CreateScene":
            self.scenes.append(data["sceneName"])
        if kind == "RemoveScene":
            self.scenes.remove(data["sceneName"])
        if kind == "CreateInput":
            assert data["inputName"] not in self.inputs, "같은 이름의 소스를 두 번 만들면 OBS가 거절한다"
            self.inputs.append(data["inputName"])
        if kind in ("CreateInput", "CreateSceneItem"):
            self._next_id += 1
            return {"sceneItemId": self._next_id}
        return {}


def test_apply_creates_shared_sources_once():
    kinds = resolve_kinds(WINDOWS_KINDS)
    scenes = build_scenes(1920, 1080, kinds)
    obs = FakeObs()
    report = apply(obs, scenes, kinds)
    assert report.created_scenes == [scene.name for scene in scenes]
    created = [data["inputName"] for kind, data in obs.calls if kind == "CreateInput"]
    assert len(created) == len(set(created))
    assert f"{PREFIX}채팅" in created
    reused = [data["sourceName"] for kind, data in obs.calls if kind == "CreateSceneItem"]
    assert reused.count(f"{PREFIX}채팅") == len(scenes) - 1
    enabled = {(kind, data.get("inputName") or data.get("sourceName")): data["sceneItemEnabled"] for kind, data in obs.calls
               if kind in ("CreateInput", "CreateSceneItem")}
    assert enabled[("CreateInput", f"{PREFIX}뽑기판")] is False and enabled[("CreateSceneItem", f"{PREFIX}뽑기판")] is False  # 토크 장면에도 숨김
    assert enabled[("CreateInput", f"{PREFIX}채팅")] is True
    transforms = [kind for kind, _ in obs.calls if kind == "SetSceneItemTransform"]
    assert len(transforms) == sum(len(scene.items) for scene in scenes)
    json.dumps(obs.calls)  # 모든 요청이 JSON으로 보낼 수 있는 값


def test_apply_skips_existing_scenes_unless_replace():
    kinds = resolve_kinds(WINDOWS_KINDS)
    scenes = build_scenes(1920, 1080, kinds)
    obs = FakeObs(scenes=["본방송", "내 장면"], inputs=[f"{PREFIX}채팅"])
    report = apply(obs, scenes, kinds)
    assert "본방송" in report.skipped_scenes and "본방송" not in report.created_scenes
    assert f"{PREFIX}채팅" in report.reused_sources
    assert ("RemoveScene", {"sceneName": "내 장면"}) not in obs.calls

    obs = FakeObs(scenes=["본방송"])
    report = apply(obs, scenes, kinds, replace=True, switch_to="대기 화면")
    assert ("RemoveScene", {"sceneName": "본방송"}) in obs.calls
    assert obs.calls[-1] == ("SetCurrentProgramScene", {"sceneName": "대기 화면"})


def test_apply_against_stream2clip_client():
    """stream2clip ObsClient와 obs-websocket 5 메시지를 실제로 주고받는다(가짜 소켓)."""
    obs_module = pytest.importorskip("stream2clip.obs")

    class Socket:
        def __init__(self):
            self.outbox = [json.dumps({"op": 0, "d": {"obsStudioVersion": "31.1.0", "rpcVersion": 1}})]
            self.requests = []
            self.ids = 0

        def send(self, raw):
            message = json.loads(raw)
            if message["op"] == 1:
                self.outbox.append(json.dumps({"op": 2, "d": {"negotiatedRpcVersion": 1}}))
            elif message["op"] == 6:
                body = message["d"]
                self.requests.append(body["requestType"])
                data = {}
                if body["requestType"] == "GetVideoSettings":
                    data = {"baseWidth": 1280, "baseHeight": 720}
                elif body["requestType"] == "GetInputKindList":
                    data = {"inputKinds": WINDOWS_KINDS}
                elif body["requestType"] in ("CreateInput", "CreateSceneItem"):
                    self.ids += 1
                    data = {"sceneItemId": self.ids}
                self.outbox.append(json.dumps({"op": 7, "d": {"requestType": body["requestType"], "requestId": body["requestId"],
                                                              "requestStatus": {"result": True, "code": 100}, "responseData": data}}))

        def recv(self):
            return self.outbox.pop(0)

        def close(self):
            pass

    socket = Socket()
    client = obs_module.ObsClient(connect=lambda url, timeout: socket, events=0)
    from debutkit.scenes import build_scenes as build

    kinds = resolve_kinds(client.request("GetInputKindList", {"unversioned": False})["inputKinds"])
    report = apply(client, build(1280, 720, kinds), kinds)
    assert len(report.created_scenes) == 5
    assert socket.requests.count("CreateScene") == 5


def test_plan_text_lists_every_scene():
    kinds = default_kinds("Windows")
    text = format_plan(build_scenes(1920, 1080, kinds), kinds)
    for name in ("대기 화면", "본방송", "토크", "자리 비움", "엔딩", "game_capture"):
        assert name in text


def test_missing_window_capture_is_reported(monkeypatch):
    """창 캡처 소스가 없는 OBS(예: 컴포지트 없는 X 서버)에서는 아바타를 생략하고 안내한다."""
    import stream2clip.obs as obs_module

    from debutkit.scenes import SceneOptions, connect_and_apply

    class FakeClient(FakeObs):
        def __init__(self, *args, **kwargs):
            super().__init__()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def request(self, kind, data=None):
            if kind == "GetVideoSettings":
                return {"baseWidth": 1280, "baseHeight": 720}
            if kind == "GetInputKindList":
                return {"inputKinds": ["color_source_v3", "text_ft2_source_v2", "browser_source", "xshm_input_v2"]}
            return super().request(kind, data)

    monkeypatch.setattr(obs_module, "ObsClient", FakeClient)
    report, scenes = connect_and_apply("127.0.0.1", 4455, None, SceneOptions(avatar="vts", os_name="Linux"))
    assert not any("아바타" in item.source for scene in scenes for item in scene.items)
    assert any("창 캡처 소스가 없어 아바타 소스 생략" in note for note in report.notes)
