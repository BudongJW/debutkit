"""뽑기판: 가려진 칸 여러 개 중 연 칸의 상품을 방송 화면(``/pick``)에 공개한다. 스트리머가 조작 화면에서 열거나 조건에 맞는 시청자가 연다.

- 판 설정: 제목, 설명, 칸 수(4에서 100), 열 수(자동 또는 지정), 상품과 수량(예: 노래 한 곡 2개). 남은 칸은 빈칸 이름(기본 꽝)
- 배치는 판을 만들거나 섞을 때 서버가 운영체제 난수(``random.SystemRandom``)로 정한다
- 비밀 유지: 방송 화면이 받는 실시간 항목(``/live?feeds=pick``)과 공개 조회(``/pick/state``, ``/pick/proof``)에는 열린 칸의 상품만 넣는다.
  전체 배치는 조작 화면 전용 조회(``/pick/secret``)로만. 남은 상품 요약은 켠 경우에만 이름과 개수(위치 없음)
- 공정성 확인: 배치마다 무작위 소금값(salt)과 배치로 만든 확인 문자열의 SHA-256을 판을 만들 때 공개하고, 판이 끝나면(모두 열기,
  끝내고 공개) 소금값과 배치를 공개한다. 확인 문자열의 SHA-256이 처음 공개한 값과 같은지 누구나 확인할 수 있다.
  다시 섞거나 상품을 바꾸면 새 배치와 새 값(지난 배치는 공개)
- 시청자 참여(선택): 채팅 ``!뽑기 7`` (번호 없으면 남은 칸 중 무작위) 또는 최소 금액 이상 후원(원 기준, 별풍선 1개 100원.
  후원 메시지의 번호, 없거나 이미 열렸으면 무작위). 열 수 있는 사람(모두, 후원자만, 스트리머와 매니저만), 시청자별 대기 시간과
  판마다 횟수 제한, 플랫폼 선택. 스트리머와 매니저는 대기 시간과 횟수 제한 없음
- 판 여러 개를 저장해 바꿔 가며 사용. 설정, 배치, 열린 칸, 기록은 ``pick.json`` (settings.save_data)에 저장해 화면을 새로 고치거나
  오버레이를 다시 시작해도 같은 판을 이어 간다(처음 실행 때 만든 예시 판은 처음 바꾸거나 열 때 저장)
- 다른 화면(휴대폰 조작 등)은 :class:`PickBoard` 의 ``open``, ``status``, ``undo`` 등을 그대로 쓰면 된다
"""

from __future__ import annotations

import colorsys
import hashlib
import hmac
import random
import re
import secrets
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable

from . import settings
from .draw import amount_text
from .overlay.events import OverlayEvent
from .overlay.feature import Channel, Context, Feature, FeatureError
from .vts import WON_PER_UNIT

DATA_FILE = "pick.json"
CELLS = (4, 100)
COLUMNS = (0, 20)  # 0은 자동
MAX_PRIZES = 30
MAX_COUNT = 100
MAX_NAME = 24
MAX_TITLE = 30
MAX_CAPTION = 80
MAX_CAPTION_LINES = 3
MAX_BOARDS = 12
MAX_BOARD_NAME = 20
MAX_BY = 40
MAX_LOG = 300
MAX_ROUNDS = 20
MAX_WON = 100_000_000
MAX_REPEAT = 10
SECONDS = (2, 30)
SCALE = (40, 130)
VOLUME = (0, 100)
COOLDOWN = (0, 3600)
PER_VIEWER = (0, 100)
DEFAULT_TITLE = "뽑기판"
DEFAULT_BLANK = "꽝"
DEFAULT_COMMAND = "!뽑기"
DEFAULT_BOARD = "기본 판"
#: 다른 채팅 명령(commands.py, 참여 추첨)과 겹치면 안 되는 명령
RESERVED_COMMANDS = ("!동작", "!단축키", "!모집", "!마감", "!추첨", "!순서", "!참가", "!clip")

INK = "#1e2327"
PAPER = "#faf7f5"
GOLD = "#ffd84d"
GOLD_DEEP = "#c9971c"
MISS = "#e6e1dc"
MUTED = "#5b6670"

PLATFORMS = {"chzzk": "치지직", "soop": "SOOP", "youtube": "YouTube", "twitch": "Twitch"}
THEMES = {"card": "카드 뒤집기", "ticket": "긁는 복권", "envelope": "봉투", "capsule": "캡슐", "door": "작은 문", "sticker": "스티커 떼기",
          "memo": "메모지"}
#: 테마 색: 하나를 고르면 덮개, 판 바탕, 글자, 당첨 띠 색을 맞춘다(직접 지정한 색이 우선)
#: channel(방송 색)은 설정 화면, 방송 화면 미리보기에서 고른 방송 색(overlay/theme.py)을 따른다
COLORS = {"channel": ("방송 색", "#ff4f8b"), "pink": ("핑크", "#ff4f8b"), "cherry": ("체리", "#e23b4e"), "tangerine": ("귤", "#ff7a2f"), "peach": ("복숭아", "#ffa48a"),
          "lime": ("라임", "#8cc63f"), "mint": ("민트", "#22b8a0"), "sky": ("하늘", "#47a8f5"), "navy": ("남색", "#2f4fbf"),
          "violet": ("보라", "#8a5cf5"), "lilac": ("라일락", "#c39bf0"), "cocoa": ("코코아", "#8a5a44"), "slate": ("먹", "#3a4249")}
COLOR_PARTS = {"cover": "덮개", "board": "판 바탕", "text": "글자", "win": "당첨 띠"}
COVERS = {"number": "큰 번호", "dots": "망점", "stripes": "사선", "check": "체크", "grid": "모눈", "stars": "별", "hearts": "하트",
          "waves": "물결", "question": "물음표", "emblem": "고양이 문양", "gift": "선물 포장"}
#: 함께 배포한 글꼴(Black Han Sans, Pretendard)과 Windows 기본 글꼴
FONTS = {"blackhan": "Black Han Sans", "pretendard": "Pretendard", "malgun": "맑은 고딕", "serif": "바탕(명조)"}
EFFECTS = {"confetti": "종이 조각", "stars": "별 터짐", "ribbons": "리본", "rays": "집중선", "coins": "동전 비", "hearts": "하트",
           "notes": "음표", "rings": "충격파", "sparkle": "반짝이", "pixels": "도트 조각", "random": "매번 무작위", "none": "없음"}
MISS_EFFECTS = {"dust": "먼지", "cloud": "먹구름", "none": "없음"}
WIN_SOUNDS = {"fanfare": "팡파르", "chime": "차임", "coin": "동전", "pop": "퐁"}
MISS_SOUNDS = {"boing": "뿅", "buzzer": "부저", "slide": "미끄럼"}
POSITIONS = {"center": "가운데", "left": "왼쪽", "right": "오른쪽"}
ALIGNS = {"left": "왼쪽", "center": "가운데", "right": "오른쪽"}
WHO = {"all": "모두(채팅 명령)", "donors": "후원자만(후원으로 열기)", "staff": "스트리머와 매니저만"}
SOURCES = {"control": "조작 화면", "chat": "채팅", "donation": "후원", "remote": "휴대폰", "api": "명령줄"}
#: 글자 모양: 부분 -> 항목 -> (최소, 최대). 크기는 1920x1080 기준 px(결과 카드는 %), 줄 간격은 %
STYLE_RANGES: dict[str, dict[str, tuple[int, int]]] = {"title": {"size": (24, 120), "line": (90, 200)},
                                                       "caption": {"size": (14, 72), "line": (100, 220)},
                                                       "result": {"size": (60, 160)}}
STYLE_NAMES = {"title": "제목", "caption": "설명", "result": "결과 카드"}
DEFAULT_STYLES: dict[str, dict[str, Any]] = {"title": {"size": 60, "color": "", "align": "center", "line": 110},
                                             "caption": {"size": 26, "color": "", "align": "center", "line": 140},
                                             "result": {"size": 100, "color": "", "align": "center"}}
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_NUMBER = re.compile(r"^[0-9]{1,3}$")


class PickError(FeatureError):
    """잘못된 뽑기판 요청. 메시지는 한국어 안내(기본 400, 없는 판은 404)."""


@dataclass(frozen=True)
class Prize:
    name: str
    count: int = 1
    rare: bool = False  # 금색 강조(희귀 상품)


@dataclass(frozen=True)
class Viewers:
    """시청자 참여. 꺼져 있으면 조작 화면(과 Python 호출)으로만 연다."""

    enabled: bool = False
    command: str = DEFAULT_COMMAND
    who: str = "all"
    donation_min: int | None = None  # 원 기준. None이면 후원으로 열지 않음(후원자만이면 필수)
    repeat: bool = False  # 최소 금액의 배수만큼 여러 칸(최대 MAX_REPEAT)
    cooldown: int = 30  # 같은 시청자의 채팅 명령 사이 대기(초)
    per_viewer: int = 0  # 판마다 시청자 한 명이 채팅으로 열 수 있는 칸(0은 제한 없음)
    platforms: tuple[str, ...] = tuple(PLATFORMS)

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "command": self.command, "who": self.who, "donation_min": self.donation_min, "repeat": self.repeat,
                "cooldown": self.cooldown, "per_viewer": self.per_viewer, "platforms": list(self.platforms)}


DEFAULT_PRIZES = (Prize("노래 한 곡", 2), Prize("성대모사", 2), Prize("애교 한 번", 3), Prize("소원 들어주기", 1, True))


@dataclass(frozen=True)
class Config:
    title: str = DEFAULT_TITLE
    caption: str = ""
    cells: int = 20
    columns: int = 0
    prizes: tuple[Prize, ...] = DEFAULT_PRIZES
    blank: str = DEFAULT_BLANK
    theme: str = "card"
    color: str = "channel"  # COLORS 이름(channel은 방송 색) 또는 #RRGGBB
    colors: dict[str, str] = field(default_factory=dict)  # 직접 지정한 색(COLOR_PARTS)
    cover: str = "number"
    font: str = "blackhan"
    styles: dict[str, dict[str, Any]] = field(default_factory=lambda: {part: dict(values) for part, values in DEFAULT_STYLES.items()})
    effect: str = "confetti"
    miss_effect: str = "dust"
    sound: bool = True
    volume: int = 70
    win_sound: str = "fanfare"
    miss_sound: str = "boing"
    seconds: int = 5  # 결과 카드 표시 시간
    position: str = "center"
    scale: int = 100
    frame: bool = True  # 판 바탕(끄면 칸만)
    show_numbers: bool = True
    show_remaining: bool = False  # 남은 상품 요약(이름과 개수만)
    show_hash: bool = True  # 공정성 확인 값
    show_help: bool = True  # 시청자 참여 안내(참여를 켠 경우)
    viewers: Viewers = Viewers()

    def tier(self, name: str) -> str:
        """칸 하나의 등급: miss(빈칸, 이름에 꽝), rare(금색 상품), win."""
        if name == self.blank or "꽝" in name:
            return "miss"
        return "rare" if any(prize.rare and prize.name == name for prize in self.prizes) else "win"

    def layout_key(self) -> tuple[Any, ...]:
        """배치를 바꾸는 설정(칸 수, 상품과 수량, 빈칸 이름)."""
        return self.cells, tuple((prize.name, prize.count) for prize in self.prizes), self.blank

    def display(self) -> dict[str, Any]:
        """방송 화면에 보내는 표시 설정(상품표는 넣지 않음)."""
        return {"title": self.title, "caption": self.caption, "cells": self.cells, "columns": self.columns, "theme": self.theme,
                "color": self.color, "palette": palette(self.color, self.colors), "cover": self.cover, "font": self.font,
                "styles": {part: dict(values) for part, values in self.styles.items()}, "effect": self.effect, "miss_effect": self.miss_effect,
                "sound": self.sound, "volume": self.volume, "win_sound": self.win_sound, "miss_sound": self.miss_sound, "seconds": self.seconds,
                "position": self.position, "scale": self.scale, "frame": self.frame, "show_numbers": self.show_numbers,
                "show_remaining": self.show_remaining, "show_hash": self.show_hash}

    def to_dict(self) -> dict[str, Any]:
        return {**self.display(), "prizes": [{"name": prize.name, "count": prize.count, "rare": prize.rare} for prize in self.prizes],
                "blank": self.blank, "colors": dict(self.colors), "show_help": self.show_help, "viewers": self.viewers.to_dict()}


# --------------------------------------------------------------------------- 색


def _rgb(color: str) -> tuple[float, float, float]:
    return int(color[1:3], 16) / 255, int(color[3:5], 16) / 255, int(color[5:7], 16) / 255


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, part)) * 255):02x}" for part in rgb)


def _mix(first: str, second: str, amount: float) -> str:
    """``amount`` 만큼 두 번째 색 쪽으로."""
    a, b = _rgb(first), _rgb(second)
    return _hex((a[0] + (b[0] - a[0]) * amount, a[1] + (b[1] - a[1]) * amount, a[2] + (b[2] - a[2]) * amount))


def _shade(color: str, lightness: float) -> str:
    hue, light, saturation = colorsys.rgb_to_hls(*_rgb(color))
    return _hex(colorsys.hls_to_rgb(hue, max(0.0, min(1.0, light + lightness)), saturation))


def _luminance(color: str) -> float:
    def linear(part: float) -> float:
        return part / 12.92 if part <= 0.03928 else ((part + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(part) for part in _rgb(color))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(first: str, second: str) -> float:
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _on(color: str) -> str:
    """색 위에 쓸 글자 색(잉크와 종이 중 대비가 큰 쪽)."""
    return INK if contrast(color, INK) >= contrast(color, PAPER) else PAPER


def color_hex(key: str) -> str:
    """테마 색 이름의 색. channel은 지금 방송 색의 주 색."""
    if key == "channel":
        from .overlay import theme

        return theme.load()["primary"]
    return COLORS[key][1]


def options() -> dict[str, Any]:
    """조작 화면의 선택 목록(방송 색은 지금 색으로)."""
    return {**OPTIONS, "colors": {key: {"label": label, "hex": color_hex(key)} for key, (label, _) in COLORS.items()}}


def palette(color: str, overrides: dict[str, str] | None = None) -> dict[str, str]:
    """테마 색 하나에서 나머지 색을 만든다. ``overrides`` (cover, board, text, win)는 직접 지정한 색."""
    overrides = overrides or {}
    base = color_hex(color) if color in COLORS else color if _COLOR.match(color or "") else COLORS["pink"][1]
    cover = overrides.get("cover") or base
    board = overrides.get("board") or _mix(base, PAPER, 0.88)
    win = overrides.get("win") or base
    return {"base": base, "cover": cover, "cover_deep": _shade(cover, -0.16), "cover_light": _mix(cover, "#ffffff", 0.5), "on_cover": _on(cover),
            "board": board, "board_deep": _mix(board, INK, 0.14), "text": overrides.get("text") or _on(board), "win": win, "on_win": _on(win),
            "ink": INK, "paper": PAPER, "gold": GOLD, "gold_deep": GOLD_DEEP, "miss": MISS, "muted": MUTED}


# --------------------------------------------------------------------------- 설정 확인


def _whole(value: Any, low: int, high: int, message: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise PickError(message)
    try:
        number = float(value)
    except ValueError:
        raise PickError(message) from None
    if number != int(number) or not low <= number <= high:
        raise PickError(message)
    return int(number)


def _choice(value: Any, options: dict[str, str], what: str) -> str:
    """``what`` 은 조사까지(예: 디자인은)."""
    if value not in options:
        raise PickError(f"{what} " + ", ".join(f"{key}({label})" for key, label in options.items()) + " 중 하나")
    return str(value)


def _line(value: Any) -> str:
    return " ".join(str(value if value is not None else "").split())


def _color(value: Any, what: str) -> str:
    color = str(value or "").strip()
    if color and not _COLOR.match(color):
        raise PickError(f"{what} 색은 #RRGGBB 형식(예: #ff4f8b)")
    return color.lower()


def check_command(value: Any) -> str:
    command = str(value or "").strip()
    if not command.startswith("!") or not 2 <= len(command) <= 20 or any(ch.isspace() for ch in command):
        raise PickError("참여 명령은 !로 시작하고 띄어쓰기 없는 20자 이내(예: !뽑기)")
    if command.casefold() in {name.casefold() for name in RESERVED_COMMANDS}:
        raise PickError(f"다른 기능이 쓰는 명령: {command}")
    return command


def _prizes(raw: Any) -> tuple[Prize, ...]:
    if not isinstance(raw, list) or not raw:
        raise PickError("상품을 1개 이상 입력")
    if len(raw) > MAX_PRIZES:
        raise PickError(f"상품은 {MAX_PRIZES}종류까지")
    found: list[Prize] = []
    for item in raw:
        item = item if isinstance(item, dict) else {}
        name = _line(item.get("name"))
        if not name:
            raise PickError("상품 이름이 비어 있음")
        if len(name) > MAX_NAME:
            raise PickError(f"상품 이름은 {MAX_NAME}자 이내: {name[:10]}")
        if name in {prize.name for prize in found}:
            raise PickError(f"같은 이름의 상품이 2개: {name}")
        count = _whole(item.get("count", 1), 1, MAX_COUNT, f"수량은 1에서 {MAX_COUNT} 사이의 정수: {name}")
        found.append(Prize(name, count, bool(item.get("rare", False))))
    return tuple(found)


def _styles(raw: Any) -> dict[str, dict[str, Any]]:
    raw = raw if isinstance(raw, dict) else {}
    found: dict[str, dict[str, Any]] = {}
    for part, defaults in DEFAULT_STYLES.items():
        given = raw.get(part) if isinstance(raw.get(part), dict) else {}
        values = {**defaults, **{key: value for key, value in given.items() if key in defaults}}
        name = STYLE_NAMES[part]
        style: dict[str, Any] = {}
        for key, (low, high) in STYLE_RANGES[part].items():
            unit = "%" if part == "result" or key == "line" else "px"
            label = "크기" if key == "size" else "줄 간격"
            style[key] = _whole(values[key], low, high, f"{name} {label}는 {low}{unit}에서 {high}{unit} 사이")
        style["color"] = _color(values["color"], name)
        style["align"] = _choice(values["align"], ALIGNS, f"{name} 정렬은")
        found[part] = style
    return found


def _viewers(raw: Any) -> Viewers:
    raw = raw if isinstance(raw, dict) else {}
    base = Viewers().to_dict()
    values = {**base, **{key: value for key, value in raw.items() if key in base}}
    who = _choice(values["who"], WHO, "열 수 있는 사람은")
    minimum = values["donation_min"]
    if minimum in (None, ""):
        minimum = None
    else:
        minimum = _whole(minimum, 0, MAX_WON, "후원 최소 금액은 0 이상의 정수(원). 후원으로 열지 않으면 비워 두기")
    if who == "donors" and minimum is None:
        raise PickError("후원자만 열기는 후원 최소 금액(원)이 필요")
    platforms = values["platforms"]
    if not isinstance(platforms, list) or not platforms or any(item not in PLATFORMS for item in platforms):
        raise PickError("플랫폼을 1개 이상 선택(" + ", ".join(PLATFORMS) + ")")
    return Viewers(enabled=bool(values["enabled"]), command=check_command(values["command"]), who=who, donation_min=minimum,
                   repeat=bool(values["repeat"]), cooldown=_whole(values["cooldown"], *COOLDOWN, f"대기 시간은 {COOLDOWN[0]}초에서 {COOLDOWN[1]}초 사이"),
                   per_viewer=_whole(values["per_viewer"], *PER_VIEWER, f"시청자별 횟수는 {PER_VIEWER[0]}에서 {PER_VIEWER[1]} 사이(0은 제한 없음)"),
                   platforms=tuple(name for name in PLATFORMS if name in platforms))


def parse_config(data: Any, base: Config | None = None) -> Config:
    """조작 화면, 명령줄에서 받은 설정 확인. 주지 않은 항목은 ``base`` (없으면 기본 설정) 값. 틀리면 PickError(한국어 안내)."""
    if not isinstance(data, dict):
        raise PickError("설정 형식이 올바르지 않음")
    merged = (base or Config()).to_dict()
    for key, value in data.items():
        if key == "styles" and isinstance(value, dict):
            merged["styles"] = {part: {**merged["styles"].get(part, {}), **(value.get(part) if isinstance(value.get(part), dict) else {})}
                                for part in DEFAULT_STYLES}
        elif key in ("colors", "viewers") and isinstance(value, dict):
            merged[key] = {**merged[key], **value}
        elif key in merged:
            merged[key] = value
    title = _line(merged["title"]) or DEFAULT_TITLE
    if len(title) > MAX_TITLE:
        raise PickError(f"제목은 {MAX_TITLE}자 이내")
    lines = [_line(line) for line in str(merged["caption"] or "").splitlines()]
    caption = "\n".join(line for line in lines if line)
    if len(caption) > MAX_CAPTION or caption.count("\n") >= MAX_CAPTION_LINES:
        raise PickError(f"설명은 {MAX_CAPTION}자, {MAX_CAPTION_LINES}줄 이내")
    cells = _whole(merged["cells"], *CELLS, f"칸 수는 {CELLS[0]}에서 {CELLS[1]} 사이")
    columns = _whole(merged["columns"], *COLUMNS, f"열 수는 0(자동) 또는 1에서 {COLUMNS[1]} 사이")
    prizes = _prizes(merged["prizes"])
    total = sum(prize.count for prize in prizes)
    if total > cells:
        raise PickError(f"상품 수({total})가 칸 수({cells})보다 많음")
    blank = _line(merged["blank"]) or DEFAULT_BLANK
    if len(blank) > MAX_NAME:
        raise PickError(f"빈칸 이름은 {MAX_NAME}자 이내")
    color = str(merged["color"] or "").strip().lower()
    if color not in COLORS and not _COLOR.match(color):
        raise PickError("테마 색은 " + ", ".join(COLORS) + " 중 하나 또는 #RRGGBB")
    raw_colors = merged["colors"] if isinstance(merged["colors"], dict) else {}
    colors = {part: _color(raw_colors.get(part), label) for part, label in COLOR_PARTS.items() if raw_colors.get(part)}
    return Config(
        title=title, caption=caption, cells=cells, columns=columns, prizes=prizes, blank=blank,
        theme=_choice(merged["theme"], THEMES, "디자인은"), color=color, colors=colors, cover=_choice(merged["cover"], COVERS, "덮개 무늬는"),
        font=_choice(merged["font"], FONTS, "글꼴은"), styles=_styles(merged["styles"]), effect=_choice(merged["effect"], EFFECTS, "당첨 효과는"),
        miss_effect=_choice(merged["miss_effect"], MISS_EFFECTS, "꽝 효과는"), sound=bool(merged["sound"]),
        volume=_whole(merged["volume"], *VOLUME, f"음량은 {VOLUME[0]}에서 {VOLUME[1]} 사이"),
        win_sound=_choice(merged["win_sound"], WIN_SOUNDS, "당첨 소리는"), miss_sound=_choice(merged["miss_sound"], MISS_SOUNDS, "꽝 소리는"),
        seconds=_whole(merged["seconds"], *SECONDS, f"결과 표시 시간은 {SECONDS[0]}초에서 {SECONDS[1]}초 사이"),
        position=_choice(merged["position"], POSITIONS, "위치는"), scale=_whole(merged["scale"], *SCALE, f"크기는 {SCALE[0]}%에서 {SCALE[1]}% 사이"),
        frame=bool(merged["frame"]), show_numbers=bool(merged["show_numbers"]), show_remaining=bool(merged["show_remaining"]),
        show_hash=bool(merged["show_hash"]), show_help=bool(merged["show_help"]), viewers=_viewers(merged["viewers"]),
    )


# --------------------------------------------------------------------------- 배치, 공정성 확인, 채팅


def contents(config: Config) -> list[str]:
    """칸에 들어갈 내용 전체(상품을 수량만큼, 나머지는 빈칸). 섞기 전 순서."""
    found = [prize.name for prize in config.prizes for _ in range(prize.count)]
    return found + [config.blank] * (config.cells - len(found))


def commit_text(layout: list[str], salt: str) -> str:
    """공정성 확인 문자열: 첫 줄 소금값, 다음 줄부터 ``번호:내용``. 이 문자열(UTF-8)의 SHA-256을 판을 만들 때 공개한다."""
    return "\n".join([salt, *(f"{number}:{name}" for number, name in enumerate(layout, 1))])


def commitment(layout: list[str], salt: str) -> str:
    return hashlib.sha256(commit_text(layout, salt).encode("utf-8")).hexdigest()


def verify(text: str, digest: str) -> bool:
    """공개한 확인 문자열과 SHA-256 값이 맞는지."""
    return hmac.compare_digest(hashlib.sha256(str(text).encode("utf-8")).hexdigest(), str(digest).strip().lower())


def parse_command(text: str, command: str) -> tuple[bool, int | None]:
    """채팅이 참여 명령인지와 칸 번호(``!뽑기 7``, ``!뽑기 7번``). 번호가 없으면 None(무작위)."""
    tokens = str(text or "").split()
    if not tokens or tokens[0].casefold() != command.casefold():
        return False, None
    if len(tokens) > 1:
        token = tokens[1].removesuffix("번")
        if _NUMBER.match(token):
            return True, int(token)
    return True, None


def donation_numbers(text: str, command: str) -> list[int]:
    """후원 메시지의 칸 번호: 참여 명령 뒤 번호들(``!뽑기 3 7``), 번호만 쓴 메시지(``7``, ``3, 7``), ``7번`` 형태 순으로 찾는다."""
    text = str(text or "").strip()
    tokens = text.replace(",", " ").split()
    if tokens and tokens[0].casefold() == command.casefold():
        return [int(token.removesuffix("번")) for token in tokens[1:] if _NUMBER.match(token.removesuffix("번"))]
    if tokens and all(_NUMBER.match(token.removesuffix("번")) for token in tokens):
        return [int(token.removesuffix("번")) for token in tokens]
    return [int(found) for found in re.findall(r"(?<![0-9])([0-9]{1,3})\s*번(?!째)", text)]


def script(entry: dict[str, Any]) -> str:
    """읽을 문장(대본): 누가(후원 금액), 몇 번, 결과."""
    result = entry["prize"] if entry["tier"] == "miss" else f"{entry['prize']} 당첨"
    opened = f"{entry['cell']}번 {result}"
    if entry.get("source") == "donation":
        return f"{entry['by']} 님 {amount_text('donation', entry.get('amount', 0), entry.get('unit', ''))} 후원 감사합니다. {opened}"
    return f"{entry['by']} 님 {opened}" if entry.get("by") else opened


def _public_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """방송 화면에 보내는 기록 항목(연 칸 하나라 공개해도 됨)."""
    return {key: entry[key] for key in ("id", "cell", "prize", "tier", "by", "platform", "source", "script", "time", "amount", "unit") if key in entry}


# --------------------------------------------------------------------------- 판


@dataclass
class _Board:
    id: str
    name: str
    config: Config
    layout: list[str]
    salt: str
    round: int = 1  # 배치 번호(섞거나 상품을 바꾸면 1 증가)
    opened: list[int] = field(default_factory=list)  # 연 칸(0부터), 연 순서
    log: list[dict[str, Any]] = field(default_factory=list)
    rounds: list[dict[str, Any]] = field(default_factory=list)  # 지난 배치(공개)
    finished: bool = False
    visible: bool = True
    created: float = 0.0
    next_id: int = 1

    @property
    def hash(self) -> str:
        return commitment(self.layout, self.salt)

    def openers(self) -> dict[int, dict[str, Any]]:
        """열린 칸 -> 그 칸을 연 기록(취소하지 않은 가장 최근 기록)."""
        found: dict[int, dict[str, Any]] = {}
        for entry in self.log:
            if not entry.get("undone") and entry.get("index") in self.opened:
                found[entry["index"]] = entry
        return found

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "config": self.config.to_dict(), "layout": list(self.layout), "salt": self.salt,
                "round": self.round, "opened": list(self.opened), "log": list(self.log), "rounds": list(self.rounds), "finished": self.finished,
                "visible": self.visible, "created": self.created, "next_id": self.next_id}


def _new_id() -> str:
    return "b" + secrets.token_hex(4)


def _new_salt() -> str:
    return secrets.token_hex(16)


class PickBoard:
    """저장한 판들과 지금 쓰는 판. 바뀔 때마다 ``pick.json`` 에 저장하고 방송 화면(``channel``)에 공개 상태를 보낸다.

    휴대폰 조작 등에서 쓰는 Python 호출(잘못된 요청은 PickError, 한국어 안내):

    - ``status()`` 방송 화면과 같은 공개 상태(열리지 않은 칸의 상품 없음), ``secret()`` 조작 화면용 전체 상태(배치 포함)
    - ``open(cell=None, by="", platform="", source="remote")`` 칸 열기(번호는 1부터, None이면 남은 칸 중 무작위). 기록 항목 반환
    - ``undo()``, ``reshuffle()``, ``reset()``, ``finish()``, ``set_visible(bool)``, ``replay()``, ``update(설정 일부)``
    - ``create_board()``, ``switch_board(id)``, ``rename_board(id, name)``, ``delete_board(id)``
    """

    def __init__(self, *, rng: random.Random | None = None, notify: Callable[[str], None] | None = None, load: bool = True,
                 clock: Callable[[], float] = time.time, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._lock = threading.RLock()
        self._rng = rng or random.SystemRandom()
        self._notify = notify or (lambda text: None)
        self._clock = clock
        self._monotonic = monotonic
        self._boards: dict[str, _Board] = {}
        self._active = ""
        self._cooldowns: dict[str, float] = {}
        self._seq = 0
        self._version = 0
        self._stored = False  # pick.json에 저장했는지(처음 예시 판은 바꾸거나 열 때 저장)
        self._restore(settings.load_data(DATA_FILE) if load else {})
        self.channel = Channel(self._public(None))

    # ------------------------------------------------------------------ 저장, 불러오기
    def _shuffled(self, config: Config) -> list[str]:
        layout = contents(config)
        self._rng.shuffle(layout)
        return layout

    def _new_board(self, name: str, config: Config) -> _Board:
        return _Board(_new_id(), name, config, self._shuffled(config), _new_salt(), created=round(self._clock(), 3))

    def _restore(self, data: dict[str, Any]) -> None:
        for raw in data.get("boards") or []:
            board = self._restore_board(raw)
            if board is not None and board.id not in self._boards and len(self._boards) < MAX_BOARDS:
                self._boards[board.id] = board
        self._stored = bool(self._boards)
        if not self._boards:
            board = self._new_board(DEFAULT_BOARD, Config())
            self._boards[board.id] = board
        active = data.get("active")
        self._active = active if active in self._boards else next(iter(self._boards))

    def _restore_board(self, raw: Any) -> _Board | None:
        """저장한 판 하나. 설정이 손상되었으면 기본 설정, 배치가 설정과 맞지 않으면 새로 섞는다(열린 칸 없이)."""
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not re.match(r"^b[0-9a-f]{8}$", raw["id"]):
            return None
        try:
            config = parse_config(raw.get("config") or {})
        except PickError:
            config = Config()
        created = raw.get("created")
        board = _Board(raw["id"], _line(raw.get("name"))[:MAX_BOARD_NAME] or DEFAULT_BOARD, config, [], "",
                       created=float(created) if isinstance(created, (int, float)) and not isinstance(created, bool) else 0.0)
        layout, salt = raw.get("layout"), raw.get("salt")
        if (isinstance(layout, list) and all(isinstance(item, str) for item in layout) and Counter(layout) == Counter(contents(config))
                and isinstance(salt, str) and re.match(r"^[0-9a-f]{32}$", salt)):
            board.layout, board.salt = list(layout), salt
            opened = raw.get("opened") if isinstance(raw.get("opened"), list) else []
            board.opened = [index for position, index in enumerate(opened) if isinstance(index, int) and not isinstance(index, bool)
                            and 0 <= index < config.cells and index not in opened[:position]]
            board.finished = bool(raw.get("finished")) or len(board.opened) == config.cells
            board.round = raw["round"] if isinstance(raw.get("round"), int) and raw["round"] > 0 else 1
        else:
            board.layout, board.salt = self._shuffled(config), _new_salt()
        board.log = [item for item in raw.get("log") or [] if isinstance(item, dict)][-MAX_LOG:]
        board.rounds = [item for item in raw.get("rounds") or [] if isinstance(item, dict)][-MAX_ROUNDS:]
        board.visible = raw.get("visible", True) is not False
        board.next_id = raw["next_id"] if isinstance(raw.get("next_id"), int) and raw["next_id"] > 0 else len(board.log) + 1
        return board

    def _save(self) -> None:
        settings.save_data(DATA_FILE, {"version": 1, "active": self._active, "boards": [board.to_dict() for board in self._boards.values()]})
        self._stored = True

    def _changed(self, event: dict[str, Any], *, keep: bool = True, save: bool = True) -> None:
        """바뀐 내용을 저장하고 방송 화면에 보낸다(잠금 안에서 부른다)."""
        self._version += 1
        if save:
            self._save()
        self._seq += 1
        self.channel.publish(self._public(event), keep=keep)

    @property
    def _board(self) -> _Board:
        return self._boards[self._active]

    # ------------------------------------------------------------------ 상태
    def _remaining(self, board: _Board) -> list[dict[str, Any]]:
        opened = Counter(board.layout[index] for index in board.opened)
        return [{"name": prize.name, "total": prize.count, "left": max(0, prize.count - opened[prize.name]), "tier": board.config.tier(prize.name)}
                for prize in board.config.prizes if board.config.tier(prize.name) != "miss"]

    def _help(self, config: Config) -> list[str]:
        """방송 화면의 참여 안내 줄."""
        viewers = config.viewers
        if not viewers.enabled or not config.show_help:
            return []
        lines = []
        if viewers.who == "all":
            lines.append(f"채팅 {viewers.command} 번호")
        elif viewers.who == "staff":
            lines.append(f"스트리머, 매니저 {viewers.command} 번호")
        if viewers.who != "staff" and viewers.donation_min is not None:
            amount = f"{viewers.donation_min:,}원 이상 " if viewers.donation_min else ""
            lines.append(f"{amount}후원 메시지에 번호")
        return lines

    def _commit(self, board: _Board) -> dict[str, Any]:
        commit: dict[str, Any] = {"round": board.round, "hash": board.hash, "revealed": board.finished}
        if board.finished:
            commit.update(salt=board.salt, text=commit_text(board.layout, board.salt))
        return commit

    def _public(self, event: dict[str, Any] | None) -> dict[str, Any]:
        """방송 화면이 받는 상태. 열린 칸(끝난 판은 모든 칸)의 상품만 넣는다."""
        board = self._board
        config = board.config
        openers = board.openers()
        cells = []
        for index, name in enumerate(board.layout):
            cell: dict[str, Any] = {"n": index + 1, "open": index in board.opened}
            if cell["open"] or board.finished:
                cell.update(prize=name, tier=config.tier(name))
                if index in openers:
                    cell["by"] = openers[index].get("by", "")
            cells.append(cell)
        value: dict[str, Any] = {"seq": self._seq, "version": self._version, "board": {"id": board.id, "name": board.name}, "visible": board.visible,
                                 "finished": board.finished, "opened": len(board.opened), "total": config.cells, "display": config.display(),
                                 "cells": cells, "commit": self._commit(board), "help": self._help(config), "event": event}
        if config.show_remaining:
            value["remaining"] = self._remaining(board)
        return value

    def status(self) -> dict[str, Any]:
        """공개 상태(방송 화면, ``/pick/state``). 열리지 않은 칸의 상품은 넣지 않는다."""
        with self._lock:
            return self._public(None)

    def secret(self) -> dict[str, Any]:
        """조작 화면용 전체 상태: 배치, 설정, 기록(최근 것부터), 저장한 판 목록. 방송 화면에는 보내지 않는다."""
        with self._lock:
            board = self._board
            config = board.config
            layout = [{"n": index + 1, "prize": name, "tier": config.tier(name), "open": index in board.opened} for index, name in enumerate(board.layout)]
            boards = [{"id": item.id, "name": item.name, "opened": len(item.opened), "total": item.config.cells, "finished": item.finished,
                       "active": item.id == self._active} for item in self._boards.values()]
            return {"version": self._version, "board": {"id": board.id, "name": board.name}, "boards": boards, "config": config.to_dict(),
                    "layout": layout, "opened": len(board.opened), "total": config.cells, "visible": board.visible, "finished": board.finished,
                    "commit": self._commit(board), "rounds": list(board.rounds), "remaining": self._remaining(board),
                    "log": list(reversed(board.log)), "help": self._help(config), "stored": self._stored, "options": options()}

    def proof(self) -> dict[str, Any]:
        """공개해도 되는 공정성 확인 정보: 지금 배치의 값(끝난 판은 확인 문자열 포함)과 지난 배치들."""
        with self._lock:
            board = self._board
            return {"board": {"id": board.id, "name": board.name}, "current": self._commit(board), "rounds": list(board.rounds)}

    # ------------------------------------------------------------------ 조작
    def _retire_round(self, board: _Board, reason: str) -> None:
        """지금 배치를 공개 기록으로 옮기고 새 소금값(새 배치를 만들기 전)."""
        board.rounds.append({"round": board.round, "hash": board.hash, "salt": board.salt, "text": commit_text(board.layout, board.salt),
                             "reason": reason, "time": round(self._clock(), 3)})
        del board.rounds[:-MAX_ROUNDS]
        board.round += 1
        board.salt = _new_salt()

    def _cell(self, board: _Board, cell: Any) -> int:
        number = _whole(cell, 1, board.config.cells, f"칸 번호는 1에서 {board.config.cells} 사이의 정수")
        if number - 1 in board.opened:
            raise PickError(f"이미 열린 칸: {number}번")
        return number - 1

    def _open(self, board: _Board, index: int | None, *, by: str, platform: str, source: str, amount: float = 0.0, unit: str = "") -> dict[str, Any]:
        if board.finished:
            raise PickError("끝난 판: 초기화하면 다시 시작")
        closed = [position for position in range(board.config.cells) if position not in board.opened]
        if not closed:
            raise PickError("남은 칸 없음")
        if index is None:
            index = self._rng.choice(closed)
        board.opened.append(index)
        name = board.layout[index]
        entry: dict[str, Any] = {"id": board.next_id, "index": index, "cell": index + 1, "prize": name, "tier": board.config.tier(name),
                                 "by": _line(by)[:MAX_BY], "platform": platform, "source": source if source in SOURCES else "api",
                                 "time": round(self._clock(), 3), "round": board.round}
        if source == "donation":
            entry.update(amount=amount, unit=unit)
        entry["script"] = script(entry)
        board.next_id += 1
        board.log.append(entry)
        del board.log[:-MAX_LOG]
        if len(board.opened) == board.config.cells:
            board.finished = True
        return entry

    def open(self, cell: Any = None, *, by: str = "", platform: str = "", source: str = "control") -> dict[str, Any]:
        """칸 열기. ``cell`` 은 1부터 시작하는 번호, None이면 남은 칸 중 무작위. 기록 항목(대본 ``script`` 포함)을 돌려준다."""
        with self._lock:
            board = self._board
            index = None if cell is None or cell == "" else self._cell(board, cell)
            entry = self._open(board, index, by=by, platform=platform, source=source)
            self._changed({"type": "open", "entry": _public_entry(entry)})
            return entry

    def undo(self) -> dict[str, Any]:
        """마지막으로 연 칸을 다시 덮는다(잘못 연 경우). 기록에는 취소로 남는다. 끝내고 공개한 판은 되돌릴 수 없다."""
        with self._lock:
            board = self._board
            if board.finished and len(board.opened) < board.config.cells:
                raise PickError("끝내고 공개한 판은 되돌릴 수 없음")
            if not board.opened:
                raise PickError("되돌릴 칸 없음")
            index = board.opened.pop()
            board.finished = False
            for entry in reversed(board.log):
                if entry.get("index") == index and not entry.get("undone"):
                    entry["undone"] = True
                    break
            self._changed({"type": "undo", "cell": index + 1})
            return self.secret()

    def reshuffle(self) -> dict[str, Any]:
        """열리지 않은 칸끼리 내용을 다시 섞는다(새 배치와 새 확인 값, 지난 배치는 공개)."""
        with self._lock:
            board = self._board
            if board.finished:
                raise PickError("끝난 판: 초기화하면 다시 시작")
            closed = [index for index in range(board.config.cells) if index not in board.opened]
            if len(closed) < 2:
                raise PickError("섞을 칸이 2개 이상 필요")
            self._retire_round(board, "reshuffle")
            self._fill(board, closed, [board.layout[index] for index in closed])
            self._changed({"type": "reshuffle"})
            return self.secret()

    def _fill(self, board: _Board, closed: list[int], names: list[str]) -> None:
        self._rng.shuffle(names)
        for index, name in zip(closed, names, strict=True):
            board.layout[index] = name

    def reset(self) -> dict[str, Any]:
        """모든 칸을 덮고 처음부터 다시 섞는다(기록은 남김)."""
        with self._lock:
            self._reset(self._board, "reset")
            self._changed({"type": "reset"})
            return self.secret()

    def _reset(self, board: _Board, reason: str) -> None:
        self._retire_round(board, reason)
        board.layout = self._shuffled(board.config)
        board.opened = []
        board.finished = False

    def finish(self) -> dict[str, Any]:
        """판을 끝내고 남은 칸과 확인 문자열(소금값, 배치)을 공개한다."""
        with self._lock:
            board = self._board
            if board.finished:
                raise PickError("이미 끝난 판")
            board.finished = True
            self._changed({"type": "finish"})
            return self.secret()

    def set_visible(self, visible: Any) -> dict[str, Any]:
        """방송 화면에 판 보이기, 숨기기(숨긴 동안 시청자는 열 수 없음)."""
        with self._lock:
            self._board.visible = visible is not False
            self._changed({"type": "visible"})
            return self.secret()

    def replay(self) -> dict[str, Any]:
        """마지막 결과 카드를 방송 화면에 한 번 더 표시(저장하지 않음, 새로 연결한 화면에는 보내지 않음)."""
        with self._lock:
            board = self._board
            last = board.openers().get(board.opened[-1]) if board.opened else None
            if last is None:
                raise PickError("다시 보일 결과 없음")
            self._changed({"type": "replay", "entry": _public_entry(last)}, keep=False, save=False)
            return {"entry": last}

    def clear_log(self) -> dict[str, Any]:
        with self._lock:
            self._board.log.clear()
            self._changed({"type": "log"})
            return self.secret()

    def update(self, changes: Any) -> dict[str, Any]:
        """설정 바꾸기(주지 않은 항목은 그대로). 칸 수, 상품, 빈칸 이름이 바뀌면 열리지 않은 칸을 새로 채워 섞는다(새 확인 값).
        열린 칸이 있으면 칸 수는 바꿀 수 없고, 열린 칸이 없거나 끝난 판이면 처음부터 다시 섞는다."""
        with self._lock:
            board = self._board
            config = parse_config(changes, board.config)
            if config.layout_key() == board.config.layout_key():
                board.config = config
                self._changed({"type": "config"})
                return self.secret()
            if board.finished or not board.opened:
                board.config = config
                self._reset(board, "config")
                self._changed({"type": "reset"})
                return self.secret()
            if config.cells != board.config.cells:
                raise PickError("열린 칸이 있으면 칸 수를 바꿀 수 없음(초기화 후 변경)")
            closed = [index for index in range(config.cells) if index not in board.opened]
            left = Counter(name for name in contents(config) if name != config.blank)
            left.subtract(Counter(board.layout[index] for index in board.opened))
            names = [name for name, count in left.items() for _ in range(max(0, count))]
            if len(names) > len(closed):
                raise PickError(f"남은 상품({len(names)})이 남은 칸({len(closed)})보다 많음")
            self._retire_round(board, "config")
            self._fill(board, closed, names + [config.blank] * (len(closed) - len(names)))
            board.config = config
            self._changed({"type": "reshuffle"})
            return self.secret()

    # ------------------------------------------------------------------ 저장한 판
    def _find(self, board_id: Any) -> _Board:
        found = self._boards.get(str(board_id or ""))
        if found is None:
            raise PickError("없는 판", 404)
        return found

    def create_board(self, name: Any = "", *, copy: bool = True) -> dict[str, Any]:
        """새 판(기본은 지금 판의 설정 복사, 배치는 새로)을 만들고 새 판으로 바꾼다."""
        with self._lock:
            if len(self._boards) >= MAX_BOARDS:
                raise PickError(f"판은 {MAX_BOARDS}개까지(쓰지 않는 판 삭제)")
            title = _line(name) or f"판 {len(self._boards) + 1}"
            if len(title) > MAX_BOARD_NAME:
                raise PickError(f"판 이름은 {MAX_BOARD_NAME}자 이내")
            board = self._new_board(title, self._board.config if copy else Config())
            self._boards[board.id] = board
            self._active = board.id
            self._changed({"type": "board"})
            return self.secret()

    def switch_board(self, board_id: Any) -> dict[str, Any]:
        with self._lock:
            self._active = self._find(board_id).id
            self._changed({"type": "board"})
            return self.secret()

    def rename_board(self, board_id: Any, name: Any) -> dict[str, Any]:
        with self._lock:
            board = self._find(board_id)
            title = _line(name)
            if not title or len(title) > MAX_BOARD_NAME:
                raise PickError(f"판 이름은 1자에서 {MAX_BOARD_NAME}자")
            board.name = title
            self._changed({"type": "config"})
            return self.secret()

    def delete_board(self, board_id: Any) -> dict[str, Any]:
        with self._lock:
            board = self._find(board_id)
            if len(self._boards) == 1:
                raise PickError("마지막 판은 지울 수 없음")
            del self._boards[board.id]
            if self._active == board.id:
                self._active = next(iter(self._boards))
            self._changed({"type": "board"})
            return self.secret()

    # ------------------------------------------------------------------ 시청자 참여
    def handle(self, event: Any) -> None:
        """오버레이 허브의 사건(채팅, 후원). 조건에 맞으면 칸을 연다. 허브가 부르므로 빨리 끝나야 한다."""
        if getattr(event, "kind", "") not in ("chat", "donation") or getattr(event, "platform", "") == "system":
            return
        try:
            if self._board.config.viewers.enabled:
                self.viewer_open(event)
        except (PickError, OSError, KeyError):  # 저장 실패, 그 사이 지운 판
            pass

    def viewer_open(self, event: Any) -> tuple[list[dict[str, Any]], str]:
        """시청자 사건 하나를 처리해 (연 칸 기록들, 열지 않은 이유)를 돌려준다. 이유는 조작 화면의 참여 시험에 표시."""
        platform = str(getattr(event, "platform", ""))
        kind = str(getattr(event, "kind", ""))
        name = _line(getattr(event, "name", ""))[:MAX_BY] or "시청자"
        text = str(getattr(event, "text", ""))
        staff = getattr(event, "role", "") in ("owner", "moderator")
        with self._lock:
            board = self._board
            viewers = board.config.viewers
            if not viewers.enabled:
                return [], "시청자 참여 꺼짐"
            if platform != "demo" and platform not in viewers.platforms:
                return [], "허용하지 않은 플랫폼"
            if not board.visible:
                return [], "판을 숨긴 상태"
            if board.finished:
                return [], "끝난 판"
            if kind == "chat":
                return self._chat_open(board, viewers, platform, name, text, staff)
            if kind == "donation":
                amount = getattr(event, "amount", 0)
                return self._donation_open(board, viewers, platform, name, text, float(amount or 0), str(getattr(event, "unit", "") or ""))
            return [], "채팅, 후원만 처리"

    def _chat_open(self, board: _Board, viewers: Viewers, platform: str, name: str, text: str, staff: bool) -> tuple[list[dict[str, Any]], str]:
        matched, number = parse_command(text, viewers.command)
        if not matched:
            return [], "참여 명령이 아님"
        if not staff and viewers.who == "staff":
            return [], "스트리머와 매니저만"
        if not staff and viewers.who == "donors":
            return [], "후원으로만 열기"
        key = f"{platform}:{name}"
        now = self._monotonic()
        if not staff:
            last = self._cooldowns.get(key)
            if last is not None and now - last < viewers.cooldown:
                return [], f"대기 시간 남음({viewers.cooldown - (now - last):.0f}초)"
            mine = sum(1 for entry in board.openers().values() if entry.get("source") == "chat" and f"{entry.get('platform')}:{entry.get('by')}" == key)
            if viewers.per_viewer and mine >= viewers.per_viewer:
                return [], f"이 판에서 {viewers.per_viewer}번까지"
        if number is not None and not 1 <= number <= board.config.cells:
            return [], f"없는 칸: {number}번"
        if number is not None and number - 1 in board.opened:
            if staff:
                self._notify(f"뽑기판: {number}번은 이미 열림")
            return [], f"이미 열린 칸: {number}번"
        entry = self._open(board, None if number is None else number - 1, by=name, platform=platform, source="chat")
        if not staff:
            self._cooldowns[key] = now
            if len(self._cooldowns) > 5000:  # 오래 켜 둔 방송: 대기가 끝난 시청자 정리
                self._cooldowns = {item: when for item, when in self._cooldowns.items() if now - when < viewers.cooldown}
        self._changed({"type": "open", "entry": _public_entry(entry)})
        return [entry], ""

    def _donation_open(self, board: _Board, viewers: Viewers, platform: str, name: str, text: str, amount: float,
                       unit: str) -> tuple[list[dict[str, Any]], str]:
        if viewers.who == "staff" or viewers.donation_min is None:
            return [], "후원으로 열기 꺼짐"
        rate = WON_PER_UNIT.get(unit)
        won = amount * rate if rate is not None else None
        minimum = viewers.donation_min
        if minimum and (won is None or won < minimum):
            return [], f"최소 금액 미달({minimum:,}원)"
        count = min(MAX_REPEAT, int(won // minimum)) if viewers.repeat and minimum and won is not None else 1
        wanted = [number - 1 for number in donation_numbers(text, viewers.command) if 1 <= number <= board.config.cells]
        opened: list[dict[str, Any]] = []
        for _ in range(count):
            if board.finished:
                break
            index = next((item for item in wanted if item not in board.opened), None)
            if index is not None:
                wanted.remove(index)
            entry = self._open(board, index, by=name, platform=platform, source="donation", amount=amount, unit=unit)
            opened.append(entry)
            self._changed({"type": "open", "entry": _public_entry(entry)})
        return opened, ""

    def test_event(self, data: dict[str, Any]) -> dict[str, Any]:
        """조작 화면의 참여 시험: 시험 플랫폼(demo)의 채팅이나 후원 하나를 처리한 결과."""
        kind = "donation" if data.get("kind") == "donation" else "chat"
        amount = data.get("amount", 1000) if kind == "donation" else 0
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not 0 <= amount <= MAX_WON:
            raise PickError("시험 금액은 0 이상의 숫자(원)")
        role = data.get("role") if data.get("role") in ("owner", "moderator") else ""
        event = OverlayEvent("demo", kind, _line(data.get("name"))[:MAX_BY] or "시험 시청자", (("text", str(data.get("text") or "")[:200]),),
                             amount=float(amount), unit="원" if kind == "donation" else "", role=role)
        opened, reason = self.viewer_open(event)
        return {"opened": opened, "reason": reason}

    # ------------------------------------------------------------------ 오버레이 서버 주소(본문 JSON)
    def route_open(self, data: dict[str, Any]) -> dict[str, Any]:
        return {"entry": self.open(data.get("cell"), by=str(data.get("by") or ""), source="control")}

    def route_config(self, data: dict[str, Any]) -> dict[str, Any]:
        changes = data.get("config") if isinstance(data.get("config"), dict) else data
        if not changes:
            raise PickError("바꿀 설정이 없음")
        return self.update(changes)

    def route_board(self, action: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
        def run(data: dict[str, Any]) -> dict[str, Any]:
            if action == "new":
                return self.create_board(data.get("name"), copy=data.get("copy", True) is not False)
            if action == "switch":
                return self.switch_board(data.get("id"))
            if action == "rename":
                return self.rename_board(data.get("id"), data.get("name"))
            return self.delete_board(data.get("id"))

        return run


#: 조작 화면이 고르는 항목 이름
OPTIONS = {"themes": THEMES, "colors": {key: {"label": label, "hex": value} for key, (label, value) in COLORS.items()}, "color_parts": COLOR_PARTS,
           "covers": COVERS, "fonts": FONTS, "effects": EFFECTS, "miss_effects": MISS_EFFECTS, "win_sounds": WIN_SOUNDS, "miss_sounds": MISS_SOUNDS,
           "positions": POSITIONS, "aligns": ALIGNS, "who": WHO, "platforms": PLATFORMS, "sources": SOURCES, "style_ranges": STYLE_RANGES,
           "limits": {"cells": CELLS, "columns": COLUMNS, "prizes": MAX_PRIZES, "count": MAX_COUNT, "name": MAX_NAME, "title": MAX_TITLE,
                      "caption": MAX_CAPTION, "boards": MAX_BOARDS, "board_name": MAX_BOARD_NAME, "seconds": SECONDS, "scale": SCALE,
                      "volume": VOLUME, "cooldown": COOLDOWN, "per_viewer": PER_VIEWER}}


def pick_feature(context: Context, board: PickBoard | None = None) -> Feature:
    """오버레이 서버에 등록하는 뽑기판(feature.default_features). ``board`` 를 주면 그 판을 사용(휴대폰 조작 등과 공유).

    등록한 기능의 ``taps[0]`` 은 ``board.handle`` 이라 ``taps[0].__self__`` 로 PickBoard를 찾을 수 있다.
    """
    board = board or PickBoard(notify=context.notify)
    return Feature(
        name="pick",
        static={"/pick": "pick.html", "/pick.js": "pick.js", "/pick.css": "pick.css", "/pick/control": "pick-control.html"},
        get={"/pick/state": lambda query: board.status(), "/pick/secret": lambda query: board.secret(), "/pick/proof": lambda query: board.proof()},
        post={"/pick/open": board.route_open, "/pick/undo": lambda data: board.undo(), "/pick/reshuffle": lambda data: board.reshuffle(),
              "/pick/reset": lambda data: board.reset(), "/pick/finish": lambda data: board.finish(),
              "/pick/visible": lambda data: board.set_visible(data.get("visible", True)), "/pick/replay": lambda data: board.replay(),
              "/pick/log/clear": lambda data: board.clear_log(), "/pick/config": board.route_config, "/pick/test": board.test_event,
              "/pick/board/new": board.route_board("new"), "/pick/board/switch": board.route_board("switch"),
              "/pick/board/rename": board.route_board("rename"), "/pick/board/delete": board.route_board("delete")},
        feeds={"pick": board.channel},
        taps=[board.handle],
        body_limit={"/pick/config": 65536},
    )
