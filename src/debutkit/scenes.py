"""OBS 장면 세트: 버튜버 방송에 필요한 기본 장면 5종을 obs-websocket으로 만든다.

``build_scenes`` 는 화면 크기와 OBS가 가진 소스 종류만 보고 장면 설계도를 만드는 순수
함수이고, ``apply`` 가 그 설계도를 OBS에 요청으로 보낸다. 이미 있는 장면은 건드리지
않으므로(``replace=True`` 제외) 쓰던 장면 모음에서 실행해도 안전하다. 처음에는 OBS 장면
모음 메뉴에서 새 장면 모음을 만든 뒤 실행하기를 권한다.

OBS 연결은 채팅 연결 모듈의 ``ObsClient`` 를 쓴다(``pip install "debutkit[live]"``).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Iterable

PREFIX = "[DK] "  # debutkit이 만든 소스 이름 앞에 붙는 표시

#: 역할별 OBS 소스 종류 후보. 앞에 있는 것부터, OBS가 가진 첫 종류를 쓴다
KIND_CANDIDATES: dict[str, tuple[str, ...]] = {
    "color": ("color_source_v3", "color_source_v2", "color_source"),
    "text": ("text_gdiplus_v3", "text_gdiplus_v2", "text_gdiplus", "text_ft2_source_v2", "text_ft2_source"),
    "browser": ("browser_source",),
    "game": ("game_capture", "screen_capture", "display_capture", "pipewire-screen-capture-source", "xshm_input_v2", "xshm_input", "monitor_capture"),
    "window": ("game_capture", "window_capture", "screen_capture", "xcomposite_input", "pipewire-window-capture-source"),
}

#: 아바타 프로그램별 창 지정 문자열(OBS 형식 "창 제목:창 클래스:실행 파일"). 버전에 따라 다를 수 있다
AVATAR_WINDOWS = {
    "vts": ("VTube Studio", "VTube Studio:UnityWndClass:VTube Studio.exe"),
    "vseeface": ("VSeeFace", "VSeeFace:UnityWndClass:VSeeFace.exe"),
    "warudo": ("Warudo", "Warudo:UnityWndClass:Warudo.exe"),
    "vmagicmirror": ("VMagicMirror", "VMagicMirror:UnityWndClass:VMagicMirror.exe"),
}

FONTS = {"Windows": "Malgun Gothic", "Darwin": "Apple SD Gothic Neo", "Linux": "Noto Sans CJK KR"}


@dataclass(frozen=True)
class SceneOptions:
    overlay_url: str = "http://127.0.0.1:8790/chat"
    alerts_url: str = "http://127.0.0.1:8790/alerts"
    character_url: str = "http://127.0.0.1:8790/character"
    draw_url: str = "http://127.0.0.1:8790/draw"
    #: 방송 연출(뽑기판, 후원 벽, 참여 레이스). 본방송과 토크 장면에 숨긴 채로 넣고 필요할 때 OBS에서 켠다
    pick_url: str = "http://127.0.0.1:8790/pick"
    wall_url: str = "http://127.0.0.1:8790/wall"
    race_url: str = "http://127.0.0.1:8790/race"
    goal_url: str = "http://127.0.0.1:8790/wall/goal"
    rank_url: str = "http://127.0.0.1:8790/wall/rank"
    frame_url: str = "http://127.0.0.1:8790/frame"
    #: 게임 패키지(overlay/games.py의 이름): 그 게임의 HUD(미니맵, 킬 로그 등)를 피한 자리에 캐릭터, 채팅, 목표 게이지, 순위를 놓고 프레임을 넣음
    game: str = ""
    #: 프레임(캐릭터 테두리, 대기, 자리 비움, 엔딩 화면). 게임 패키지를 고르면 함께 켬
    frames: bool = False
    avatar: str = "vts"  # vts | vseeface | warudo | vmagicmirror | debutkit(캐릭터 화면) | none
    background: int = 0xFF3D1F2A  # OBS 색은 ABGR 순서: 짙은 남보라
    os_name: str = field(default_factory=lambda: {"win32": "Windows", "darwin": "Darwin"}.get(sys.platform, "Linux"))
    starting_text: str = "곧 방송을 시작합니다"
    brb_text: str = "잠시 자리를 비웠습니다"
    ending_text: str = "시청해 주셔서 감사합니다"


@dataclass(frozen=True)
class Item:
    """장면 안의 소스 하나. ``source`` 가 OBS 전체에서 이미 있으면 새로 만들지 않고 장면에 추가만 한다."""

    source: str
    role: str  # KIND_CANDIDATES의 키
    settings: dict[str, Any]
    transform: dict[str, Any]
    enabled: bool = True  # False면 장면에 넣되 숨김(OBS 소스 목록의 눈 아이콘으로 켬)


@dataclass(frozen=True)
class Scene:
    name: str
    purpose: str
    items: tuple[Item, ...]


def resolve_kinds(available: Iterable[str]) -> dict[str, str]:
    """역할별로 OBS가 가진 첫 소스 종류. 없는 역할은 빠진다."""
    have = set(available)
    return {role: next(kind for kind in candidates if kind in have) for role, candidates in KIND_CANDIDATES.items() if any(kind in have for kind in candidates)}


def default_kinds(os_name: str) -> dict[str, str]:
    """OBS에 연결하지 않고 설계도만 볼 때(--dry-run) 쓰는 종류."""
    if os_name == "Windows":
        return {"color": "color_source_v3", "text": "text_gdiplus_v3", "browser": "browser_source", "game": "game_capture", "window": "game_capture"}
    if os_name == "Darwin":
        return {"color": "color_source_v3", "text": "text_ft2_source_v2", "browser": "browser_source", "game": "screen_capture", "window": "screen_capture"}
    return {"color": "color_source_v3", "text": "text_ft2_source_v2", "browser": "browser_source", "game": "pipewire-screen-capture-source",
            "window": "xcomposite_input"}


def _bounds(x: float, y: float, w: float, h: float, *, alignment: int = 5) -> dict[str, Any]:
    """(x, y)에 ``alignment`` 기준점을 두고 w x h 상자 안에 비율을 유지해 맞춘다. 5 = 왼쪽 위, 0 = 가운데, 9 = 왼쪽 아래."""
    return {"positionX": round(x), "positionY": round(y), "alignment": alignment, "boundsType": "OBS_BOUNDS_SCALE_INNER",
            "boundsWidth": max(1, round(w)), "boundsHeight": max(1, round(h)), "boundsAlignment": 0}


def _text_settings(kind: str, text: str, size: int, font: str) -> dict[str, Any]:
    if kind.startswith("text_gdiplus"):
        return {"text": text, "font": {"face": font, "size": size, "style": "Bold", "flags": 1}, "color": 0xFFFFFFFF, "align": "center",
                "outline": True, "outline_size": max(2, size // 18), "outline_color": 0xFF000000}
    return {"text": text, "font": {"face": font, "size": size, "style": "Bold", "flags": 1}, "color1": 0xFFFFFFFF, "color2": 0xFFFFFFFF,
            "outline": True, "drop_shadow": True}


def _avatar_item(options: SceneOptions, kinds: dict[str, str], box: dict[str, Any]) -> Item | None:
    if options.avatar == "none":
        return None
    if options.avatar == "debutkit":  # debutkit 캐릭터 화면(PNGTuber, VRM): 브라우저 소스, 투명 배경
        if "browser" not in kinds:
            return None
        settings_ = {"url": options.character_url, "width": round(box["boundsWidth"]), "height": round(box["boundsHeight"]), "shutdown": False,
                     "reroute_audio": False, "fps_custom": True, "fps": 30}
        return Item(f"{PREFIX}캐릭터", "browser", settings_, box)
    if "window" not in kinds:
        return None
    title, window = AVATAR_WINDOWS.get(options.avatar, AVATAR_WINDOWS["vts"])
    kind = kinds["window"]
    if kind == "game_capture":  # Windows: 투명 배경을 살리는 방법 (VTube Studio, VSeeFace 공식 안내)
        settings: dict[str, Any] = {"capture_mode": "window", "window": window, "allow_transparency": True}
    elif kind == "window_capture":
        settings = {"window": window}
    else:  # macOS, Linux: 창은 OBS에서 직접 고른다
        settings = {}
    return Item(f"{PREFIX}아바타 ({title})", "window", settings, box)


def build_scenes(width: int, height: int, kinds: dict[str, str], options: SceneOptions | None = None) -> list[Scene]:
    """장면 5종의 설계도. 소스는 아래에서 위 순서(먼저 만든 것이 뒤에 깔린다)."""
    options = options or SceneOptions()
    W, H = width, height
    from .overlay import games as game_packs

    spots = game_packs.layout(options.game) if options.game else None
    framed = options.frames or spots is not None

    def spot(name: str) -> dict[str, Any] | None:
        """게임 패키지의 자리(1920x1080 기준)를 이 캔버스 크기로."""
        if spots is None:
            return None
        x, y, w, h = spots[name]
        return _bounds(x * W / 1920, y * H / 1080, w * W / 1920, h * H / 1080)
    margin = round(H * 0.03)
    chat_w = round(W * 0.22)
    font = FONTS.get(options.os_name, FONTS["Linux"])
    text_size = round(H * 0.065)

    def background() -> Item | None:
        if "color" not in kinds:
            return None
        return Item(f"{PREFIX}배경", "color", {"color": options.background, "width": W, "height": H}, _bounds(0, 0, W, H))

    def chat(in_game: bool = False) -> Item | None:
        """채팅창. 게임 장면(``in_game``)에서만 게임 패키지 자리, 나머지 장면은 오른쪽 세로 전체.

        OBS 소스 하나를 여러 장면이 함께 쓰므로 자리는 장면마다(장면 안 항목의 변환) 다르다."""
        if "browser" not in kinds:
            return None
        placed = spot("chat") if in_game else None
        box = placed or _bounds(W - chat_w - margin, margin, chat_w, H - 2 * margin)
        settings = {"url": options.overlay_url, "width": round(box["boundsWidth"]), "height": round(box["boundsHeight"]), "fps_custom": False,
                    "reroute_audio": False, "shutdown": False, "restart_when_active": False}
        # 브라우저 소스의 화면 크기는 소스마다 하나: 게임 배치의 채팅은 크기가 달라 따로 만든다
        return Item(f"{PREFIX}채팅 (게임 배치)" if placed else f"{PREFIX}채팅", "browser", settings, box)

    def alerts() -> Item | None:
        if "browser" not in kinds:
            return None
        settings = {"url": options.alerts_url, "width": W, "height": H, "reroute_audio": True, "shutdown": False}
        return Item(f"{PREFIX}후원 알림", "browser", settings, _bounds(0, 0, W, H))

    def draws() -> Item | None:  # 후원 추첨 연출: 평소 투명, 추첨 결과가 올 때만 표시
        if "browser" not in kinds:
            return None
        settings = {"url": options.draw_url, "width": W, "height": H, "reroute_audio": False, "shutdown": False}
        return Item(f"{PREFIX}후원 추첨", "browser", settings, _bounds(0, 0, W, H))

    def stage(name: str, url: str, size: tuple[int, int] = (1920, 1080), box: tuple[float, float, float, float] = (0, 0, 1, 1)) -> Item | None:
        """방송 연출: 숨긴 채로 넣고 필요할 때 OBS에서 켠다. 숨긴 동안은 브라우저를 멈춰 연결과 그리기를 쉰다(켜면 서버의 지금 상태로 다시 그림).

        ``size`` 는 화면이 설계된 크기, ``box`` 는 놓을 자리(캔버스 비율: 왼쪽, 위, 가로, 세로)."""
        if "browser" not in kinds:
            return None
        settings = {"url": url, "width": size[0], "height": size[1], "reroute_audio": True, "shutdown": True}
        x, y, w, h = box
        return Item(f"{PREFIX}{name}", "browser", settings, _bounds(W * x, H * y, W * w, H * h), enabled=False)

    def wall() -> Item | None:  # 후원 벽은 벽지처럼 캐릭터 뒤에
        return stage("후원 벽", options.wall_url)

    def stages(in_game: bool = False) -> tuple[Item | None, ...]:
        """캐릭터 앞의 연출. 목표 게이지는 왼쪽 위(알림이 뜨는 가운데 위와 겹치지 않게), 순위는 그 아래 왼쪽. 게임 장면은 게임 패키지의 HUD를 피한 자리"""
        goal, rank = (0.017, 0.022, 0.3, 0.1), (0.017, 0.14, 0.15, 0.36)
        if spots is not None and in_game:
            goal = tuple(value / size for value, size in zip(spots["goal"], (1920, 1080, 1920, 1080), strict=True))  # type: ignore[assignment]
            rank = tuple(value / size for value, size in zip(spots["rank"], (1920, 1080, 1920, 1080), strict=True))  # type: ignore[assignment]
        return (stage("뽑기판", options.pick_url), stage("참여 레이스", options.race_url),
                stage("목표 게이지", options.goal_url, (1280, 240), goal), stage("후원 순위", options.rank_url, (560, 720), rank))

    def frame(name: str, kind: str, box: dict[str, Any] | None = None) -> Item | None:
        """프레임(/frame): 캐릭터 테두리는 캐릭터 위에, 대기, 자리 비움, 엔딩 화면은 안내 문구 대신 화면 전체에."""
        if not framed or "browser" not in kinds:
            return None
        box = box or _bounds(0, 0, W, H)
        settings = {"url": f"{options.frame_url}?kind={kind}", "width": round(box["boundsWidth"]), "height": round(box["boundsHeight"]),
                    "reroute_audio": False, "shutdown": True}
        return Item(f"{PREFIX}{name}", "browser", settings, box)

    def screen(name: str, kind: str, text_name: str, text: str) -> Item | None:
        return frame(name, kind) if framed and "browser" in kinds else caption(text_name, text)

    def caption(name: str, text: str) -> Item | None:
        if "text" not in kinds:
            return None
        return Item(f"{PREFIX}{name}", "text", _text_settings(kinds["text"], text, text_size, font),
                    _bounds((W - chat_w - margin) / 2, H / 2, W * 0.6, text_size * 2.5, alignment=0))

    def game() -> Item | None:
        if "game" not in kinds:
            return None
        settings = {"capture_mode": "any_fullscreen"} if kinds["game"] == "game_capture" else {}
        return Item(f"{PREFIX}게임 화면", "game", settings, _bounds(0, 0, W, H))

    # 본방송: 게임 위 왼쪽 아래에 아바타, 오른쪽에 채팅(게임 패키지는 그 게임의 HUD를 피한 자리)
    main_box = spot("character") or _bounds(0, H, W * 0.32, H * 0.62, alignment=9)
    main_avatar = _avatar_item(options, kinds, main_box)
    cam_box = spot("character") or _bounds(0, H - H * 0.62, W * 0.32, H * 0.62)
    cam_frame = frame("캐릭터 프레임", "cam", cam_box) if main_avatar is not None else None
    # 토크: 아바타를 크게 가운데에
    talk_avatar = _avatar_item(options, kinds, _bounds((W - chat_w - margin) / 2, H, W * 0.6, H * 0.95, alignment=8))

    def scene(name: str, purpose: str, *items: Item | None) -> Scene:
        return Scene(name, purpose, tuple(item for item in items if item is not None))

    return [
        scene("대기 화면", "방송 시작 전 대기. 안내 문구와 채팅", background(), screen("대기 화면 프레임", "starting", "대기 문구", options.starting_text),
              chat(), alerts(), draws()),
        scene("본방송", "게임 화면, 아바타, 채팅, 후원 알림과 추첨", background(), game(), wall(), main_avatar, cam_frame, *stages(in_game=True),
              chat(in_game=True), alerts(), draws()),
        scene("토크", "잡담, 노래. 아바타 크게 표시", background(), wall(), talk_avatar, *stages(), chat(), alerts(), draws()),
        scene("자리 비움", "휴식 시간. 마이크는 직접 음소거", background(), screen("자리 비움 프레임", "brb", "자리 비움 문구", options.brb_text),
              chat(), alerts(), draws()),
        scene("엔딩", "방송 마무리", background(), screen("엔딩 프레임", "ending", "엔딩 문구", options.ending_text), chat()),
    ]


@dataclass
class Report:
    created_scenes: list[str] = field(default_factory=list)
    skipped_scenes: list[str] = field(default_factory=list)
    created_sources: list[str] = field(default_factory=list)
    reused_sources: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def apply(client: Any, scenes: list[Scene], kinds: dict[str, str], *, replace: bool = False, switch_to: str | None = None) -> Report:
    """설계도를 OBS에 만든다. ``client`` 는 ``request(type, data) -> dict`` 를 가진 객체(stream2clip ``ObsClient``)."""
    report = Report()
    existing_scenes = {scene["sceneName"] for scene in client.request("GetSceneList").get("scenes", [])}
    existing_inputs = {source["inputName"] for source in client.request("GetInputList").get("inputs", [])}
    for scene in scenes:
        if scene.name in existing_scenes:
            if not replace:
                report.skipped_scenes.append(scene.name)
                continue
            client.request("RemoveScene", {"sceneName": scene.name})
        client.request("CreateScene", {"sceneName": scene.name})
        report.created_scenes.append(scene.name)
        for item in scene.items:
            if item.source in existing_inputs:
                item_id = client.request("CreateSceneItem", {"sceneName": scene.name, "sourceName": item.source,
                                                             "sceneItemEnabled": item.enabled})["sceneItemId"]
                if item.source not in report.created_sources and item.source not in report.reused_sources:
                    report.reused_sources.append(item.source)
            else:
                item_id = client.request("CreateInput", {"sceneName": scene.name, "inputName": item.source, "inputKind": kinds[item.role],
                                                         "inputSettings": item.settings, "sceneItemEnabled": item.enabled})["sceneItemId"]
                existing_inputs.add(item.source)
                report.created_sources.append(item.source)
            client.request("SetSceneItemTransform", {"sceneName": scene.name, "sceneItemId": item_id, "sceneItemTransform": item.transform})
    if switch_to:
        client.request("SetCurrentProgramScene", {"sceneName": switch_to})
    if any(item.role == "window" for scene in scenes for item in scene.items) and kinds.get("window") != "game_capture":
        report.notes.append("아바타 소스: OBS에서 속성을 열어 아바타 프로그램 창 직접 선택")
    return report


NOT_AVAILABLE = 604  # obs-websocket RequestStatus::InvalidResourceState 계열: 리플레이 버퍼 출력이 아직 없음


def enable_replay_buffer(client: Any, seconds: int = 60) -> tuple[bool, str]:
    """OBS 설정의 리플레이 버퍼를 켜고 길이를 정한 뒤, 가능하면 시작한다(자동 클립에 필요).

    OBS 설정 출력 탭의 단순 모드와 고급 모드는 저장 위치가 달라 현재 모드를 먼저 읽는다. 설정을
    처음 켠 경우 OBS는 재시작해야 리플레이 버퍼를 만든다(OBS 33에서 확인). 그때는 ``(False, 안내)``.
    """
    from stream2clip.obs import ObsError

    mode = str(client.request("GetProfileParameter", {"parameterCategory": "Output", "parameterName": "Mode"}).get("parameterValue") or "Simple")
    category = "AdvOut" if mode.lower().startswith("adv") else "SimpleOutput"
    client.request("SetProfileParameter", {"parameterCategory": category, "parameterName": "RecRB", "parameterValue": "true"})
    client.request("SetProfileParameter", {"parameterCategory": category, "parameterName": "RecRBTime", "parameterValue": str(int(seconds))})
    try:
        if client.request("GetReplayBufferStatus").get("outputActive"):
            return True, f"리플레이 버퍼 실행 중 (길이 {seconds}초는 다음 시작부터 적용)"
        client.request("StartReplayBuffer")
    except ObsError as error:
        if getattr(error, "code", None) == NOT_AVAILABLE:
            return False, f"리플레이 버퍼 설정 완료(최대 {seconds}초). OBS 재시작 후 사용 가능"
        raise
    return True, f"리플레이 버퍼 시작 (최대 {seconds}초)"


def connect_and_apply(host: str, port: int, password: str | None, options: SceneOptions, *, replace: bool = False, switch: bool = False,
                      replay_buffer: int | None = None) -> tuple[Report, list[Scene]]:
    """OBS에 연결해 장면을 만든다. ``replay_buffer`` 초를 주면 자동 클립용 리플레이 버퍼도 켠다."""
    try:
        from stream2clip.obs import ObsClient, ObsError
    except ImportError as error:
        raise RuntimeError('OBS 연결에는 채팅 연결 모듈 필요: pip install "debutkit[live]"') from error
    with ObsClient(host, port, password, events=0) as client:
        video = client.request("GetVideoSettings")
        kinds = resolve_kinds(client.request("GetInputKindList", {"unversioned": False}).get("inputKinds", []))
        scenes = build_scenes(int(video.get("baseWidth", 1920)), int(video.get("baseHeight", 1080)), kinds, options)
        report = apply(client, scenes, kinds, replace=replace, switch_to=scenes[0].name if switch else None)
        if options.avatar not in ("none", "debutkit") and "window" not in kinds:
            report.notes.append("이 OBS에는 창 캡처 소스가 없어 아바타 소스 생략. OBS에서 아바타 프로그램 창 캡처를 직접 추가 필요")
        if replay_buffer:
            try:
                report.notes.append(enable_replay_buffer(client, replay_buffer)[1])
            except ObsError as error:
                report.notes.append(f"리플레이 버퍼 켜기 실패: {error}. OBS 설정의 출력 탭에서 리플레이 버퍼 사용 직접 체크")
    return report, scenes


def format_plan(scenes: list[Scene], kinds: dict[str, str]) -> str:
    lines = []
    for scene in scenes:
        lines.append(f"[{scene.name}] {scene.purpose}")
        for item in scene.items:
            t = item.transform
            hidden = ", 숨김: 필요할 때 켜기" if not item.enabled else ""
            lines.append(f"    - {item.source}  ({kinds.get(item.role, '?')}, {t['boundsWidth']}x{t['boundsHeight']}{hidden})")
    return "\n".join(lines)


def format_report(report: Report) -> str:
    lines = []
    if report.created_scenes:
        lines.append("만든 장면: " + ", ".join(report.created_scenes))
    if report.skipped_scenes:
        lines.append("기존 장면이 있어 건너뜀: " + ", ".join(report.skipped_scenes) + " (--replace로 다시 생성)")
    if report.created_sources:
        lines.append("만든 소스: " + ", ".join(report.created_sources))
    if report.reused_sources:
        lines.append("기존 소스 재사용: " + ", ".join(report.reused_sources))
    lines += report.notes
    lines.append("채팅, 후원 알림 소스: debutkit overlay 실행 중에만 표시")
    return "\n".join(lines)
