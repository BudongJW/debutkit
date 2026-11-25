"""후원 추첨 연출: 후원이 오면 상품표에서 확률대로 뽑아 방송 화면(``/draw``)에 카드 뒤집기, 룰렛 연출로 표시한다.

- 설정은 저장 설정의 ``draw_*`` 항목. 조작 화면(``/draw/control``)이나 ``debutkit draw set`` 으로 바꾸며 다음 후원부터 적용
- 상품표 ``"가중치:이름"``: 가중치는 비율(합이 100이 아니어도 됨). 확률 5% 이하는 희귀 상품으로 강조, 이름에 꽝이 있으면 꽝 표시
- 추첨 규칙 ``"최소 금액:횟수"``: 원 기준(별풍선 1개 100원, VTube Studio 후원 반응과 같은 환산). 기본은 금액 이상인 규칙 중
  금액이 가장 큰 규칙, ``exact`` 는 금액이 정확히 같은 규칙만. 원으로 환산할 수 없는 단위(Twitch bits, 외화)는 최소 금액 0 규칙만
- 구독, 멤버십은 선택하면 1회 추첨
- 추첨은 서버에서 운영체제 난수(``random.SystemRandom``)로 하고 모든 화면이 같은 결과를 표시
- 결과는 메모리에만 최근 100개 보관(파일로 저장하지 않음). 조작 화면의 최근 결과와 읽을 문장(대본), 대본 창(``/draw/script``),
  기록 창(``/draw/log``)에 사용
- 연출 7가지(카드, 룰렛, 캡슐, 즉석 복권, 티켓, 추첨기, 타로)와 연출별 모양(DESIGNS), 결과 뒤 효과(EFFECTS),
  상품 이름과 안내 글의 글꼴(FONTS, 함께 배포한 글꼴과 운영체제 기본 글꼴만)과 크기(SIZES)
- 타로의 오늘의 한마디는 서버가 고른다(스트리머가 넣은 문장, 없으면 기본 문장 ADVICE). 화면은 받은 문장만 표시
- 대기 중인 추첨이 많으면 방송 화면이 공개 시간을 줄인다(빠른 모드, draw.js의 FAST_QUEUE)
"""

from __future__ import annotations

import queue
import random
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any, Callable

from . import settings
from .vts import WON_PER_UNIT

STYLES = {"card": "카드 뒤집기", "wheel": "룰렛", "capsule": "캡슐 뽑기", "scratch": "즉석 복권", "ticket": "티켓 출력", "drum": "추첨기",
          "tarot": "타로"}
#: 연출별 모양. 첫 항목이 기본(저장한 모양이 연출에 없으면 기본)
DESIGNS = {
    "card": {"basic": "기본"},
    "wheel": {"basic": "기본"},
    "capsule": {"round": "둥근 유리 돔", "box": "네모 유리창", "night": "검정 머신"},
    "scratch": {"classic": "은박, 깔끔하게", "rough": "은박, 거칠게", "night": "검정 복권"},
    "ticket": {"stub": "입장권", "receipt": "영수증", "coupon": "교환권"},
    "drum": {"classic": "핑크 팔각", "wood": "나무", "night": "검정"},
    "tarot": {"night": "밤하늘", "sun": "해", "pink": "핑크 문양"},
}
#: 결과 판이 나올 때의 효과(모두 꽝이면 생략)
EFFECTS = {"none": "없음", "confetti": "종이 조각", "streamers": "색 테이프", "fireworks": "불꽃놀이", "spotlight": "무대 조명", "hearts": "하트",
           "stars": "반짝이는 별"}
#: 상품 이름, 안내 글(하단 띠, 한마디) 글꼴. 함께 배포한 글꼴 2가지와 Windows 기본 글꼴(macOS는 비슷한 글꼴로 대신)
FONTS = {"display": "Black Han Sans(굵은 제목)", "text": "Pretendard(본문)", "gothic": "맑은 고딕", "serif": "바탕(명조)", "gungsuh": "궁서"}
SIZES = {"small": "작게", "medium": "보통", "large": "크게"}
#: 타로 오늘의 한마디 기본 문장(스트리머가 문장을 넣지 않은 경우)
ADVICE = ("작은 일부터 하나씩 해 보기 좋은 날", "물 한 잔 마시고 기지개 한 번", "오늘의 행운은 채팅창에 있음", "웃으면 반은 이미 성공",
          "미뤄 둔 연락 하나 하기 좋은 날", "평소보다 조금 더 대담하게", "좋아하는 노래가 기분을 바꿔 줌", "천천히 가도 결국 도착함",
          "오늘 고른 선택이 정답", "고맙다는 말이 두 배로 돌아오는 날", "충분히 잘하고 있음", "쉬는 것도 실력")
MAX_ADVICE = 30
MAX_ADVICE_LENGTH = 40
POSITIONS = {"center": "아래 가운데", "left": "왼쪽 아래", "right": "오른쪽 아래"}
DEFAULT_TITLE = "후원 추첨"
MAX_TITLE = 20
SCALE = (60, 140)  # 표시 크기(%), 1920x1080 기준 100
MAX_PRIZES = 30
MAX_RULES = 10
MAX_DRAWS = 30
MAX_NAME = 40
MAX_WEIGHT = 1_000_000
MAX_WON = 100_000_000
RARE_PERCENT = 5.0
SECONDS = (3, 60)
#: 처음 사용할 때 보이는 예시(사용은 꺼져 있음)
DEFAULT_PRIZES = ["50:꽝", "35:감사 인사", "12:노래 한 곡", "3:소원 들어주기"]
DEFAULT_RULES = ["1000:1", "10000:11"]


class DrawError(ValueError):
    """저장할 수 없는 추첨 설정. 메시지는 한국어 안내."""


@dataclass(frozen=True)
class Prize:
    name: str
    weight: float


@dataclass(frozen=True)
class Rule:
    min_won: int
    draws: int


@dataclass
class Config:
    enabled: bool = False
    prizes: list[Prize] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)  # 최소 금액이 큰 순서
    exact: bool = False
    members: bool = False
    style: str = "card"
    seconds: int = 8
    title: str = DEFAULT_TITLE  # 추첨 이름(하단 띠에 표시). 예: 벌칙 룰렛
    position: str = "center"
    scale: int = 100
    sound: bool = False  # 효과음(브라우저에서 합성, OBS 오디오 제어를 켠 경우 방송에 나감)
    show_percent: bool = False  # 방송 화면에 확률 표시
    design: str = "basic"  # 연출별 모양(DESIGNS)
    effect: str = "none"  # 결과 뒤 효과(EFFECTS)
    name_font: str = "display"  # 상품 이름 글꼴(FONTS)
    name_size: str = "medium"
    caption_font: str = "display"  # 안내 글(하단 띠, 한마디) 글꼴
    caption_size: str = "medium"
    advice: bool = True  # 타로 오늘의 한마디
    advice_lines: list[str] = field(default_factory=list)  # 스트리머가 넣은 한마디(비면 기본 문장)

    def percent(self, prize: Prize) -> float:
        total = sum(item.weight for item in self.prizes)
        return round(prize.weight / total * 100, 2) if total else 0.0

    def entry(self, prize: Prize) -> dict[str, Any]:
        percent = self.percent(prize)
        miss = "꽝" in prize.name
        return {"name": prize.name, "weight": prize.weight, "percent": percent, "rare": percent <= RARE_PERCENT and not miss, "miss": miss}

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "prizes": [self.entry(prize) for prize in self.prizes],
                "rules": [{"min_won": rule.min_won, "draws": rule.draws} for rule in self.rules], "exact": self.exact,
                "members": self.members, "style": self.style, "seconds": self.seconds, "title": self.title, "position": self.position,
                "scale": self.scale, "sound": self.sound, "show_percent": self.show_percent, "design": self.design, "effect": self.effect,
                "name_font": self.name_font, "name_size": self.name_size, "caption_font": self.caption_font, "caption_size": self.caption_size,
                "advice": self.advice, "advice_lines": list(self.advice_lines), "advice_example": (self.advice_lines or list(ADVICE))[0],
                "styles": STYLES, "positions": POSITIONS, "designs": DESIGNS, "effects": EFFECTS, "fonts": FONTS, "sizes": SIZES}

    def to_settings(self) -> dict[str, Any]:
        return {"draw_enabled": self.enabled, "draw_prizes": [f"{prize.weight:g}:{prize.name}" for prize in self.prizes],
                "draw_rules": [f"{rule.min_won}:{rule.draws}" for rule in self.rules], "draw_exact": self.exact,
                "draw_members": self.members, "draw_style": self.style, "draw_seconds": self.seconds, "draw_title": self.title,
                "draw_position": self.position, "draw_scale": self.scale, "draw_sound": self.sound, "draw_show_percent": self.show_percent,
                "draw_design": self.design, "draw_effect": self.effect, "draw_name_font": self.name_font, "draw_name_size": self.name_size,
                "draw_caption_font": self.caption_font, "draw_caption_size": self.caption_size, "draw_advice": self.advice,
                "draw_advice_lines": list(self.advice_lines)}


# --------------------------------------------------------------------------- 설정 읽기, 확인


def parse_prizes(values: Any) -> list[Prize]:
    """저장 설정의 ``["50:꽝", "3:소원"]``. 형식이 틀린 항목은 건너뛴다."""
    found: list[Prize] = []
    for item in values or []:
        if not isinstance(item, str) or ":" not in item:
            continue
        weight, _, name = item.partition(":")
        try:
            value = float(weight)
        except ValueError:
            continue
        name = name.strip()
        if 0 < value <= MAX_WEIGHT and name and len(name) <= MAX_NAME and name not in {prize.name for prize in found}:
            found.append(Prize(name, value))
    return found[:MAX_PRIZES]


def parse_rules(values: Any) -> list[Rule]:
    """저장 설정의 ``["1000:1", "10000:11"]``. 같은 금액은 나중 항목, 최소 금액이 큰 순서로 정렬."""
    found: dict[int, int] = {}
    for item in values or []:
        if not isinstance(item, str) or ":" not in item:
            continue
        amount, _, draws = item.partition(":")
        if amount.strip().isdigit() and draws.strip().isdigit():
            won, count = int(amount), int(draws)
            if won <= MAX_WON and 1 <= count <= MAX_DRAWS:
                found[won] = count
    return [Rule(won, count) for won, count in sorted(found.items(), reverse=True)][:MAX_RULES]


def parse_advice(values: Any) -> list[str]:
    """저장 설정의 한마디 목록. 빈 줄, 너무 긴 줄, 겹친 줄은 건너뛴다."""
    found: list[str] = []
    for item in values or []:
        line = item.strip() if isinstance(item, str) else ""
        if line and len(line) <= MAX_ADVICE_LENGTH and line not in found:
            found.append(line)
    return found[:MAX_ADVICE]


def design_for(style: str, value: Any) -> str:
    """연출에 있는 모양이면 그대로, 아니면 그 연출의 기본 모양."""
    designs = DESIGNS.get(style, DESIGNS["card"])
    return value if isinstance(value, str) and value in designs else next(iter(designs))


def _choice(value: Any, choices: dict[str, str], default: str) -> str:
    return value if isinstance(value, str) and value in choices else default


def _look(saved: dict[str, Any], style: str) -> dict[str, Any]:
    """저장 설정의 모양, 효과, 글꼴, 한마디. 모르는 값은 기본값."""
    return {"design": design_for(style, saved.get("draw_design")), "effect": _choice(saved.get("draw_effect"), EFFECTS, "none"),
            "name_font": _choice(saved.get("draw_name_font"), FONTS, "display"), "name_size": _choice(saved.get("draw_name_size"), SIZES, "medium"),
            "caption_font": _choice(saved.get("draw_caption_font"), FONTS, "display"),
            "caption_size": _choice(saved.get("draw_caption_size"), SIZES, "medium"), "advice": bool(saved.get("draw_advice", True)),
            "advice_lines": parse_advice(saved.get("draw_advice_lines"))}


def load_config(saved: dict[str, Any] | None = None) -> Config:
    """저장한 추첨 설정. 상품, 규칙을 저장하지 않았으면 예시(사용 꺼짐)."""
    saved = settings.load() if saved is None else saved
    style = saved.get("draw_style") if saved.get("draw_style") in STYLES else "card"
    prizes = parse_prizes(saved.get("draw_prizes")) or parse_prizes(DEFAULT_PRIZES)
    rules = parse_rules(saved.get("draw_rules")) or parse_rules(DEFAULT_RULES)
    seconds = saved.get("draw_seconds", 8)
    scale = saved.get("draw_scale", 100)
    title = str(saved.get("draw_title") or "").strip()[:MAX_TITLE] or DEFAULT_TITLE
    return Config(enabled=bool(saved.get("draw_enabled", False)), prizes=prizes, rules=rules, exact=bool(saved.get("draw_exact", False)),
                  members=bool(saved.get("draw_members", False)), style=style,
                  seconds=seconds if isinstance(seconds, int) and SECONDS[0] <= seconds <= SECONDS[1] else 8, title=title,
                  position=saved.get("draw_position") if saved.get("draw_position") in POSITIONS else "center",
                  scale=scale if isinstance(scale, int) and SCALE[0] <= scale <= SCALE[1] else 100,
                  sound=bool(saved.get("draw_sound", False)), show_percent=bool(saved.get("draw_show_percent", False)), **_look(saved, style))


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _listed(choices: dict[str, str]) -> str:
    return ", ".join(f"{key}({label})" for key, label in choices.items())


def from_request(data: Any) -> Config:
    """조작 화면, 명령줄에서 받은 설정 확인. 틀리면 DrawError(한국어 안내).

    모양, 효과, 글꼴, 한마디 항목이 빠져 있으면 저장한 값을 유지한다(이 항목을 모르는 명령줄에서 다른 설정을 바꿔도 지워지지 않게).
    """
    if not isinstance(data, dict):
        raise DrawError("설정 형식이 올바르지 않음")
    prizes: list[Prize] = []
    raw_prizes = data.get("prizes")
    if not isinstance(raw_prizes, list) or not raw_prizes:
        raise DrawError("상품을 1개 이상 입력")
    if len(raw_prizes) > MAX_PRIZES:
        raise DrawError(f"상품은 {MAX_PRIZES}개까지")
    for item in raw_prizes:
        name = str(item.get("name", "") if isinstance(item, dict) else "").strip()
        weight = _number(item.get("weight") if isinstance(item, dict) else None)
        if not name:
            raise DrawError("상품 이름이 비어 있음")
        if len(name) > MAX_NAME:
            raise DrawError(f"상품 이름은 {MAX_NAME}자 이내: {name[:10]}")
        if name in {prize.name for prize in prizes}:
            raise DrawError(f"같은 이름의 상품이 2개: {name}")
        if weight is None or not 0 < weight <= MAX_WEIGHT:
            raise DrawError(f"확률(가중치)은 0보다 큰 숫자: {name}")
        prizes.append(Prize(name, weight))
    rules: list[Rule] = []
    raw_rules = data.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise DrawError("추첨 규칙을 1개 이상 입력")
    if len(raw_rules) > MAX_RULES:
        raise DrawError(f"추첨 규칙은 {MAX_RULES}개까지")
    for item in raw_rules:
        won = _number(item.get("min_won") if isinstance(item, dict) else None)
        draws = _number(item.get("draws") if isinstance(item, dict) else None)
        if won is None or won != int(won) or not 0 <= won <= MAX_WON:
            raise DrawError("최소 금액은 0 이상의 정수(원)")
        if draws is None or draws != int(draws) or not 1 <= draws <= MAX_DRAWS:
            raise DrawError(f"추첨 횟수는 1에서 {MAX_DRAWS} 사이의 정수")
        if int(won) in {rule.min_won for rule in rules}:
            raise DrawError(f"같은 금액의 규칙이 2개: {int(won):,}원")
        rules.append(Rule(int(won), int(draws)))
    style = data.get("style", "card")
    if not isinstance(style, str) or style not in STYLES:
        raise DrawError(f"연출은 {_listed(STYLES)}")
    seconds = _number(data.get("seconds", 8))
    if seconds is None or seconds != int(seconds) or not SECONDS[0] <= seconds <= SECONDS[1]:
        raise DrawError(f"표시 시간은 {SECONDS[0]}초에서 {SECONDS[1]}초 사이")
    title = str(data.get("title") or "").strip() or DEFAULT_TITLE
    if len(title) > MAX_TITLE:
        raise DrawError(f"추첨 이름은 {MAX_TITLE}자 이내")
    position = data.get("position", "center")
    if position not in POSITIONS:
        raise DrawError("표시 위치는 center(아래 가운데), left(왼쪽 아래), right(오른쪽 아래)")
    scale = _number(data.get("scale", 100))
    if scale is None or scale != int(scale) or not SCALE[0] <= scale <= SCALE[1]:
        raise DrawError(f"표시 크기는 {SCALE[0]}%에서 {SCALE[1]}% 사이")
    return Config(enabled=bool(data.get("enabled", False)), prizes=prizes, rules=sorted(rules, key=lambda rule: rule.min_won, reverse=True),
                  exact=bool(data.get("exact", False)), members=bool(data.get("members", False)), style=style, seconds=int(seconds),
                  title=title, position=position, scale=int(scale), sound=bool(data.get("sound", False)),
                  show_percent=bool(data.get("show_percent", False)), **_look_request(data, style))


_LOOK_KEYS = ("design", "effect", "name_font", "name_size", "caption_font", "caption_size", "advice", "advice_lines")


def _look_request(data: dict[str, Any], style: str) -> dict[str, Any]:
    """모양, 효과, 글꼴, 한마디 확인. 빠진 항목은 저장한 값(모양은 연출에 없으면 그 연출의 기본 모양)."""
    kept = _look(settings.load(), style) if any(key not in data for key in _LOOK_KEYS) else {}
    designs = DESIGNS[style]
    design = data.get("design", kept.get("design"))
    if design in ("", None):
        design = next(iter(designs))
    if not isinstance(design, str) or design not in designs:
        raise DrawError(f"{STYLES[style]} 모양은 {_listed(designs)}")
    effect = data.get("effect", kept.get("effect"))
    if not isinstance(effect, str) or effect not in EFFECTS:
        raise DrawError(f"효과는 {_listed(EFFECTS)}")
    found: dict[str, Any] = {"design": design, "effect": effect}
    for key, label in (("name_font", "상품 이름 글꼴"), ("caption_font", "안내 글꼴")):
        value = data.get(key, kept.get(key))
        if not isinstance(value, str) or value not in FONTS:
            raise DrawError(f"{label}은 {_listed(FONTS)}")
        found[key] = value
    for key, label in (("name_size", "상품 이름 크기"), ("caption_size", "안내 글 크기")):
        value = data.get(key, kept.get(key))
        if not isinstance(value, str) or value not in SIZES:
            raise DrawError(f"{label}는 {_listed(SIZES)}")
        found[key] = value
    lines = data.get("advice_lines", kept.get("advice_lines"))
    if isinstance(lines, str):
        lines = lines.splitlines()
    if not isinstance(lines, list) or not all(isinstance(line, str) for line in lines):
        raise DrawError("한마디는 문장 목록")
    lines = list(dict.fromkeys(line.strip() for line in lines if line.strip()))
    if len(lines) > MAX_ADVICE:
        raise DrawError(f"한마디는 {MAX_ADVICE}개까지")
    for line in lines:
        if len(line) > MAX_ADVICE_LENGTH:
            raise DrawError(f"한마디는 한 줄에 {MAX_ADVICE_LENGTH}자 이내: {line[:10]}")
    found["advice_lines"] = lines
    found["advice"] = bool(data.get("advice", kept.get("advice", True)))
    return found


def save_config(config: Config) -> Config:
    settings.save({**settings.load(), **config.to_settings()})
    return config


# --------------------------------------------------------------------------- 추첨


def draws_for(config: Config, kind: str, amount: float, unit: str) -> int:
    """후원, 구독 하나의 추첨 횟수(0이면 추첨 안 함)."""
    if kind == "member":
        return 1 if config.members else 0
    if kind != "donation":
        return 0
    rate = WON_PER_UNIT.get(unit)
    won = amount * rate if rate is not None else None
    for rule in config.rules:
        if config.exact:
            if won is not None and round(won) == rule.min_won:
                return rule.draws
        elif rule.min_won == 0 or (won is not None and won >= rule.min_won):
            return rule.draws
    return 0


def pick(config: Config, count: int, rng: random.Random) -> list[dict[str, Any]]:
    chosen = rng.choices(config.prizes, weights=[prize.weight for prize in config.prizes], k=count)
    return [config.entry(prize) for prize in chosen]


def amount_text(kind: str, amount: float, unit: str) -> str:
    if kind == "member":
        return "구독"
    if unit == "원":
        return f"{amount:,.0f}원"
    if unit in ("별풍선", "애드벌룬"):
        return f"{unit} {amount:g}개"
    return f"{amount:g} {unit}".strip()


def script(result: dict[str, Any]) -> str:
    """읽을 문장(대본): 이름, 후원, 결과(같은 상품은 횟수로 묶음), 타로의 오늘의 한마디."""
    counts = Counter(item["name"] for item in result["draws"])
    summary = ", ".join(f"{name} {count}회" if count > 1 else name for name, count in counts.items())
    thanks = "구독 감사합니다" if result["kind"] == "member" else f"{amount_text(result['kind'], result['amount'], result['unit'])} 후원 감사합니다"
    advice = f". 오늘의 한마디 {result['advice']}" if result.get("advice") else ""
    return f"{result['name']} 님 {thanks}. 추첨 결과 {summary}{advice}"


def pick_advice(config: Config, rng: random.Random) -> str:
    """타로 연출의 오늘의 한마디. 한마디를 끄거나 다른 연출이면 빈 문자열."""
    if config.style != "tarot" or not config.advice:
        return ""
    return rng.choice(config.advice_lines or list(ADVICE))


class DrawState:
    """추첨 결과를 화면들에게 나눠 주고 최근 결과를 보관한다(메모리만)."""

    def __init__(self, history: int = 100, rng: random.Random | None = None) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[Any] = []
        self._history: deque[dict[str, Any]] = deque(maxlen=history)
        self._rng = rng or random.SystemRandom()
        self.current: dict[str, Any] = {"seq": 0, "time": 0.0}

    def run(self, config: Config, *, name: str, platform: str, kind: str, amount: float, unit: str, count: int,
            test: bool = False) -> dict[str, Any]:
        count = max(1, min(MAX_DRAWS, count))
        with self._lock:
            result: dict[str, Any] = {
                "seq": self.current["seq"] + 1, "time": round(time.time(), 3), "test": test, "name": name or "시청자", "platform": platform,
                "kind": kind, "amount": amount, "unit": unit, "count": count, "draws": pick(config, count, self._rng),
                "prizes": [config.entry(prize) for prize in config.prizes], "style": config.style, "seconds": config.seconds,
                "title": config.title, "position": config.position, "scale": config.scale, "sound": config.sound, "show_percent": config.show_percent,
                "design": config.design, "effect": config.effect, "name_font": config.name_font, "name_size": config.name_size,
                "caption_font": config.caption_font, "caption_size": config.caption_size, "advice": pick_advice(config, self._rng),
            }
            result["script"] = script(result)
            self.current = result
            self._history.appendleft(result)
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(result)
            except Exception:  # 가득 찬 대기열(멈춘 화면)
                pass
        return result

    def recent(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._history)

    def clear(self) -> None:
        with self._lock:
            self._history.clear()

    def subscribe(self, into: Any = None) -> tuple[Any, dict[str, Any]]:
        subscriber = into if into is not None else queue.Queue(maxsize=50)
        with self._lock:
            self._subscribers.append(subscriber)
            return subscriber, dict(self.current)

    def unsubscribe(self, subscriber: Any) -> None:
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)


class DrawReactor:
    """오버레이 허브에 붙여 후원, 구독 사건이 오면 저장한 설정대로 추첨. 설정은 사건마다 다시 읽는다(조작 화면에서 바꾼 값 바로 적용)."""

    def __init__(self, state: DrawState, load: Callable[[], Config] = load_config) -> None:
        self.state = state
        self._load = load

    def __call__(self, event: Any) -> None:
        kind = getattr(event, "kind", "")
        if kind not in ("donation", "member") or getattr(event, "platform", "") == "system":
            return
        config = self._load()
        if not config.enabled:
            return
        amount, unit = float(getattr(event, "amount", 0) or 0), str(getattr(event, "unit", "") or "")
        count = draws_for(config, kind, amount, unit)
        if count:
            platform = str(getattr(event, "platform", ""))
            self.state.run(config, name=str(getattr(event, "name", "")), platform=platform, kind=kind, amount=amount, unit=unit,
                           count=count, test=platform == "demo")
