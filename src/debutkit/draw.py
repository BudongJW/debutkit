"""후원 추첨 연출: 후원이 오면 상품표에서 확률대로 뽑아 방송 화면(``/draw``)에 카드 뒤집기, 룰렛 연출로 표시한다.

- 설정은 저장 설정의 ``draw_*`` 항목. 조작 화면(``/draw/control``)이나 ``debutkit draw set`` 으로 바꾸며 다음 후원부터 적용
- 상품표 ``"가중치:이름"``: 가중치는 비율(합이 100이 아니어도 됨). 확률 5% 이하는 희귀 상품으로 강조, 이름에 꽝이 있으면 꽝 표시
- 추첨 규칙 ``"최소 금액:횟수"``: 원 기준(별풍선 1개 100원, VTube Studio 후원 반응과 같은 환산). 기본은 금액 이상인 규칙 중
  금액이 가장 큰 규칙, ``exact`` 는 금액이 정확히 같은 규칙만. 원으로 환산할 수 없는 단위(Twitch bits, 외화)는 최소 금액 0 규칙만
- 구독, 멤버십은 선택하면 1회 추첨
- 추첨은 서버에서 운영체제 난수(``random.SystemRandom``)로 하고 모든 화면이 같은 결과를 표시
- 결과는 메모리에만 최근 100개 보관(파일로 저장하지 않음). 조작 화면의 최근 결과와 읽을 문장(대본)에 사용
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

STYLES = {"card": "카드 뒤집기", "wheel": "룰렛"}
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
                "members": self.members, "style": self.style, "seconds": self.seconds, "styles": STYLES}

    def to_settings(self) -> dict[str, Any]:
        return {"draw_enabled": self.enabled, "draw_prizes": [f"{prize.weight:g}:{prize.name}" for prize in self.prizes],
                "draw_rules": [f"{rule.min_won}:{rule.draws}" for rule in self.rules], "draw_exact": self.exact,
                "draw_members": self.members, "draw_style": self.style, "draw_seconds": self.seconds}


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


def load_config(saved: dict[str, Any] | None = None) -> Config:
    """저장한 추첨 설정. 상품, 규칙을 저장하지 않았으면 예시(사용 꺼짐)."""
    saved = settings.load() if saved is None else saved
    prizes = parse_prizes(saved.get("draw_prizes")) or parse_prizes(DEFAULT_PRIZES)
    rules = parse_rules(saved.get("draw_rules")) or parse_rules(DEFAULT_RULES)
    seconds = saved.get("draw_seconds", 8)
    return Config(enabled=bool(saved.get("draw_enabled", False)), prizes=prizes, rules=rules, exact=bool(saved.get("draw_exact", False)),
                  members=bool(saved.get("draw_members", False)), style=saved.get("draw_style") if saved.get("draw_style") in STYLES else "card",
                  seconds=seconds if isinstance(seconds, int) and SECONDS[0] <= seconds <= SECONDS[1] else 8)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def from_request(data: Any) -> Config:
    """조작 화면, 명령줄에서 받은 설정 확인. 틀리면 DrawError(한국어 안내)."""
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
    if style not in STYLES:
        raise DrawError("연출은 card(카드 뒤집기) 또는 wheel(룰렛)")
    seconds = _number(data.get("seconds", 8))
    if seconds is None or seconds != int(seconds) or not SECONDS[0] <= seconds <= SECONDS[1]:
        raise DrawError(f"표시 시간은 {SECONDS[0]}초에서 {SECONDS[1]}초 사이")
    return Config(enabled=bool(data.get("enabled", False)), prizes=prizes, rules=sorted(rules, key=lambda rule: rule.min_won, reverse=True),
                  exact=bool(data.get("exact", False)), members=bool(data.get("members", False)), style=style, seconds=int(seconds))


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
    """읽을 문장(대본): 이름, 후원, 결과(같은 상품은 횟수로 묶음)."""
    counts = Counter(item["name"] for item in result["draws"])
    summary = ", ".join(f"{name} {count}회" if count > 1 else name for name, count in counts.items())
    thanks = "구독 감사합니다" if result["kind"] == "member" else f"{amount_text(result['kind'], result['amount'], result['unit'])} 후원 감사합니다"
    return f"{result['name']} 님 {thanks}. 추첨 결과 {summary}"


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
