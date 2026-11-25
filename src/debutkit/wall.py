"""후원 벽: 후원이 올 때마다 카드 한 장을 방송 화면(``/wall``)의 칸에 붙여 쌓는다. 스트리머가 비울 때까지 방송이 끝나도 남는다.

- 치지직, SOOP, YouTube, Twitch 후원을 오버레이 허브에서 함께 받는다. 칸은 단위(별풍선, 애드벌룬, 원, 비트, 외화)마다 따로이고
  단위마다 칸 나누기(정확한 금액, 앞자리별 30~39개와 3만원대, 자릿수별 10~99개와 만원대, 10개 단위 등)를 고른다.
  새 단위(예: SOOP 미션)가 사건으로 들어오면 단위 이름 그대로 칸을 만든다(칸 나누기 기본은 앞자리별)
- 시그니처: 단위와 금액이 정확히 같은 후원을 그림을 붙인 큰 칸에 따로 모은다(그림에 숫자가 있으면 숫자 숨기기). 칸마다 그림도 붙일 수 있다
- 오라: 단위별 금액 단계마다 빛 번짐, 반사광, 별가루, 금박(세기 30~200%, 단계 수 제한 없음에 가깝게 100개까지)
- 카드, 설정, 칸 배치는 설정 폴더의 ``wall.json``, 올린 그림은 같은 폴더의 ``wall`` 폴더(이름은 debutkit이 만든 임의 이름).
  후원자 닉네임은 이 PC에만 저장하고 외부로 보내지 않는다. 비우기는 8초 안에 되돌릴 수 있다(되돌리기 전 카드는 메모리에만)
- 목표(``/wall/goal``)와 순위(``/wall/rank``)도 같은 카드로 계산. 순위는 원 기준(별풍선 1개 100원, vts.WON_PER_UNIT)이고
  원으로 바꿀 수 없는 단위(애드벌룬, 비트, 외화)는 따로 표시하거나 뺀다
- 방송 화면은 ``/live?feeds=wall`` (연결할 때 전체, 이후 새 카드와 바뀐 칸). 목표, 순위, 조작 화면은 짧은 조회로 확인(연결 수 절약)
"""

from __future__ import annotations

import base64
import binascii
import copy
import math
import re
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable

from . import settings
from .overlay.feature import Channel, Context, Feature, FeatureError, Raw
from .vts import WON_PER_UNIT

FILE = "wall.json"
FOLDER = "wall"
VERSION = 1
UNDO_SECONDS = 8.0
MAX_CARDS = 5000  # 넘으면 가장 오래된 카드부터 뺀다
MAX_SHOWN = 60  # 칸 하나에서 방송 화면으로 보내는 최근 카드 수(나머지는 개수로만)
MAX_NAME = 40
MAX_TITLE = 20
MAX_SIGNATURES = 30
MAX_AURAS = 100
MAX_MILESTONES = 12
MAX_COLUMN_IMAGES = 100
MAX_AMOUNT = 100_000_000
MAX_IMAGE = 8 * 1024 * 1024
IMAGE_BODY = 12_000_000  # base64(4/3배)와 JSON 여유
CANVAS = (1920, 1080)
STRENGTH = (30, 200)

#: 단위 -> (칸 이름표, 개수 뒤에 붙는 말)
UNITS = {"별풍선": ("별풍선", "개"), "애드벌룬": ("애드벌룬", "개"), "원": ("후원", "원"), "bits": ("비트", "비트")}
UNIT_ORDER = ("별풍선", "애드벌룬", "원", "bits")
FOREIGN = "외화"  # USD, JPY 같은 통화 코드(YouTube 외화 슈퍼챗)의 칸 나누기 설정
RESERVED = ("sig", "solo")
PLATFORMS = {"chzzk": "치지직", "soop": "SOOP", "twitch": "Twitch", "youtube": "YouTube", "demo": "시험"}
_CURRENCY = re.compile(r"[A-Z]{3}")  # fullmatch로만 사용
_IMAGE_NAME = re.compile(r"[0-9a-f]{24}\.(png|gif|webp|jpg)")  # debutkit이 만든 그림 이름(fullmatch로만 사용)
_IMAGE_TYPES = {"png": "image/png", "gif": "image/gif", "webp": "image/webp", "jpg": "image/jpeg"}
#: 올린 그림을 바로 열어도 아무것도 실행되지 않게
IMAGE_POLICY = "default-src 'none'; sandbox"

COUNT_MODES = {"exact": "정확한 개수", "lead": "앞자리별(30~39개, 300~399개)", "digits": "자릿수별(10~99개, 100~999개)",
               "10": "10개 단위", "100": "100개 단위", "1000": "1000개 단위"}
WON_MODES = {"exact": "정확한 금액", "lead": "앞자리별(3천원대, 3만원대)", "digits": "자릿수별(천원대, 만원대)",
             "1000": "1천원 단위", "10000": "1만원 단위", "100000": "10만원 단위"}
FOREIGN_MODES = {"exact": "정확한 금액", "lead": "앞자리별(10~19, 20~29)", "1": "1 단위", "10": "10 단위", "100": "100 단위"}
DEFAULT_BUCKETS = {"별풍선": "lead", "애드벌룬": "lead", "원": "lead", "bits": "lead", FOREIGN: "exact"}

ENTRANCES = {"pop": "톡 튀어나오기", "drop": "위에서 떨어지기", "sparkle": "반짝 등장", "stamp": "도장 찍기", "unfold": "종이 펼치기",
             "jelly": "말랑 착지", "trace": "테두리 그리기", "bubble": "비눗방울", "flip": "카드 뒤집기", "tape": "테이프 붙이기",
             "random": "무작위"}
IDLES = {"none": "없음", "bob": "통통", "float": "둥실", "pulse": "빛 숨쉬기", "flash": "반짝 지나감", "sway": "흔들흔들", "beat": "두근두근"}
AURAS = {"glow": "빛 번짐", "shimmer": "반사광", "stardust": "별가루", "gold": "금박"}
GOAL_BASES = {"won": "원 기준 합계(별풍선 1개 100원)", "별풍선": "별풍선 개수", "애드벌룬": "애드벌룬 개수", "원": "원(치지직, YouTube)", "bits": "Twitch 비트"}
OTHERS = {"separate": "따로 표시", "exclude": "빼기"}

DEFAULT_AURAS = [
    {"unit": "별풍선", "min": 100, "effect": "glow", "strength": 100}, {"unit": "별풍선", "min": 500, "effect": "shimmer", "strength": 120},
    {"unit": "별풍선", "min": 1000, "effect": "stardust", "strength": 150}, {"unit": "별풍선", "min": 10000, "effect": "gold", "strength": 180},
    {"unit": "원", "min": 10000, "effect": "glow", "strength": 100}, {"unit": "원", "min": 50000, "effect": "shimmer", "strength": 120},
    {"unit": "원", "min": 100000, "effect": "stardust", "strength": 150}, {"unit": "원", "min": 1000000, "effect": "gold", "strength": 180},
    {"unit": "애드벌룬", "min": 1000, "effect": "glow", "strength": 100}, {"unit": "애드벌룬", "min": 10000, "effect": "stardust", "strength": 150},
    {"unit": "bits", "min": 1000, "effect": "glow", "strength": 100}, {"unit": "bits", "min": 10000, "effect": "stardust", "strength": 150},
]
DEFAULT_CONFIG: dict[str, Any] = {
    "buckets": dict(DEFAULT_BUCKETS), "auras": DEFAULT_AURAS, "entrance": "pop", "idle": "float", "fast_after": 6, "sound": False,
    "names": True, "auto_clear": False, "empty_signatures": False,
    "goal": {"title": "오늘의 목표", "basis": "won", "target": 100000,
             "milestones": [{"at": 30000, "label": ""}, {"at": 60000, "label": ""}]},
    "rank": {"title": "후원 순위", "count": 5, "others": "separate"},
    "signatures": [], "columns": {},
}

# 칸 크기(1920x1080 기준). 칸 머리와 카드 크기는 wall.css와 맞춘다
MARGIN, GAP = 40, 18
COLUMN_W, SIGNATURE_W = 200, 270
MIN_W, MIN_H = 120, 160


class WallError(FeatureError):
    """잘못된 후원 벽 요청. 메시지는 한국어 안내."""


# --------------------------------------------------------------------------- 숫자, 단위


def number_text(value: float) -> str:
    """1,234 또는 4.99 (소수 둘째 자리까지, 끝의 0은 뺌)."""
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value)):,}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def won_short(value: float) -> str:
    """원 금액 줄임: 12000 -> 1만 2천, 50000 -> 5만, 1234 -> 1,234."""
    n = int(round(value))
    eok, n = divmod(n, 100_000_000)
    man, n = divmod(n, 10_000)
    parts = [f"{eok:,}억"] if eok else []
    if man:
        parts.append(f"{man:,}만")
    if n:
        parts.append(f"{n // 1000}천" if n % 1000 == 0 else f"{n:,}")
    return " ".join(parts) or "0"


def is_currency(unit: str) -> bool:
    return bool(_CURRENCY.fullmatch(unit))


def unit_of(raw: Any) -> str | None:
    """사건의 단위를 칸 단위로: 원, 별풍선, 애드벌룬, bits, 통화 코드(USD), 그 밖의 짧은 이름(앞으로 생길 단위). 쓸 수 없으면 None."""
    unit = str(raw or "").strip()
    if unit in UNITS:
        return unit
    if unit.upper() == "KRW":
        return "원"
    if unit.lower() == "bits":
        return "bits"
    if not unit or len(unit) > 10 or unit.lower() in RESERVED or unit == FOREIGN or any(char in unit for char in "/\\\n\r\t"):
        return None
    if re.fullmatch(r"[A-Za-z]{3}", unit):
        return unit.upper()
    return unit


def group_of(unit: str) -> str:
    """칸 나누기 설정을 찾는 이름: 통화 코드는 모두 외화."""
    return FOREIGN if is_currency(unit) else unit


def modes_for(unit: str) -> dict[str, str]:
    if unit == "원":
        return WON_MODES
    if unit == FOREIGN or is_currency(unit):
        return FOREIGN_MODES
    return COUNT_MODES


def suffix_of(unit: str) -> str:
    return UNITS.get(unit, ("", ""))[1]


def tag_of(unit: str) -> str:
    return UNITS.get(unit, (unit, ""))[0]


def amount_text(amount: float, unit: str) -> str:
    """카드에 쓰는 짧은 금액: 34개, 5,000원, 500비트, USD 4.99, 미션 3."""
    if unit in UNITS:
        return f"{number_text(amount)}{suffix_of(unit)}"
    return f"{unit} {number_text(amount)}"


def long_amount(amount: float, unit: str) -> str:
    """단위 이름까지: 별풍선 34개, 5,000원, 500비트, USD 4.99."""
    if unit in ("별풍선", "애드벌룬"):
        return f"{unit} {number_text(amount)}개"
    return amount_text(amount, unit)


def won_of(amount: float, unit: str) -> float | None:
    rate = WON_PER_UNIT.get(unit)
    return amount * rate if rate is not None else None


def _magnitude(amount: float) -> int:
    return 10 ** (len(str(int(amount))) - 1)


# --------------------------------------------------------------------------- 칸 나누기, 시그니처, 오라


def bucket_key(unit: str, amount: float, mode: str) -> str:
    """칸 이름(``단위/간격/시작``). 간격 0은 정확한 금액, d는 자릿수별. 같은 구간이면 방식이 달라도 같은 이름(배치 유지)."""
    if mode == "exact" or amount < 1:
        return f"{unit}/0/{number_text(amount).replace(',', '')}"
    magnitude = _magnitude(amount)
    if mode == "digits":
        return f"{unit}/d/{magnitude}"
    step = magnitude if mode == "lead" else int(mode)
    low = math.floor(amount / step + 1e-9) * step
    return f"{unit}/{step}/{low}"


def signature_for(unit: str, amount: float, signatures: list[dict[str, Any]]) -> dict[str, Any] | None:
    for signature in signatures:
        if signature["unit"] == unit and abs(signature["amount"] - amount) < 0.005:
            return signature
    return None


def natural_column(card: dict[str, Any], config: dict[str, Any]) -> str:
    """옮기지 않은 카드가 들어갈 칸: 시그니처 금액이면 시그니처 칸, 아니면 단위의 칸 나누기."""
    signature = signature_for(card["unit"], card["amount"], config["signatures"])
    if signature is not None:
        return f"sig/{signature['id']}"
    mode = config["buckets"].get(group_of(card["unit"]), "lead")
    return bucket_key(card["unit"], card["amount"], mode)


def _label(unit: str, step: str, low: float) -> tuple[str, str]:
    """칸 머리의 큰 숫자와 뒤에 붙는 말."""
    money, decimals, suffix = unit == "원", is_currency(unit), suffix_of(unit)
    edge = 0.01 if decimals else 1
    if step == "0":
        return number_text(low), suffix
    if step == "d":
        if low >= 1000 and not decimals:  # 천원대, 만개대
            places = {1000: "천", 10_000: "만", 100_000: "십만", 1_000_000: "백만", 10_000_000: "천만"}
            return places.get(int(low), won_short(low)), f"{suffix}대"
        return f"{number_text(low)}~{number_text(low * 10 - edge)}", suffix
    size = float(step)
    if not decimals and (size >= 1000 or (money and size >= 100)):  # 3만원대, 1천개대(긴 범위 대신)
        return (won_short(size), f"{suffix} 미만") if low == 0 else (won_short(low), f"{suffix}대")
    if size == 1 and not decimals:
        return number_text(low), suffix
    return f"{number_text(low if low > 0 else edge)}~{number_text(low + size - edge)}", suffix


def column_info(key: str, config: dict[str, Any], cards: dict[int, dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """칸 이름을 화면 정보로(이름표, 큰 숫자, 그림). 알 수 없거나 사라진 칸(지운 시그니처 등)은 None."""
    head, _, rest = key.partition("/")
    image = (config["columns"].get(key) or {}).get("image", "")
    if head == "sig":
        signature = next((item for item in config["signatures"] if item["id"] == rest), None)
        if signature is None:
            return None
        number, suffix = number_text(signature["amount"]), suffix_of(signature["unit"])
        if signature["unit"] not in UNITS:
            number, suffix = amount_text(signature["amount"], signature["unit"]), ""
        return {"key": key, "kind": "sig", "unit": signature["unit"], "tag": "시그니처", "title": signature["title"], "number": number,
                "suffix": suffix, "hide_number": signature["hide_number"], "image": signature["image"] or image,
                "sort": (0, _unit_rank(signature["unit"]), -signature["amount"], "")}
    if head == "solo":
        card = (cards or {}).get(int(rest)) if rest.isdigit() else None
        if card is None:
            return None
        return {"key": key, "kind": "solo", "unit": card["unit"], "tag": "따로", "title": "", "number": number_text(card["amount"]),
                "suffix": suffix_of(card["unit"]) if card["unit"] in UNITS else card["unit"], "hide_number": False, "image": image,
                "sort": (2, 0, -card["id"], "")}
    step, _, low_text = rest.partition("/")
    unit = unit_of(head)
    if unit != head or not (step in ("0", "d") or re.fullmatch(r"\d+", step)):
        return None
    try:
        low = float(low_text)
    except ValueError:
        return None
    number, suffix = _label(unit, step, low)
    return {"key": key, "kind": "bucket", "unit": unit, "tag": tag_of(unit), "title": "", "number": number, "suffix": suffix,
            "hide_number": False, "image": image, "sort": (1, _unit_rank(unit), -low, step)}


def _unit_rank(unit: str) -> tuple[int, str]:
    return (UNIT_ORDER.index(unit), "") if unit in UNIT_ORDER else (len(UNIT_ORDER) + (0 if is_currency(unit) else 1), unit)


def aura_for(unit: str, amount: float, tiers: list[dict[str, Any]]) -> dict[str, Any] | None:
    """단위가 같은 단계 중 금액 이하에서 가장 높은 단계. ``tier`` 는 몇 번째 단계(1부터), ``tiers`` 는 그 단위의 단계 수."""
    own = sorted((tier for tier in tiers if tier["unit"] == unit), key=lambda tier: tier["min"])
    chosen, rank = None, 0
    for index, tier in enumerate(own):
        if amount >= tier["min"]:
            chosen, rank = tier, index + 1
    if chosen is None:
        return None
    return {"effect": chosen["effect"], "strength": chosen["strength"], "tier": rank, "tiers": len(own)}


# --------------------------------------------------------------------------- 칸 배치


def arrange(columns: list[dict[str, Any]], layout: dict[str, dict[str, int]]) -> None:
    """칸 위치와 크기(x, y, w, h)를 채운다. 저장한 배치(끌어 옮긴 칸)는 그대로, 나머지는 왼쪽 위부터 줄을 바꿔 가며 놓는다.

    칸이 많으면 3줄 안에 들어가도록 폭을 줄이고, 줄 수에 맞춰 높이를 나눈다.
    """
    auto = []
    for column in columns:
        saved = layout.get(column["key"])
        if saved:
            column.update(saved, pinned=True)
        else:
            column["pinned"] = False
            auto.append(column)
    if not auto:
        return
    width = CANVAS[0] - 2 * MARGIN
    for scale in (1.0, 0.9, 0.8, 0.7, 0.62):
        sizes = [round((SIGNATURE_W if column["kind"] == "sig" else COLUMN_W) * scale) for column in auto]
        rows: list[list[int]] = [[]]
        used = 0
        for index, size in enumerate(sizes):
            if rows[-1] and used + GAP + size > width:
                rows.append([])
                used = 0
            used += (GAP if rows[-1] else 0) + size
            rows[-1].append(index)
        if len(rows) <= 3:
            break
    height = max(MIN_H, (CANVAS[1] - 2 * MARGIN - (len(rows) - 1) * GAP) // len(rows))
    for number, row in enumerate(rows):
        x = MARGIN
        for index in row:
            auto[index].update(x=x, y=MARGIN + number * (height + GAP), w=sizes[index], h=height)
            x += sizes[index] + GAP


# --------------------------------------------------------------------------- 목표, 순위, 내보내기


def goal_progress(cards: list[dict[str, Any]], goal: dict[str, Any]) -> dict[str, Any]:
    """목표 게이지: 원 기준 합계(원으로 바꿀 수 있는 후원) 또는 한 단위의 합."""
    basis = goal["basis"]
    if basis == "won":
        current = sum(won for card in cards if (won := won_of(card["amount"], card["unit"])) is not None)
        suffix, unit = "원", "원"
    else:
        current = sum(card["amount"] for card in cards if card["unit"] == basis)
        suffix, unit = suffix_of(basis), basis
    target = goal["target"]
    percent = round(min(current / target * 100, 9999.0), 1) if target else 0.0
    milestones = [{"at": item["at"], "label": item["label"], "reached": current >= item["at"], "position": round(min(item["at"] / target, 1) * 100, 2),
                   "text": amount_text(item["at"], unit)} for item in sorted(goal["milestones"], key=lambda item: item["at"])]
    upcoming = next((item for item in milestones if not item["reached"]), None)
    return {"title": goal["title"], "basis": basis, "basis_label": GOAL_BASES.get(basis, basis), "current": current, "target": target,
            "percent": percent, "reached": current >= target, "suffix": suffix, "current_text": number_text(current),
            "target_text": number_text(target) + suffix, "milestones": milestones, "next": upcoming}


def ranking(cards: list[dict[str, Any]], rank: dict[str, Any]) -> dict[str, Any]:
    """후원 순위: 같은 플랫폼의 같은 닉네임을 한 사람으로 원 기준 합계. 같은 합계는 같은 순위(먼저 후원한 사람이 위).

    원으로 바꿀 수 없는 단위(애드벌룬, 비트, 외화)는 ``others`` (따로 표시 선택일 때만)에 단위별 합계로.
    """
    totals: dict[tuple[str, str], dict[str, Any]] = {}
    others: dict[tuple[str, str, str], dict[str, Any]] = {}
    excluded = 0
    for card in cards:
        won = won_of(card["amount"], card["unit"])
        if won is None:
            excluded += 1
            entry = others.setdefault((card["platform"], card["name"], card["unit"]), {"name": card["name"], "platform": card["platform"],
                                                                                      "unit": card["unit"], "amount": 0.0, "count": 0})
            entry["amount"] += card["amount"]
            entry["count"] += 1
            continue
        entry = totals.setdefault((card["platform"], card["name"]), {"name": card["name"], "platform": card["platform"], "won": 0.0, "count": 0,
                                                                     "first": card["id"]})
        entry["won"] += won
        entry["count"] += 1
    ordered = sorted(totals.values(), key=lambda entry: (-entry["won"], entry["first"]))[: rank["count"]]
    entries = []
    for index, entry in enumerate(ordered):
        place = entries[-1]["rank"] if entries and abs(entries[-1]["won"] - entry["won"]) < 0.5 else index + 1
        entries.append({"rank": place, "name": entry["name"], "platform": entry["platform"], "won": entry["won"], "count": entry["count"],
                        "text": f"{number_text(entry['won'])}원", "key": f"{entry['platform']}/{entry['name']}"})
    other_list = []
    if rank["others"] == "separate":
        for entry in sorted(others.values(), key=lambda entry: (_unit_rank(entry["unit"]), -entry["amount"]))[: rank["count"]]:
            other_list.append({**entry, "text": long_amount(entry["amount"], entry["unit"]), "key": f"{entry['platform']}/{entry['name']}/{entry['unit']}"})
    return {"title": rank["title"], "count": rank["count"], "others_mode": rank["others"], "entries": entries, "others": other_list,
            "excluded": excluded, "basis": "원 기준(별풍선 1개 100원)"}


def export_text(cards: list[dict[str, Any]], columns: list[dict[str, Any]], now: float | None = None) -> str:
    """벽 기록 글: 단위별 후원자 건수와 합계, 칸별 건수. 시험 카드도 포함(표시)."""
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(now if now is not None else time.time()))
    lines = [f"debutkit 후원 벽 기록({stamp} 기준, 카드 {len(cards)}장)"]
    if not cards:
        return "\n".join([*lines, "", "카드 없음"]) + "\n"
    units = sorted({card["unit"] for card in cards}, key=_unit_rank)
    for unit in units:
        own = [card for card in cards if card["unit"] == unit]
        donors: dict[tuple[str, str], dict[str, Any]] = {}
        for card in own:
            entry = donors.setdefault((card["platform"], card["name"]), {"count": 0, "amount": 0.0, "tests": 0})
            entry["count"] += 1
            entry["amount"] += card["amount"]
            entry["tests"] += 1 if card.get("test") else 0
        lines += ["", f"[{tag_of(unit) if unit in UNITS else unit}] {len(own)}건, 합계 {long_amount(sum(card['amount'] for card in own), unit)}"]
        ordered = sorted(donors.items(), key=lambda item: (-item[1]["amount"], item[0][1]))
        for place, ((platform, name), entry) in enumerate(ordered, 1):
            test = " 시험" if entry["tests"] == entry["count"] else ""
            lines.append(f"{place}. {name}({PLATFORMS.get(platform, platform)}{test}) {entry['count']}건, {long_amount(entry['amount'], unit)}")
    lines += ["", "[칸별 건수]"]
    for column in columns:
        name = column["title"] or f"{column['tag']} {column['number']}{column['suffix']}"
        lines.append(f"{name}: {column['count']}건")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- 설정 확인


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        found = float(str(value).replace(",", "")) if isinstance(value, str) else float(value)
    except ValueError:
        return None
    return found if math.isfinite(found) else None


def _text(value: Any, limit: int, what: str) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]", "", str(value or "")).strip()
    if len(text) > limit:
        raise WallError(f"{what}은 {limit}자 이내")
    return text


def _flag(data: dict[str, Any], name: str) -> bool:
    if not isinstance(data[name], bool):
        raise WallError(f"{name} 값은 참 또는 거짓")
    return data[name]


def _config_unit(value: Any, *, foreign: bool = False) -> str:
    raw = str(value or "").strip()
    if foreign and raw == FOREIGN:
        return FOREIGN
    unit = unit_of(raw)
    if unit is None or (unit != raw and unit != raw.upper()):
        raise WallError(f"알 수 없는 단위: {raw[:12] or '(비어 있음)'}")
    return unit


def _buckets(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise WallError("칸 나누기 형식이 올바르지 않음")
    found = dict(DEFAULT_BUCKETS)
    for raw, mode in value.items():
        unit = _config_unit(raw, foreign=True)
        if mode not in modes_for(unit):
            raise WallError(f"칸 나누기 방식이 올바르지 않음: {unit}")
        found[unit] = mode
    return found


def _auras(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise WallError("오라 단계 형식이 올바르지 않음")
    if len(value) > MAX_AURAS:
        raise WallError(f"오라 단계는 {MAX_AURAS}개까지")
    found: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise WallError("오라 단계 형식이 올바르지 않음")
        unit = _config_unit(item.get("unit"))
        minimum = _number(item.get("min"))
        if minimum is None or not 0 < minimum <= MAX_AMOUNT:
            raise WallError(f"오라 단계의 금액은 0보다 큰 숫자: {unit}")
        if item.get("effect") not in AURAS:
            raise WallError("오라 효과는 glow(빛 번짐), shimmer(반사광), stardust(별가루), gold(금박)")
        strength = _number(item.get("strength", 100))
        if strength is None or strength != int(strength) or not STRENGTH[0] <= strength <= STRENGTH[1]:
            raise WallError(f"오라 세기는 {STRENGTH[0]}%에서 {STRENGTH[1]}% 사이의 정수")
        if any(tier["unit"] == unit and tier["min"] == minimum for tier in found):
            raise WallError(f"같은 단위, 같은 금액의 오라 단계가 2개: {long_amount(minimum, unit)}")
        found.append({"unit": unit, "min": minimum, "effect": item["effect"], "strength": int(strength)})
    return sorted(found, key=lambda tier: (_unit_rank(tier["unit"]), tier["min"]))


def _goal(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WallError("목표 형식이 올바르지 않음")
    title = _text(value.get("title"), MAX_TITLE, "목표 이름") or DEFAULT_CONFIG["goal"]["title"]
    basis = value.get("basis", "won")
    if basis not in GOAL_BASES:
        raise WallError("목표 기준은 won(원 기준 합계), 별풍선, 애드벌룬, 원, bits")
    target = _number(value.get("target"))
    if target is None or not 0 < target <= MAX_AMOUNT * 100:
        raise WallError("목표는 0보다 큰 숫자")
    raw = value.get("milestones", [])
    if not isinstance(raw, list) or len(raw) > MAX_MILESTONES:
        raise WallError(f"중간 목표는 {MAX_MILESTONES}개까지")
    milestones = []
    for item in raw:
        at = _number(item.get("at") if isinstance(item, dict) else None)
        if at is None or not 0 < at <= target:
            raise WallError("중간 목표는 0보다 크고 목표 이하인 숫자")
        if at in {milestone["at"] for milestone in milestones}:
            raise WallError(f"같은 금액의 중간 목표가 2개: {number_text(at)}")
        milestones.append({"at": at, "label": _text(item.get("label"), MAX_TITLE, "중간 목표 이름")})
    return {"title": title, "basis": basis, "target": target, "milestones": sorted(milestones, key=lambda item: item["at"])}


def _rank(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WallError("순위 형식이 올바르지 않음")
    count = _number(value.get("count", 5))
    if count is None or count != int(count) or not 1 <= count <= 20:
        raise WallError("순위 인원은 1에서 20 사이의 정수")
    others = value.get("others", "separate")
    if others not in OTHERS:
        raise WallError("원으로 바꿀 수 없는 후원은 separate(따로 표시) 또는 exclude(빼기)")
    return {"title": _text(value.get("title"), MAX_TITLE, "순위 이름") or DEFAULT_CONFIG["rank"]["title"], "count": int(count), "others": others}


def _choice(table: dict[str, str], what: str) -> Callable[[Any], str]:
    def check(value: Any) -> str:
        if value not in table:
            raise WallError(f"{what}: " + ", ".join(f"{key}({label})" for key, label in table.items()))
        return str(value)
    return check


def _fast_after(value: Any) -> int:
    found = _number(value)
    if found is None or found != int(found) or not 2 <= found <= 50:
        raise WallError("빠른 진행 기준은 대기 카드 2장에서 50장 사이")
    return int(found)


#: 조작 화면, 명령줄이 바꿀 수 있는 설정(시그니처, 칸 그림은 따로 저장)
_FIELDS: dict[str, Callable[[Any], Any]] = {
    "buckets": _buckets, "auras": _auras, "goal": _goal, "rank": _rank, "entrance": _choice(ENTRANCES, "등장 연출은"),
    "idle": _choice(IDLES, "대기 효과는"), "fast_after": _fast_after,
}
_FLAGS = ("sound", "names", "auto_clear", "empty_signatures")


def update_config(config: dict[str, Any], data: Any) -> dict[str, Any]:
    """받은 항목만 확인해 바꾼 새 설정. 틀리면 WallError(한국어 안내)."""
    if not isinstance(data, dict):
        raise WallError("설정 형식이 올바르지 않음")
    found = copy.deepcopy(config)
    for name, check in _FIELDS.items():
        if name in data:
            found[name] = check(data[name])
    for name in _FLAGS:
        if name in data:
            found[name] = _flag(data, name)
    return found


def load_config(saved: Any) -> dict[str, Any]:
    """저장한 설정. 형식이 틀린 항목은 기본값(항목별로)."""
    config = copy.deepcopy(DEFAULT_CONFIG)
    if not isinstance(saved, dict):
        return config
    for name in [*_FIELDS, *_FLAGS]:
        if name in saved:
            try:
                config = update_config(config, {name: saved[name]})
            except WallError:
                pass
    config["signatures"] = _saved_signatures(saved.get("signatures"))
    columns = saved.get("columns")
    if isinstance(columns, dict):
        config["columns"] = {str(key): {"image": value["image"]} for key, value in list(columns.items())[:MAX_COLUMN_IMAGES]
                             if isinstance(value, dict) and _IMAGE_NAME.fullmatch(str(value.get("image", "")))}
    return config


def _saved_signatures(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for item in value if isinstance(value, list) else []:
        try:
            signature = _signature(item, found)
        except WallError:
            continue
        if isinstance(item, dict) and re.fullmatch(r"[0-9a-f]{8}", str(item.get("id", ""))):
            signature["id"] = item["id"]
        image = str(item.get("image") or "") if isinstance(item, dict) else ""
        signature["image"] = image if _IMAGE_NAME.fullmatch(image) else ""
        found.append(signature)
    return found[:MAX_SIGNATURES]


def _signature(item: Any, others: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise WallError("시그니처 형식이 올바르지 않음")
    unit = _config_unit(item.get("unit"))
    amount = _number(item.get("amount"))
    if amount is None or not 0 < amount <= MAX_AMOUNT:
        raise WallError("시그니처 금액은 0보다 큰 숫자")
    amount = round(amount, 2)
    if signature_for(unit, amount, [other for other in others if other.get("id") != item.get("id")]):
        raise WallError(f"같은 금액의 시그니처가 이미 있음: {long_amount(amount, unit)}")
    hide = item.get("hide_number", False)
    if not isinstance(hide, bool):
        raise WallError("숫자 숨기기 값은 참 또는 거짓")
    return {"id": secrets.token_hex(4), "unit": unit, "amount": amount, "title": _text(item.get("title"), MAX_TITLE, "시그니처 이름"),
            "hide_number": hide, "image": ""}


# --------------------------------------------------------------------------- 그림


def image_kind(data: bytes) -> str | None:
    """파일 앞부분(매직 바이트)으로 PNG, GIF, WebP, JPEG 판별. 이름, 확장자는 믿지 않는다."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    return None


def decode_image(value: Any) -> tuple[bytes, str]:
    """조작 화면이 보낸 base64(``data:...;base64,`` 앞부분 허용). 틀리면 WallError."""
    if not isinstance(value, str) or not value:
        raise WallError("그림 파일이 비어 있음")
    if value.startswith("data:"):
        value = value.partition(",")[2]
    try:
        data = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise WallError("그림 파일을 읽지 못함") from error
    if len(data) > MAX_IMAGE:
        raise WallError(f"그림 파일은 {MAX_IMAGE // (1024 * 1024)}MB 이하")
    kind = image_kind(data)
    if kind is None:
        raise WallError("그림은 PNG, GIF, WebP, JPEG만")
    return data, kind


def image_folder() -> Path:
    return settings.settings_path().parent / FOLDER


def image_path(name: str) -> Path | None:
    """저장한 그림 경로. debutkit이 만든 이름 형식만(경로, 다른 파일 차단)."""
    if not isinstance(name, str) or not _IMAGE_NAME.fullmatch(name):
        return None
    path = image_folder() / name
    return path if path.is_file() else None


# --------------------------------------------------------------------------- 상태


class _Feed(Channel):
    """새로 연결한 화면에는 그 순간의 벽 전체를 보낸다(마지막 값을 들고 있지 않음)."""

    def __init__(self, snapshot: Callable[[], dict[str, Any]]) -> None:
        super().__init__({"seq": 0}, size=400)
        self._snapshot = snapshot

    def subscribe(self, into: Any = None) -> tuple[Any, dict[str, Any]]:
        subscriber, _ = super().subscribe(into)
        return subscriber, self._snapshot()


def _clean_card(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict) or not isinstance(item.get("id"), int) or isinstance(item.get("id"), bool):
        return None
    amount, unit = _number(item.get("amount")), unit_of(item.get("unit"))
    if amount is None or amount <= 0 or unit is None:
        return None
    when = _number(item.get("time"))
    card: dict[str, Any] = {"id": item["id"], "name": str(item.get("name") or "")[:MAX_NAME], "amount": amount, "unit": unit,
                            "platform": str(item.get("platform") or "")[:20], "time": when or 0.0}
    if item.get("test") is True:
        card["test"] = True
    if isinstance(item.get("column"), str) and item["column"]:
        card["column"] = item["column"][:80]
    return card


def _clean_layout(value: Any) -> dict[str, dict[str, int]]:
    found = {}
    for key, box in (value.items() if isinstance(value, dict) else []):
        try:
            found[str(key)[:80]] = _box(box)
        except WallError:
            continue
    return found


def _box(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        raise WallError("칸 위치 형식이 올바르지 않음")
    numbers = {name: _number(value.get(name)) for name in ("x", "y", "w", "h")}
    if any(number is None for number in numbers.values()):
        raise WallError("칸 위치와 크기는 숫자(x, y, w, h)")
    x, y, w, h = (int(round(numbers[name] or 0)) for name in ("x", "y", "w", "h"))
    # 칸은 1920x1080 무대 안에(아래로 옮기면 높이를 줄여 맞춤)
    w = max(MIN_W, min(CANVAS[0], w))
    x = max(0, min(CANVAS[0] - w, x))
    y = max(0, min(CANVAS[1] - MIN_H, y))
    return {"x": x, "y": y, "w": w, "h": max(MIN_H, min(CANVAS[1] - y, h))}


class Wall:
    """후원 벽의 카드, 설정, 배치. 바뀌면 화면들에게 알리고 ``wall.json`` 에 저장한다.

    카드 추가(허브 사건)는 잠시 모았다가 저장하고, 조작 화면의 변경은 바로 저장한다(실패하면 OSError).
    """

    def __init__(self, *, notify: Callable[[str], None] | None = None, clock: Callable[[], float] = time.monotonic,
                 delay: float = 0.4, starting: bool = True) -> None:
        self._lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._notify = notify or (lambda text: None)
        self._clock = clock
        self._delay = delay
        self._timer: threading.Timer | None = None
        self._dirty = False
        self._version = self._written = 0
        self._undo: tuple[list[dict[str, Any]], float] | None = None
        self._last: int | None = None  # 마지막으로 붙인 카드(다시 보기)
        saved = settings.load_data(FILE)
        self.config = load_config(saved.get("config"))
        self.layout = _clean_layout(saved.get("layout"))
        self.cards = [card for card in map(_clean_card, saved.get("cards") or []) if card is not None][-MAX_CARDS:]
        seq = saved.get("seq")
        self.seq = max([seq if isinstance(seq, int) and not isinstance(seq, bool) else 0, *(card["id"] for card in self.cards)])
        self.rev = 0
        self.feed = _Feed(lambda: self.view(kind="state"))
        if starting and self.config["auto_clear"] and self.cards:
            count = len(self.cards)
            self.clear()
            self._notify(f"후원 벽: 오버레이 시작 때 비움({count}장, 조작 화면에서 {UNDO_SECONDS:.0f}초 안에 되돌리기)")

    # ------------------------------------------------------------------ 저장
    def _snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"version": VERSION, "seq": self.seq, "config": copy.deepcopy(self.config), "layout": copy.deepcopy(self.layout),
                    "cards": [dict(card) for card in self.cards]}

    def _write(self) -> None:
        """지금 상태를 파일로. 쓰는 동안 다른 쓰기가 끼면 더 새 상태만 남는다(오래된 상태로 덮지 않음)."""
        with self._lock:
            self._dirty = False
            self._version += 1
            version = self._version
            values = self._snapshot()
        with self._write_lock:
            if version < self._written:
                return
            settings.save_data(FILE, values)
            self._written = version

    def _save_soon(self) -> None:
        with self._lock:
            self._dirty = True
            if self._timer is not None:
                return
            self._timer = threading.Timer(self._delay, self._background_write)
            self._timer.daemon = True
            self._timer.start()

    def _background_write(self) -> None:
        with self._lock:
            self._timer = None
        try:
            self._write()
        except OSError as error:
            self._notify(f"후원 벽 저장 실패: {error}")

    def _save_now(self) -> None:
        with self._lock:
            timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()
        self._write()

    def flush(self) -> None:
        """모아 둔 변경을 바로 저장(서버를 멈출 때)."""
        with self._lock:
            dirty = self._dirty or self._timer is not None
        if dirty:
            try:
                self._save_now()
            except OSError as error:
                self._notify(f"후원 벽 저장 실패: {error}")

    stop = flush

    # ------------------------------------------------------------------ 화면 정보
    def _columns(self) -> tuple[list[dict[str, Any]], dict[int, str]]:
        """지금 있는 칸들(배치 포함)과 카드마다 들어갈 칸."""
        by_id = {card["id"]: card for card in self.cards}
        natural = {card["id"]: natural_column(card, self.config) for card in self.cards}
        infos: dict[str, dict[str, Any]] = {}

        def info(key: str) -> dict[str, Any] | None:
            if key not in infos:
                found = column_info(key, self.config, by_id)
                if found is None:
                    return None
                infos[key] = {**found, "count": 0}
            return infos[key]

        placed: dict[int, str] = {}
        for card in self.cards:
            target = card.get("column")
            key = natural[card["id"]]
            # 옮긴 칸이 아직 있으면 그 칸(따로 세운 칸은 그 카드의 칸만)
            if target and not (target.startswith("solo/") and target != f"solo/{card['id']}") and info(target) is not None:
                key = target
            if info(key) is None:  # 칸 이름을 읽지 못하는 카드(없음에 가깝게): 정확한 금액 칸
                key = bucket_key(card["unit"], card["amount"], "exact")
                info(key)
            infos[key]["count"] += 1
            placed[card["id"]] = key
        if self.config["empty_signatures"]:
            for signature in self.config["signatures"]:
                info(f"sig/{signature['id']}")
        columns = sorted(infos.values(), key=lambda column: column["sort"])
        for column in columns:
            del column["sort"]
            column["image"] = f"/wall/image?name={column['image']}" if column["image"] else ""
        arrange(columns, self.layout)
        return columns, placed

    def _card_view(self, card: dict[str, Any], column: str, names: bool) -> dict[str, Any]:
        return {"id": card["id"], "name": card["name"] if names else "", "amount": card["amount"], "unit": card["unit"],
                "platform": card["platform"], "time": card["time"], "test": bool(card.get("test")), "column": column,
                "detached": bool(card.get("column")) and column == card.get("column"), "text": amount_text(card["amount"], card["unit"]),
                "aura": aura_for(card["unit"], card["amount"], self.config["auras"])}

    def _options(self) -> dict[str, Any]:
        return {name: self.config[name] for name in ("entrance", "idle", "fast_after", "sound", "names")}

    def view(self, *, kind: str = "state", names: bool | None = None, part: str = "") -> dict[str, Any]:
        """방송 화면이 받는 값. 이름 숨기기를 켜면 닉네임을 빼고 보낸다. ``part`` 가 goal, rank면 그 부분만."""
        with self._lock:
            show = self.config["names"] if names is None else names
            if part == "goal":
                return {"rev": self.rev, "goal": goal_progress(self.cards, self.config["goal"])}
            if part == "rank":
                return {"rev": self.rev, "rank": self._rank(show)}
            columns, placed = self._columns()
            shown: list[dict[str, Any]] = []
            per_column: dict[str, int] = {}
            for card in reversed(self.cards):
                key = placed[card["id"]]
                if per_column.get(key, 0) < MAX_SHOWN:
                    per_column[key] = per_column.get(key, 0) + 1
                    shown.append(self._card_view(card, key, show))
            shown.reverse()
            return {"type": kind, "rev": self.rev, "options": self._options(), "columns": columns, "cards": shown}

    def _rank(self, names: bool) -> dict[str, Any]:
        found = ranking(self.cards, self.config["rank"])
        if not names:
            for entry in [*found["entries"], *found["others"]]:
                entry["name"] = ""
        return found

    def _publish(self, message: dict[str, Any] | None = None) -> None:
        """바뀐 내용을 방송 화면에 알린다. 기본은 벽 전체."""
        with self._lock:
            self.rev += 1
            value = message if message is not None else self.view(kind="state")
            value["rev"] = self.rev
        self.feed.publish(value, keep=False)

    def status(self) -> dict[str, Any]:
        """조작 화면: 설정, 선택지, 칸 목록, 최근 카드(닉네임 포함), 되돌리기 남은 시간, 목표와 순위."""
        with self._lock:
            columns, placed = self._columns()
            recent = [self._card_view(card, placed[card["id"]], True) for card in reversed(self.cards[-80:])]
            units: dict[str, dict[str, Any]] = {}
            for card in self.cards:
                entry = units.setdefault(card["unit"], {"unit": card["unit"], "count": 0, "amount": 0.0})
                entry["count"] += 1
                entry["amount"] += card["amount"]
            undo = 0.0
            if self._undo is not None:
                undo = max(0.0, self._undo[1] - self._clock())
            unit_names = [*UNIT_ORDER, *sorted({card["unit"] for card in self.cards if card["unit"] not in UNITS})]
            return {
                "config": copy.deepcopy(self.config), "columns": columns, "cards": recent, "rev": self.rev,
                "summary": {"cards": len(self.cards), "columns": len(columns), "tests": sum(1 for card in self.cards if card.get("test")),
                            "units": [{**entry, "text": long_amount(entry["amount"], entry["unit"])}
                                      for entry in sorted(units.values(), key=lambda entry: _unit_rank(entry["unit"]))]},
                "undo": round(undo, 1), "undo_count": len(self._undo[0]) if self._undo and undo > 0 else 0, "last": self._last,
                "goal": goal_progress(self.cards, self.config["goal"]), "rank": self._rank(True),
                "choices": {"units": unit_names, "buckets": {unit: modes_for(unit) for unit in [*UNIT_ORDER, FOREIGN]}, "entrances": ENTRANCES,
                            "idles": IDLES, "auras": AURAS, "goal_bases": GOAL_BASES, "others": OTHERS, "platforms": PLATFORMS},
                "file": str(settings.data_path(FILE)),
            }

    # ------------------------------------------------------------------ 카드
    def add(self, name: str, amount: float, unit: str, platform: str, when: float | None = None, *, test: bool = False) -> dict[str, Any] | None:
        """카드 한 장. 단위를 쓸 수 없거나 금액이 0 이하이면 None."""
        found = unit_of(unit)
        if found is None or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount <= 0:
            return None
        clean_name = re.sub(r"[\x00-\x1f\x7f]", "", str(name or "")).strip()[:MAX_NAME] or "익명"
        with self._lock:
            self.seq += 1
            card: dict[str, Any] = {"id": self.seq, "name": clean_name, "amount": round(float(min(amount, MAX_AMOUNT)), 2), "unit": found,
                                    "platform": str(platform or "")[:20], "time": round(when if when else time.time(), 3)}
            if test:
                card["test"] = True
            self.cards.append(card)
            if len(self.cards) > MAX_CARDS:
                del self.cards[: len(self.cards) - MAX_CARDS]
            self._last = card["id"]
            columns, placed = self._columns()
            message = {"type": "add", "options": self._options(), "columns": columns,
                       "card": self._card_view(card, placed[card["id"]], self.config["names"])}
        self._publish(message)
        self._save_soon()
        return card

    def tap(self, event: Any) -> None:
        """오버레이 허브의 사건: 후원만(시스템 알림, 채팅, 구독 제외). 시험 사건(demo)은 시험 카드."""
        if getattr(event, "kind", "") != "donation" or getattr(event, "platform", "") == "system":
            return
        amount = getattr(event, "amount", 0)
        if isinstance(amount, (int, float)):
            platform = str(getattr(event, "platform", ""))
            self.add(str(getattr(event, "name", "")), float(amount), str(getattr(event, "unit", "")), platform, getattr(event, "time", None),
                     test=platform == "demo")

    def _find(self, card_id: Any) -> dict[str, Any]:
        number = _number(card_id)
        found = next((card for card in self.cards if number is not None and card["id"] == number), None)
        if found is None:
            raise WallError("카드 없음(이미 지웠거나 벽을 비움)", 404)
        return found

    def clear(self) -> dict[str, Any]:
        """벽 비우기. 파일에서는 바로 지우고 8초 동안만 메모리에 두어 되돌릴 수 있게 한다."""
        with self._lock:
            removed, self.cards = self.cards, []
            self._undo = (removed, self._clock() + UNDO_SECONDS) if removed else None
            self._last = None
            self._save_now()
        self._publish()
        return {"cleared": len(removed), "undo": UNDO_SECONDS if removed else 0}

    def undo(self) -> dict[str, Any]:
        with self._lock:
            if self._undo is None:
                raise WallError("되돌릴 비우기가 없음")
            removed, deadline = self._undo
            if self._clock() > deadline:
                self._undo = None
                raise WallError(f"되돌릴 수 있는 시간({UNDO_SECONDS:.0f}초)이 지났음")
            kept = {card["id"] for card in removed}
            self.cards = sorted([*removed, *(card for card in self.cards if card["id"] not in kept)], key=lambda card: card["id"])[-MAX_CARDS:]
            self._undo = None
            self._last = self.cards[-1]["id"] if self.cards else None
            self._save_now()
        self._publish()
        return {"restored": len(removed), "cards": len(self.cards)}

    def detach(self, data: dict[str, Any]) -> dict[str, Any]:
        """카드 하나를 다른 칸으로(``column``: 지금 있는 칸 이름, 또는 ``"solo"`` 이면 그 카드만의 칸)."""
        with self._lock:
            card = self._find(data.get("card"))
            target = str(data.get("column") or "")
            if target == "solo":
                target = f"solo/{card['id']}"
            else:
                columns, _ = self._columns()
                if target not in {column["key"] for column in columns}:
                    raise WallError("옮길 칸 없음: 칸 목록에 있는 칸이나 따로 세우기를 선택", 404)
            if target == natural_column(card, self.config):
                card.pop("column", None)
            else:
                card["column"] = target
            self._save_now()
        self._publish()
        return {"card": card["id"], "column": target}

    def restore(self, data: dict[str, Any]) -> dict[str, Any]:
        """옮긴 카드를 원래 칸으로."""
        with self._lock:
            card = self._find(data.get("card"))
            card.pop("column", None)
            self._save_now()
        self._publish()
        return {"card": card["id"], "column": natural_column(card, self.config)}

    def remove(self, data: dict[str, Any]) -> dict[str, Any]:
        """카드 하나(``card``) 또는 시험 카드 모두(``{"tests": true}``) 지우기."""
        with self._lock:
            if data.get("tests") is True:
                before = len(self.cards)
                self.cards = [card for card in self.cards if not card.get("test")]
                removed = before - len(self.cards)
            else:
                card = self._find(data.get("card"))
                self.cards.remove(card)
                removed = 1
            if self._last is not None and all(card["id"] != self._last for card in self.cards):
                self._last = self.cards[-1]["id"] if self.cards else None
            self._save_now()
        self._publish()
        return {"removed": removed, "cards": len(self.cards)}

    def replay(self, data: dict[str, Any]) -> dict[str, Any]:
        """마지막 카드(또는 ``card``)의 등장 연출을 다시."""
        with self._lock:
            card = self._find(data["card"]) if data.get("card") is not None else None
            if card is None:
                if self._last is None or not self.cards:
                    raise WallError("다시 볼 카드 없음")
                card = next((item for item in self.cards if item["id"] == self._last), self.cards[-1])
            self.rev += 1
            message = {"type": "replay", "rev": self.rev, "id": card["id"]}
        self.feed.publish(message, keep=False)
        return {"replay": card["id"]}

    def test(self, data: dict[str, Any]) -> dict[str, Any]:
        """시험 후원: ``unit``, ``amount``, ``name``, ``platform`` (기본 시험), ``count`` 장. ``mix`` 면 여러 단위 예시 12장을 한꺼번에."""
        if data.get("mix") is True:
            samples = [("치즈냥", 10, "별풍선", "soop"), ("고양이집사", 5000, "원", "chzzk"), ("새벽감성", 34, "별풍선", "soop"),
                       ("Haru", 500, "bits", "twitch"), ("별빛시청자", 10000, "원", "youtube"), ("도토리", 44, "별풍선", "soop"),
                       ("숲속토끼", 1000, "원", "chzzk"), ("lurker_kim", 5, "USD", "youtube"), ("노래하는토끼", 100, "별풍선", "soop"),
                       ("밤하늘산책", 1000, "애드벌룬", "soop"), ("초코우유", 30000, "원", "chzzk"), ("푸른고래", 59, "별풍선", "soop")]
            added = [self.add(name, amount, unit, platform, test=True) for name, amount, unit, platform in samples]
            return {"added": len([card for card in added if card])}
        unit = _config_unit(data.get("unit", "원"))
        amount = _number(data.get("amount", 1000))
        if amount is None or not 0 < amount <= MAX_AMOUNT:
            raise WallError("시험 금액은 0보다 큰 숫자")
        count = _number(data.get("count", 1))
        if count is None or count != int(count) or not 1 <= count <= 30:
            raise WallError("시험 카드 수는 1에서 30 사이")
        platform = data.get("platform") or "demo"
        if platform not in PLATFORMS:
            raise WallError("플랫폼은 chzzk, soop, twitch, youtube, demo")
        name = _text(data.get("name"), MAX_NAME, "이름") or "시험"
        added = [self.add(name, amount, unit, str(platform), test=True) for _ in range(int(count))]
        return {"added": len(added), "card": added[-1]["id"] if added and added[-1] else None}

    # ------------------------------------------------------------------ 설정, 배치, 그림
    def update(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self.config = update_config(self.config, data)
            self._save_now()
        self._publish()
        return self.status()

    def set_layout(self, data: dict[str, Any]) -> dict[str, Any]:
        """칸 하나의 위치와 크기(``key``, ``x``, ``y``, ``w``, ``h``), ``{"reset": true}`` 는 모두 자동 배치로, ``{"key", "auto": true}`` 는 그 칸만."""
        with self._lock:
            if data.get("reset") is True:
                self.layout = {}
            else:
                key = str(data.get("key") or "")
                if data.get("auto") is True:
                    self.layout.pop(key, None)
                else:
                    columns, _ = self._columns()
                    if key not in {column["key"] for column in columns}:
                        raise WallError("칸 없음(벽이 바뀌었으면 다시 시도)", 404)
                    self.layout[key] = _box(data)
            self._save_now()
        self._publish()
        return {"layout": copy.deepcopy(self.layout)}

    def _store_image(self, value: Any) -> str:
        data, kind = decode_image(value)
        folder = image_folder()
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{secrets.token_hex(12)}.{kind}"
        (folder / name).write_bytes(data)
        return name

    def _drop_image(self, name: str) -> None:
        path = image_path(name)
        if path is not None:
            try:
                path.unlink()
            except OSError:
                pass

    def save_signature(self, data: dict[str, Any]) -> dict[str, Any]:
        """시그니처 추가(``id`` 없이) 또는 바꾸기. ``image``: base64면 새 그림, 빈 값이면 그림 빼기, 없으면 그대로."""
        with self._lock:
            signatures = self.config["signatures"]
            existing = next((item for item in signatures if item["id"] == data.get("id")), None) if data.get("id") else None
            if data.get("id") and existing is None:
                raise WallError("시그니처 없음", 404)
            if existing is None and len(signatures) >= MAX_SIGNATURES:
                raise WallError(f"시그니처는 {MAX_SIGNATURES}개까지")
            signature = _signature(data, signatures)
            if existing is not None:
                signature["id"], signature["image"] = existing["id"], existing["image"]
            old = signature["image"]
            if "image" in data:
                signature["image"] = self._store_image(data["image"]) if data["image"] else ""
            if existing is not None:
                signatures[signatures.index(existing)] = signature
            else:
                signatures.append(signature)
            try:
                self._save_now()
            except OSError:
                if signature["image"] != old:
                    self._drop_image(signature["image"])
                raise
            if old and old != signature["image"]:
                self._drop_image(old)
        self._publish()
        return {"signature": dict(signature), "signatures": copy.deepcopy(self.config["signatures"])}

    def remove_signature(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            found = next((item for item in self.config["signatures"] if item["id"] == data.get("id")), None)
            if found is None:
                raise WallError("시그니처 없음", 404)
            self.config["signatures"].remove(found)
            self.layout.pop(f"sig/{found['id']}", None)
            self._save_now()
            self._drop_image(found["image"])
        self._publish()
        return {"signatures": copy.deepcopy(self.config["signatures"])}

    def set_column(self, data: dict[str, Any]) -> dict[str, Any]:
        """칸 그림 붙이기(``key``, ``image`` base64) 또는 빼기(``image`` 빈 값)."""
        with self._lock:
            key = str(data.get("key") or "")
            columns, _ = self._columns()
            images = self.config["columns"]
            if key not in {column["key"] for column in columns} and key not in images:
                raise WallError("칸 없음(벽이 바뀌었으면 다시 시도)", 404)
            old = (images.get(key) or {}).get("image", "")
            if data.get("image"):
                if key not in images and len(images) >= MAX_COLUMN_IMAGES:
                    raise WallError(f"칸 그림은 {MAX_COLUMN_IMAGES}개까지")
                images[key] = {"image": self._store_image(data["image"])}
            else:
                images.pop(key, None)
            self._save_now()
            if old:
                self._drop_image(old)
        self._publish()
        return {"key": key, "image": (images.get(key) or {}).get("image", "")}

    def image(self, query: dict[str, list[str]]) -> Raw:
        name = (query.get("name") or [""])[0]
        path = image_path(name)
        if path is None:
            raise WallError("그림 없음", 404)
        return Raw(path.read_bytes(), _IMAGE_TYPES[name.rsplit(".", 1)[1]], IMAGE_POLICY)

    def export(self, query: dict[str, list[str]] | None = None) -> Raw:
        with self._lock:
            columns, _ = self._columns()
            text = export_text(self.cards, columns)
        return Raw(text.encode("utf-8"), "text/plain; charset=utf-8", "default-src 'none'")

    def public_view(self, query: dict[str, list[str]]) -> dict[str, Any]:
        part = (query.get("part") or [""])[0]
        return self.view(part=part if part in ("goal", "rank") else "")

    def undo_left(self) -> float:
        with self._lock:
            return max(0.0, self._undo[1] - self._clock()) if self._undo else 0.0

    def feature(self) -> Feature:
        return Feature(
            name="wall",
            static={"/wall": "wall.html", "/wall/goal": "wall.html", "/wall/rank": "wall.html", "/wall.js": "wall.js", "/wall.css": "wall.css",
                    "/wall/control": "wall-control.html"},
            get={"/wall/state": lambda query: self.status(), "/wall/view": self.public_view, "/wall/image": self.image, "/wall/export": self.export},
            post={"/wall/config": self.update, "/wall/signature": self.save_signature, "/wall/signature/remove": self.remove_signature,
                  "/wall/column": self.set_column, "/wall/layout": self.set_layout, "/wall/test": self.test, "/wall/clear": lambda data: self.clear(),
                  "/wall/undo": lambda data: self.undo(), "/wall/detach": self.detach, "/wall/restore": self.restore, "/wall/remove": self.remove,
                  "/wall/replay": self.replay},
            feeds={"wall": self.feed},
            taps=[self.tap],
            body_limit={"/wall/config": 65536, "/wall/signature": IMAGE_BODY, "/wall/column": IMAGE_BODY},
            stop=self.stop,
        )


def feature(context: Context) -> Feature:
    """오버레이 서버에 등록하는 후원 벽(feature.py의 default_features)."""
    return Wall(notify=context.notify).feature()
