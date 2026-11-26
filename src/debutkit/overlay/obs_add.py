"""OBS에 넣기: 방송 화면 주소를 복사해 OBS 브라우저 소스를 만들고 크기를 입력하는 대신, 단추 하나로 지금 OBS 장면에 넣는다.

- ``POST /obs/add`` (``{"kind": "chat", "query": "theme=card", "css": ""}``): ``[DK] 이름`` 브라우저 소스를 만들거나(처음)
  주소와 크기를 맞추고(이미 있으면, 장면 만들기가 만든 소스 포함) 지금 방송 장면에 없으면 추가한다. 화면 크기는 OBS 캔버스에 맞춰 놓는다
- ``GET /obs/status``: OBS 연결 정보가 있는지(명령줄, 설정 마법사가 알려 줌)
- OBS WebSocket(OBS 28 이상 기본 포함)을 쓴다. OBS 도구 메뉴의 WebSocket 서버 설정에서 서버 사용을 켜야 한다
"""

from __future__ import annotations

import re
from typing import Any, Callable

from . import feature

PREFIX = "[DK] "
#: kind -> (소스 이름, 주소, 화면 너비, 높이, 놓을 자리). 놓을 자리는 1920x1080 기준 (왼쪽, 위, 가로, 세로), None이면 화면 전체
SOURCES: dict[str, tuple[str, str, int, int, tuple[int, int, int, int] | None]] = {
    "chat": ("채팅", "/chat", 422, 1016, (1466, 32, 422, 1016)),
    "alerts": ("후원 알림", "/alerts", 1920, 1080, None),
    "character": ("캐릭터", "/character", 720, 900, (0, 410, 614, 670)),
    "draw": ("후원 추첨", "/draw", 1920, 1080, None),
    "pick": ("뽑기판", "/pick", 1920, 1080, None),
    "wall": ("후원 벽", "/wall", 1920, 1080, None),
    "goal": ("목표 게이지", "/wall/goal", 1280, 240, (33, 24, 576, 108)),
    "rank": ("후원 순위", "/wall/rank", 560, 720, (33, 151, 288, 389)),
    "race": ("참여 레이스", "/race", 1920, 1080, None),
    "community": ("커뮤니티", "/community", 1920, 1080, None),
    "frame-cam": ("캐릭터 프레임", "/frame?kind=cam", 614, 670, (0, 410, 614, 670)),
    "frame-starting": ("대기 화면 프레임", "/frame?kind=starting", 1920, 1080, None),
    "discord": ("디스코드 음성", "", 360, 800, (24, 120, 360, 800)),
}
_QUERY = re.compile(r"^[A-Za-z0-9_=&%.,:\-]*$")
_STREAMKIT = re.compile(r"^https://streamkit\.discord\.com/overlay/voice/\d{5,25}/\d{5,25}(\?[A-Za-z0-9_=&%.\-]*)?$")


class ObsAddError(feature.FeatureError):
    pass


def explain(error: Exception) -> str:
    """OBS 연결 오류를 처음 쓰는 사람이 할 일로."""
    text = str(error)
    lower = text.lower()
    if "auth" in lower or "password" in lower or "4009" in text or "비밀번호" in text:
        return "OBS WebSocket 비밀번호가 맞지 않음: OBS 도구 메뉴의 WebSocket 서버 설정에서 비밀번호를 확인해 설정 마법사의 OBS 장면 단계에 입력"
    if any(word in lower for word in ("refused", "connect", "reach", "running", "timed out", "unreachable", "10061")) or isinstance(error, (ConnectionError, TimeoutError, OSError)):
        return "OBS에 연결하지 못함: OBS를 켜고 도구 메뉴의 WebSocket 서버 설정에서 서버 사용을 켜기(포트 4455)"
    return f"OBS에 넣지 못함: {text}"


def place(box: tuple[int, int, int, int] | None, width: int, height: int) -> dict[str, Any]:
    from ..scenes import _bounds

    x, y, w, h = box or (0, 0, 1920, 1080)
    return _bounds(x * width / 1920, y * height / 1080, w * width / 1920, h * height / 1080)


def add(client: Any, kind: str, base: str, *, query: str = "", url: str = "", css: str = "") -> dict[str, Any]:
    """소스를 만들거나 맞추고 지금 장면에 넣는다. 돌려주는 값: 소스 이름, 장면, 새로 만들었는지."""
    name, path, width, height, box = SOURCES[kind]
    if kind == "discord":
        if not _STREAMKIT.match(url):
            raise ObsAddError("디스코드 음성 위젯 주소는 https://streamkit.discord.com/overlay/voice/서버/채널 형식")
        address = url
    else:
        if not _QUERY.match(query):
            raise ObsAddError("주소 뒤 설정 값에 쓸 수 없는 글자")
        joiner = "&" if "?" in path else "?"
        address = f"{base}{path}{joiner + query if query else ''}"
    source = PREFIX + name
    kinds = client.request("GetInputKindList", {"unversioned": False}).get("inputKinds", [])
    if "browser_source" not in kinds:
        raise ObsAddError("이 OBS에는 브라우저 소스가 없음(OBS 설치 상태 확인)")
    current = client.request("GetCurrentProgramScene")
    scene = str(current.get("sceneName") or current.get("currentProgramSceneName") or "")
    if not scene:
        raise ObsAddError("OBS의 지금 장면을 알 수 없음")
    video = client.request("GetVideoSettings")
    canvas_w, canvas_h = int(video.get("baseWidth", 1920)), int(video.get("baseHeight", 1080))
    settings = {"url": address, "width": width, "height": height, "reroute_audio": kind in ("alerts", "draw", "pick", "race"), "shutdown": False}
    if css:
        settings["css"] = css
    exists = source in {str(item.get("inputName")) for item in client.request("GetInputList").get("inputs", [])}
    if exists:
        client.request("SetInputSettings", {"inputName": source, "inputSettings": settings, "overlay": True})
    items = client.request("GetSceneItemList", {"sceneName": scene}).get("sceneItems", [])
    found = next((item for item in items if str(item.get("sourceName")) == source), None)
    if found is None:
        if exists:
            item_id = client.request("CreateSceneItem", {"sceneName": scene, "sourceName": source})["sceneItemId"]
        else:
            item_id = client.request("CreateInput", {"sceneName": scene, "inputName": source, "inputKind": "browser_source",
                                                     "inputSettings": settings, "sceneItemEnabled": True})["sceneItemId"]
        client.request("SetSceneItemTransform", {"sceneName": scene, "sceneItemId": item_id, "sceneItemTransform": place(box, canvas_w, canvas_h)})
    elif not found.get("sceneItemEnabled", True):
        client.request("SetSceneItemEnabled", {"sceneName": scene, "sceneItemId": found["sceneItemId"], "sceneItemEnabled": True})
    if settings["reroute_audio"]:
        # 소리 나는 화면(알림 효과음 등): OBS 오디오로 보내고 스트리머도 들리게(모니터와 출력). 초보자가 가장 많이 막히는 단계
        try:
            client.request("SetInputAudioMonitorType", {"inputName": source, "monitorType": "OBS_MONITORING_TYPE_MONITOR_AND_OUTPUT"})
        except Exception:
            pass
    return {"source": source, "scene": scene, "created": not exists, "added": found is None, "url": address}


def check(client: Any) -> dict[str, Any]:
    """OBS 연결 확인: 지금 장면과 그 장면에 들어 있는 debutkit 화면."""
    current = client.request("GetCurrentProgramScene")
    scene = str(current.get("sceneName") or current.get("currentProgramSceneName") or "")
    names = {str(item.get("sourceName")) for item in client.request("GetSceneItemList", {"sceneName": scene}).get("sceneItems", [])} if scene else set()
    inside = [kind for kind, (name, *_rest) in SOURCES.items() if PREFIX + name in names]
    if PREFIX + "채팅 (게임 배치)" in names and "chat" not in inside:
        inside.append("chat")
    # 알림 소리: OBS로 오디오 보내기를 켠 알림 소스가 음소거가 아니고 모니터링(모니터와 출력)인지
    sound: dict[str, Any] = {"exists": False, "ok": False, "muted": False, "monitor": ""}
    alerts = PREFIX + SOURCES["alerts"][0]
    if alerts in {str(item.get("inputName")) for item in client.request("GetInputList").get("inputs", [])}:
        try:
            monitor = str(client.request("GetInputAudioMonitorType", {"inputName": alerts}).get("monitorType") or "")
            muted = bool(client.request("GetInputMute", {"inputName": alerts}).get("inputMuted"))
        except Exception:  # OBS로 오디오 보내기를 끈 브라우저 소스는 오디오 입력이 아님
            monitor, muted = "", False
        sound = {"exists": True, "monitor": monitor, "muted": muted, "ok": monitor == "OBS_MONITORING_TYPE_MONITOR_AND_OUTPUT" and not muted}
    return {"connected": True, "scene": scene, "inside": inside, "alerts_sound": sound}


def make_feature(context: feature.Context, *, connect: Callable[..., Any] | None = None) -> feature.Feature:
    def opener() -> Any:
        target = context.obs()
        if not target:
            raise ObsAddError("OBS 연결 정보 없음: 설정 마법사로 오버레이를 켜거나 debutkit overlay를 다시 실행")
        if connect is not None:
            return connect(*target)
        from ..camera import connect as camera_connect

        return camera_connect(*target)

    def run(data: dict[str, Any]) -> dict[str, Any]:
        kind = str(data.get("kind") or "")
        if kind not in SOURCES:
            raise ObsAddError("넣을 수 있는 화면: " + ", ".join(SOURCES))
        base = f"http://127.0.0.1:{context.port_of()}"
        try:
            with opener() as client:
                done = add(client, kind, base, query=str(data.get("query") or ""), url=str(data.get("url") or ""), css=str(data.get("css") or "")[:200000])
        except feature.FeatureError:
            raise
        except Exception as error:  # OBS 연결 실패, 비밀번호, 채팅 연결 모듈 없음
            raise ObsAddError(explain(error)) from None
        cache["value"] = None  # 시작하기 목록이 바로 다시 확인하도록
        verb = "새로 만들어" if done["created"] else "주소를 맞추고"
        where = f"{done['scene']} 장면에 넣음" if done["added"] else f"{done['scene']} 장면에 이미 있음"
        return {**done, "message": f"OBS {done['source']}: {verb} {where}"}

    cache: dict[str, Any] = {"at": 0.0, "value": None}

    def status(query: Any) -> dict[str, Any]:
        """OBS에 연결해 확인(5초 동안 기억). 실패하면 할 일을 알려 줌."""
        import time

        if not context.obs():
            return {"ready": False, "connected": False, "error": "OBS 연결 정보 없음: 설정 마법사로 오버레이를 켜거나 debutkit overlay를 다시 실행"}
        fresh = query.get("fresh", ["0"])[0] == "1" if isinstance(query, dict) else False
        if cache["value"] is not None and time.monotonic() - cache["at"] < 5 and not fresh:
            return cache["value"]
        try:
            with opener() as client:
                value = {"ready": True, **check(client)}
        except feature.FeatureError as error:
            value = {"ready": True, "connected": False, "error": str(error)}
        except Exception as error:
            value = {"ready": True, "connected": False, "error": explain(error)}
        cache.update(at=time.monotonic(), value=value)
        return value

    return feature.Feature(name="obs-add", get={"/obs/status": status}, post={"/obs/add": run},
                           body_limit={"/obs/add": 262144})
