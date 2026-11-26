"""게임 패키지(``/games``): 게임마다 어울리는 방송 스타일과 색, 게임 화면의 HUD(미니맵, 킬 로그, 체력과 스킬)를 피한 배치, 프레임.

- 패키지 하나 = 게임별 스타일(theme.GAME_LOOKS, 게임과 같은 이름) + 주 색과 강조 색 + 알림 위치 + 캐릭터, 채팅, 목표 게이지, 순위 자리
  + HUD 자리(미리보기용) + 그 게임 느낌의 배경 그림(``/games/scene/키.jpg``, 미리보기와 대기 화면)
- 배경 그림은 공개 모델 FLUX.1 schnell(Apache-2.0)로 만든 일러스트(packaging/build_game_art.py, 생성 기록은 games/scenes.json).
  게임 이름, 로고, 캐릭터 없이 장면만 묘사
- ``/games/preview?game=키`` 배경 그림 위에 실제 방송 화면(캐릭터 프레임, 채팅, 알림)을 패키지 배치로 겹친 미리보기.
  ``/games/thumb/키.jpg`` 는 그 미리보기를 찍어 둔 그림(packaging/build_game_previews.py)
- 게임 이름은 어떤 게임에 맞춘 배치인지 알리는 데만 쓴다. 게임 회사의 로고, 글꼴, 그림, 캐릭터는 쓰지 않으며 debutkit은 게임 회사와 관계없음
- ``/games`` 조회, ``POST /games/apply`` (``{"game": "valorant", "parts": ["style", "alerts", "layout"]}``),
  ``POST /games/frames`` 프레임 문구(이름표, 대기, 자리 비움, 엔딩 문구, 아래 한 줄, 대기 시간). ``/live?feeds=games`` 로 바뀐 값
- ``/frame?kind=cam|screen|starting|brb|ending`` 프레임 화면(frame.html). 장면 만들기(``debutkit scenes --game``)가 배치와 프레임을 씀
- 설정은 설정 폴더의 ``games.json`` (고른 게임, 프레임 문구)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .. import settings
from . import feature
from .alerts import _josa

DATA = "games.json"
Rect = tuple[int, int, int, int]  # 1920x1080 기준 왼쪽, 위, 가로, 세로


@dataclass(frozen=True)
class Game:
    name: str
    genre: str
    style: str  # theme.STYLES 이름
    primary: str
    highlight: str
    alert: str  # alerts.POSITIONS 이름
    character: Rect
    chat: Rect
    goal: Rect
    rank: Rect
    hud: tuple[tuple[str, Rect], ...]
    tips: tuple[str, ...]  # 배치 요약(항목)


#: 게임 패키지. HUD 자리는 1920x1080, 기본 HUD 설정 기준의 대략적인 자리(게임 설정에서 HUD 크기와 위치를 바꾸면 달라짐)
GAMES: dict[str, Game] = {
    "valorant": Game(
        "발로란트", "전술 FPS", "valorant", "#ff5160", "#2fd3c0", "left",
        character=(0, 680, 420, 400), chat=(1560, 370, 350, 310), goal=(10, 372, 410, 76), rank=(10, 456, 200, 220),
        hud=(("미니맵", (0, 0, 360, 360)), ("점수, 시간, 요원", (600, 0, 720, 120)), ("킬 로그", (1440, 40, 480, 320)),
             ("체력, 스킬, 탄약", (560, 940, 800, 140)), ("무기와 크레드", (1600, 700, 320, 380)), ("게임 채팅", (0, 560, 520, 300))),
        tips=("비우는 곳: 가운데 조준점, 위쪽 점수판, 아래 가운데 체력과 스킬", "캐릭터: 왼쪽 아래", "채팅: 오른쪽, 킬 로그 아래")),
    "lol": Game(
        "리그 오브 레전드", "판타지 AOS", "lol", "#19b8b0", "#c9a86a", "top",
        character=(90, 0, 420, 420), chat=(1610, 460, 300, 300), goal=(90, 430, 420, 78), rank=(90, 516, 200, 220),
        hud=(("미니맵", (1620, 780, 300, 300)), ("팀 점수와 시간", (1500, 0, 420, 40)), ("킬 알림", (1600, 120, 320, 330)),
             ("챔피언 정보와 스킬", (560, 900, 800, 180)), ("게임 채팅", (0, 740, 500, 220)), ("아군 초상", (0, 180, 90, 380))),
        tips=("비우는 곳: 오른쪽 아래 미니맵, 아래 가운데 챔피언 정보", "캐릭터: 왼쪽 위", "채팅: 오른쪽, 미니맵 위", "미니맵을 왼쪽으로 옮겼다면 좌우를 바꿈")),
    "overwatch": Game(
        "오버워치", "히어로 슈터", "overwatch", "#ff9c1f", "#3fc1f2", "left",
        character=(0, 0, 460, 440), chat=(1570, 360, 340, 400), goal=(10, 446, 440, 76), rank=(10, 530, 200, 200),
        hud=(("목표와 팀 정보", (560, 0, 800, 170)), ("킬 로그", (1440, 40, 480, 300)), ("체력", (0, 900, 520, 180)),
             ("스킬과 탄약", (1400, 880, 520, 200)), ("궁극기", (860, 880, 200, 170)), ("게임 채팅", (0, 560, 520, 320))),
        tips=("비우는 곳: 위쪽 목표, 아래 양쪽 체력과 스킬", "캐릭터: 왼쪽 위", "채팅: 오른쪽 가운데")),
    "hearthstone": Game(
        "하스스톤", "카드 게임", "hearthstone", "#2f7bd8", "#d4a84b", "top",
        character=(0, 700, 300, 380), chat=(1690, 40, 220, 560), goal=(10, 10, 230, 60), rank=(10, 80, 200, 220),
        hud=(("상대 영웅과 손패", (560, 0, 800, 220)), ("전장", (240, 230, 1440, 600)), ("내 영웅과 손패", (520, 840, 880, 240)),
             ("턴 종료 버튼", (1500, 470, 180, 110)), ("내 덱 추적기", (1690, 620, 230, 460)), ("상대 기록", (0, 260, 230, 420))),
        tips=("비우는 곳: 가운데 판(4:3)", "캐릭터: 왼쪽 아래", "채팅: 오른쪽 위", "덱 추적기를 쓰면 채팅 길이를 줄이기")),
    "pubg": Game(
        "배틀그라운드", "배틀로얄", "pubg", "#c9b48a", "#f2b400", "right",
        character=(0, 0, 460, 420), chat=(0, 430, 300, 330), goal=(1560, 380, 350, 72), rank=(1560, 460, 200, 220),
        hud=(("나침반", (660, 0, 600, 80)), ("생존 인원과 킬 로그", (1500, 0, 420, 360)), ("미니맵", (1640, 800, 280, 280)),
             ("체력과 무기", (600, 940, 720, 140)), ("팀원 목록", (0, 820, 360, 220))),
        tips=("비우는 곳: 위쪽 나침반, 오른쪽 아래 미니맵, 아래 가운데 체력", "캐릭터: 왼쪽 위", "채팅: 왼쪽 가운데")),
    "maplestory": Game(
        "메이플스토리", "캐주얼 RPG", "maplestory", "#4fb3ef", "#ffd45c", "top",
        character=(1560, 520, 360, 400), chat=(0, 280, 340, 400), goal=(0, 690, 340, 64), rank=(380, 280, 200, 220),
        hud=(("미니맵", (0, 0, 360, 260)), ("버프", (1480, 0, 440, 90)), ("퀘스트 도우미", (1660, 200, 260, 320)),
             ("게임 채팅", (0, 760, 560, 200)), ("상태 막대와 퀵슬롯", (0, 960, 1920, 120))),
        tips=("비우는 곳: 왼쪽 위 미니맵, 맨 아래 상태 막대", "캐릭터: 오른쪽 가운데", "채팅: 왼쪽, 미니맵 아래")),
    "lostark": Game(
        "로스트아크", "다크 판타지 RPG", "lostark", "#f99200", "#c9a063", "top",
        character=(0, 0, 420, 300), chat=(1600, 640, 310, 260), goal=(0, 610, 420, 76), rank=(0, 694, 200, 200),
        hud=(("미니맵과 퀘스트 추적", (1620, 0, 300, 620)), ("우두머리 체력", (560, 30, 800, 80)), ("파티 정보", (0, 300, 260, 300)),
             ("스킬과 체력", (560, 900, 800, 180)), ("게임 채팅", (0, 760, 500, 220))),
        tips=("비우는 곳: 오른쪽 위 미니맵, 아래 가운데 스킬, 왼쪽 파티 정보", "캐릭터: 왼쪽 위", "채팅: 오른쪽 아래")),
    "fconline": Game(
        "FC 온라인", "축구 게임", "fconline", "#3ba55c", "#f4f2ec", "top",
        character=(1480, 0, 440, 420), chat=(1560, 430, 350, 420), goal=(10, 110, 440, 76), rank=(10, 194, 200, 220),
        hud=(("점수와 시간", (0, 0, 450, 100)), ("레이더", (760, 900, 400, 180)), ("선수 이름", (40, 960, 500, 90))),
        tips=("비우는 곳: 왼쪽 위 점수, 아래 가운데 레이더", "캐릭터: 오른쪽 위", "채팅: 오른쪽, 캐릭터 아래")),
    "tft": Game(
        "전략적 팀 전투", "오토 배틀러", "tft", "#8b5cd6", "#c89b3c", "top",
        character=(1500, 770, 420, 310), chat=(0, 0, 400, 170), goal=(410, 0, 280, 60), rank=(1500, 560, 170, 200),
        hud=(("시너지", (0, 180, 260, 540)), ("전장", (400, 150, 1120, 610)), ("대기석과 상점", (420, 760, 1080, 320)),
             ("플레이어 목록", (1680, 130, 240, 630)), ("단계 표시", (700, 0, 520, 60))),
        tips=("비우는 곳: 가운데 전장, 아래 상점, 오른쪽 플레이어 목록", "캐릭터: 오른쪽 아래", "채팅: 왼쪽 위")),
    "minecraft": Game(
        "마인크래프트", "샌드박스", "minecraft", "#5d9c3a", "#f2c94c", "top",
        character=(1500, 640, 420, 440), chat=(0, 0, 380, 420), goal=(420, 10, 440, 76), rank=(0, 430, 200, 220),
        hud=(("단축 칸과 체력", (640, 900, 640, 180)), ("게임 채팅", (0, 640, 640, 320)), ("효과", (1660, 0, 260, 120)),
             ("서버 점수판", (1680, 360, 240, 320))),
        tips=("비우는 곳: 아래 가운데 단축 칸, 왼쪽 아래 게임 채팅", "캐릭터: 오른쪽 아래", "채팅: 왼쪽 위")),
}
GAME_PARTS = ("style", "alerts", "layout")
FRAME_KEYS = {"name": 30, "tag": 12, "starting": 40, "brb": 40, "ending": 40, "note": 60}
FRAME_DEFAULTS: dict[str, Any] = {"name": "", "tag": "", "starting": "", "brb": "", "ending": "", "note": "", "minutes": 0}


class GameError(feature.FeatureError):
    pass


def layout(key: str) -> dict[str, Rect] | None:
    """장면 만들기와 미리보기의 자리: 캐릭터, 채팅, 목표 게이지, 순위. 없는 게임이면 None(기본 배치)."""
    game = GAMES.get(key)
    if game is None:
        return None
    return {"character": game.character, "chat": game.chat, "goal": game.goal, "rank": game.rank}


def check_frames(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise GameError("프레임 설정 형식이 올바르지 않음")
    found = {}
    labels = {"name": "이름표", "tag": "머리표", "starting": "대기 문구", "brb": "자리 비움 문구", "ending": "엔딩 문구", "note": "아래 한 줄"}
    for key, limit in FRAME_KEYS.items():
        if key in data:
            text = " ".join(str(data[key] or "").split())
            if len(text) > limit:
                raise GameError(_josa(labels[key], "은", "는") + f" {limit}자 이내")
            found[key] = text
    if "minutes" in data:
        minutes = data["minutes"]
        if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or minutes != int(minutes) or not 0 <= minutes <= 120:
            raise GameError("대기 시간은 0에서 120분 사이의 정수(0은 표시 안 함)")
        found["minutes"] = int(minutes)
    return found


def load() -> dict[str, Any]:
    saved = settings.load_data(DATA)
    game = saved.get("game") if saved.get("game") in GAMES else ""
    frames = dict(FRAME_DEFAULTS)
    try:
        frames.update(check_frames(saved.get("frames") or {}))
    except GameError:
        pass
    return {"game": game, "frames": frames}


def _rect(rect: Rect) -> list[int]:
    return list(rect)


def catalog() -> dict[str, Any]:
    return {key: {"name": game.name, "genre": game.genre, "style": game.style, "primary": game.primary, "highlight": game.highlight,
                  "alert": game.alert, "character": _rect(game.character), "chat": _rect(game.chat), "goal": _rect(game.goal),
                  "rank": _rect(game.rank), "hud": [{"label": label, "rect": _rect(rect)} for label, rect in game.hud], "tips": list(game.tips),
                  "look": game.style}
            for key, game in GAMES.items()}


def make_feature(context: feature.Context, theme_part: feature.Feature, alerts_part: feature.Feature) -> feature.Feature:
    """``theme_part``, ``alerts_part`` 의 저장 처리를 그대로 불러 확인, 저장, 화면 반영을 한곳에서."""
    channel = feature.Channel({"seq": 0, **load()})

    def publish() -> dict[str, Any]:
        channel.publish({"seq": channel.current.get("seq", 0) + 1, **load()})
        return info()

    def info(_: Any = None) -> dict[str, Any]:
        return {**load(), "games": catalog(), "parts": list(GAME_PARTS)}

    def apply(data: dict[str, Any]) -> dict[str, Any]:
        key = data.get("game")
        if key == "":
            settings.save_data(DATA, {**load(), "game": ""})
            return publish()
        if key not in GAMES:
            raise GameError("없는 게임: " + ", ".join(GAMES))
        parts = data.get("parts", list(GAME_PARTS))
        if not isinstance(parts, list) or not parts or any(part not in GAME_PARTS for part in parts):
            raise GameError("적용할 항목은 style(방송 스타일과 색), alerts(알림 위치), layout(장면 배치) 중에서")
        game = GAMES[key]
        if "style" in parts:
            theme_part.post["/theme"]({"style": game.style, "primary": game.primary, "highlight": game.highlight})
        if "alerts" in parts:
            alerts_part.post["/alerts/config"]({"position": game.alert, "style": "auto", "enter": "auto"})
        settings.save_data(DATA, {**load(), "game": key})
        return publish()

    def save_frames(data: dict[str, Any]) -> dict[str, Any]:
        current = load()
        settings.save_data(DATA, {**current, "frames": {**current["frames"], **check_frames(data)}})
        return publish()

    static = {"/frame": "frame.html", "/frame.css": "frame.css", "/frame.js": "frame.js", "/games/look.css": "games/look.css",
              "/games/preview": "games/preview.html", "/games/preview.js": "games/preview.js", "/games/avatar.svg": "games/avatar.svg"}
    for key in GAMES:
        static[f"/games/scene/{key}.jpg"] = f"games/scene-{key}.jpg"
        static[f"/games/thumb/{key}.jpg"] = f"games/thumb-{key}.jpg"
    return feature.Feature(name="games", static=static,
                           get={"/games": info}, post={"/games/apply": apply, "/games/frames": save_frames}, feeds={"games": channel})
