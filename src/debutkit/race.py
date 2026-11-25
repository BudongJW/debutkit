"""참여 레이스: 시청자 이름이 방송 화면에서 경주하는 게임(구슬 레이스, 달리기 경주, 서바이벌).

- 참가자는 시청자 참여 추첨 명단(채팅 ``!참가``, 후원 참가, 직접 추가. 치지직, SOOP, YouTube, Twitch)과 붙여 넣은 이름.
  ``이름*3`` 은 3번 참가(화면에는 이름, 이름#2, 이름#3). 한 판에 최대 100명. 연습은 예시 이름으로 방송 화면에 나가지 않음
- 순위는 시작할 때 서버가 정한다: 운영체제 난수(``random.SystemRandom``)로 시드(6자리)를 고르고 그 시드로 섞은 순서가 전체 순위.
  같은 시드와 같은 명단이면 언제나 같은 순위. 계획(게임, 시드, 순위, 시작 시각, 길이, 재생 속도, 연출 설정)을 한 번 보내고
  방송 화면(``/race``)과 조작 화면의 미리보기는 (시드, 순위, 경과 시간)만으로 같은 장면을 그린다. 중간에 연 화면은 지금 장면부터
- 달리기 경주는 8명씩 조별 경기 뒤 결승(또는 30명까지 모두 함께). 다음 조는 스트리머가 시작
- 당첨 순위는 1등, 꼴찌, 지정 순위. 꼴찌 당첨이면 조별 경기에서 느린 참가자가 꼴찌 결승에 진출
- 설정은 race.json(settings.save_data). 참가 명단과 결과는 메모리에만(결과는 조작 화면에서 텍스트 파일로 저장)
"""

from __future__ import annotations

import copy
import math
import random
import re
import threading
import time
from collections import Counter
from typing import Any, Callable

from . import settings
from .overlay.feature import Channel, Feature, FeatureError

DATA_FILE = "race.json"
GAMES = {"marble": "구슬 레이스", "run": "달리기 경주", "survival": "서바이벌"}
#: 줄(레인)을 나눠 달리는 게임: 8명씩 조별 경기 뒤 결승
LANE_GAMES = ("run",)
COURSES = {"zigzag": "지그재그 경사로", "pegs": "핀 숲", "stairs": "계단 폭포"}
FORMATS = {"heats": "8명씩 조별 경기 뒤 결승", "all": "모두 함께(30명까지)"}
SURPRISES = {"none": "없음", "some": "조금", "many": "많이"}
EVENTS = {
    "marble": {"wind": "바람", "lightning": "번개", "quake": "지진", "comeback": "꼴찌 가속", "check": "선두 견제", "item": "아이템 상자",
               "gate": "운명의 문", "switch": "갈림길 전환"},
    "run": {"sprint": "질주", "stumble": "넘어짐", "dive": "막판 다이빙", "cramp": "다리 쥐"},
    "survival": {"heal": "회복", "shield": "보호막", "power": "힘 키우기", "spikes": "가시 함정", "zone": "좁아지는 구역"},
}
RANKS = {"first": "1등", "last": "꼴찌", "custom": "지정 순위"}
LENGTHS = {"short": "짧게", "normal": "보통", "long": "길게"}
#: 1배속 기준 경주 시간(초). 구슬, 서바이벌은 한 판, 달리기는 한 조
SECONDS = {"marble": {"short": 24, "normal": 36, "long": 54}, "run": {"short": 11, "normal": 16, "long": 24},
           "survival": {"short": 26, "normal": 40, "long": 60}}
SPEED = (0.7, 2.2)
DESIGNS = {"wood": "나무 장난감", "metal": "유리와 금속", "paper": "종이 공작"}
#: 기본 색. 화면은 이 색 하나에서 밝은 색, 어두운 색, 참가자 색을 만든다
#: channel(방송 색)은 설정 화면, 방송 화면 미리보기에서 고른 방송 색(overlay/theme.py)을 따른다
COLORS = {"channel": ("방송 색", "#ff4f8b"), "pink": ("분홍", "#ff4f8b"), "red": ("빨강", "#e5484d"), "orange": ("주황", "#ff8a3d"), "yellow": ("노랑", "#f2b705"),
          "lime": ("연두", "#7cb342"), "green": ("초록", "#1f9d67"), "mint": ("민트", "#20b2aa"), "sky": ("하늘", "#3ba7f0"),
          "blue": ("파랑", "#3d63dd"), "purple": ("보라", "#8e5cf0"), "lilac": ("라일락", "#c27ae0"), "brown": ("갈색", "#a0673d"),
          "slate": ("먹색", "#59626a")}
#: 글꼴: 함께 배포한 글꼴(Black Han Sans, Pretendard)과 Windows 기본 글꼴. 없는 글꼴은 맑은 고딕으로 표시
FONTS = {"blackhan": ("Black Han Sans(함께 배포)", '"Black Han Sans", "Malgun Gothic", sans-serif'),
         "pretendard": ("Pretendard(함께 배포)", '"Pretendard", "Malgun Gothic", sans-serif'),
         "malgun": ("맑은 고딕", '"Malgun Gothic", "Apple SD Gothic Neo", sans-serif'),
         "gulim": ("굴림", 'Gulim, "Malgun Gothic", sans-serif'),
         "dotum": ("돋움", 'Dotum, "Malgun Gothic", sans-serif'),
         "batang": ("바탕", 'Batang, "AppleMyungjo", serif'),
         "gungsuh": ("궁서", 'Gungsuh, Batang, serif'),
         "nanum": ("나눔고딕(설치한 경우)", '"NanumGothic", "Malgun Gothic", sans-serif'),
         "nanumpen": ("나눔손글씨 펜(설치한 경우)", '"Nanum Pen Script", "NanumPen", "Malgun Gothic", cursive'),
         "impact": ("Impact(영문)", 'Impact, "Black Han Sans", "Malgun Gothic", sans-serif'),
         "consolas": ("Consolas(영문)", 'Consolas, "Malgun Gothic", monospace')}
MIN_RUNNERS = 2
MAX_RUNNERS = 100
LANES = 8
MAX_AT_ONCE = 30
MAX_REPEAT = 10
MAX_NAME = 40
MAX_PASTE = 20000
#: 출발 전 숫자 세기(실제 초, 재생 속도와 무관)
COUNTDOWN = 3.0
#: 마지막 도착 뒤 결과 확정까지(실제 초)
SETTLE = 1.5
SAMPLE_NAMES = ["고양이집사", "새벽감성", "별빛구름", "debut_streamer", "노래하는토끼", "밤하늘산책", "초코우유", "푸른고래", "라면한그릇", "햇살가득",
                "모닝커피", "달빛소나타", "감자튀김", "구름빵", "딸기라떼", "pixel_fox", "은하수", "솜사탕", "고등어구이", "말랑콩떡", "봄바람", "nightowl",
                "치즈냥", "바다소금", "귤까는중", "호떡장인", "보라빛", "lucky7", "새우깡", "졸린곰", "콩나물", "여름밤", "산책가자", "까만콩", "레몬에이드",
                "꿀호박", "도토리묵", "momo", "파란하늘", "토마토"]
SOURCE_LABELS = {"chat": "채팅", "donation": "후원", "manual": "직접", "paste": "붙여넣기", "practice": "연습"}
PLATFORM_LABELS = {"chzzk": "치지직", "soop": "SOOP", "youtube": "YouTube", "twitch": "Twitch", "demo": "시험"}
DEFAULTS: dict[str, Any] = {
    "game": "marble", "course": "zigzag", "format": "heats", "surprise": "some", "events": {game: list(kinds) for game, kinds in EVENTS.items()},
    "rank": "first", "custom_rank": 2, "length": "normal", "speed": 1.0, "design": "wood", "color": "channel", "font": "blackhan",
    "sound": True, "volume": 70, "listen": False, "use_raffle": True, "dedupe": False, "practice_count": 24,
}


class RaceError(FeatureError):
    """잘못된 레이스 요청. 메시지는 한국어 안내(400)."""


# --------------------------------------------------------------------------- 설정


def _pick(value: Any, table: dict[str, Any], message: str) -> str:
    if not isinstance(value, str) or value not in table:
        raise RaceError(message)
    return value


def _integer(value: Any, low: int, high: int, message: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value) or not low <= value <= high:
        raise RaceError(message)
    return int(value)


def _events(value: Any, base: dict[str, list[str]]) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        raise RaceError("깜짝 요소는 게임별 목록(예: {\"marble\": [\"wind\"]})")
    found = {game: list(base.get(game, EVENTS[game])) for game in EVENTS}
    for game, kinds in value.items():
        if game not in EVENTS:
            raise RaceError(f"깜짝 요소의 게임 이름이 올바르지 않음: {str(game)[:20]}")
        if not isinstance(kinds, list):
            raise RaceError("깜짝 요소는 게임별 목록(예: {\"marble\": [\"wind\"]})")
        for kind in kinds:
            if kind not in EVENTS[game]:
                raise RaceError(f"{GAMES[game]}의 깜짝 요소가 올바르지 않음: {str(kind)[:20]}")
        found[game] = [kind for kind in EVENTS[game] if kind in kinds]  # 정해진 순서, 중복 없이
    return found


def check_options(data: Any, base: dict[str, Any] | None = None) -> dict[str, Any]:
    """조작 화면, 명령줄에서 받은 설정 확인. 주지 않은 항목은 ``base`` (기본값) 그대로. 틀리면 RaceError(한국어 안내)."""
    if not isinstance(data, dict):
        raise RaceError("설정 형식이 올바르지 않음")
    base = copy.deepcopy(base if base is not None else DEFAULTS)
    merged = {**base, **{key: value for key, value in data.items() if key in DEFAULTS}}
    speed = merged["speed"]
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not SPEED[0] <= speed <= SPEED[1]:
        raise RaceError(f"재생 속도는 {SPEED[0]}에서 {SPEED[1]} 사이(1이 보통)")
    return {
        "game": _pick(merged["game"], GAMES, "게임은 marble(구슬 레이스), run(달리기 경주), survival(서바이벌) 중 하나"),
        "course": _pick(merged["course"], COURSES, "구슬 코스는 zigzag(지그재그 경사로), pegs(핀 숲), stairs(계단 폭포) 중 하나"),
        "format": _pick(merged["format"], FORMATS, "경기 방식은 heats(8명씩 조별 경기 뒤 결승) 또는 all(모두 함께, 30명까지)"),
        "surprise": _pick(merged["surprise"], SURPRISES, "깜짝 요소는 none(없음), some(조금), many(많이) 중 하나"),
        "events": _events(merged["events"], base.get("events") or DEFAULTS["events"]),
        "rank": _pick(merged["rank"], RANKS, "당첨 순위는 first(1등), last(꼴찌), custom(지정 순위) 중 하나"),
        "custom_rank": _integer(merged["custom_rank"], 1, MAX_RUNNERS, f"지정 순위는 1에서 {MAX_RUNNERS} 사이의 정수"),
        "length": _pick(merged["length"], LENGTHS, "경주 길이는 short(짧게), normal(보통), long(길게) 중 하나"),
        "speed": round(float(speed), 2),
        "design": _pick(merged["design"], DESIGNS, "디자인은 wood(나무 장난감), metal(유리와 금속), paper(종이 공작) 중 하나"),
        "color": _pick(merged["color"], COLORS, "색은 " + ", ".join(COLORS) + " 중 하나"),
        "font": _pick(merged["font"], FONTS, "글꼴은 " + ", ".join(FONTS) + " 중 하나"),
        "sound": bool(merged["sound"]),
        "volume": _integer(merged["volume"], 0, 100, "효과음 크기는 0에서 100 사이의 정수"),
        "listen": bool(merged["listen"]),
        "use_raffle": bool(merged["use_raffle"]),
        "dedupe": bool(merged["dedupe"]),
        "practice_count": _integer(merged["practice_count"], MIN_RUNNERS, MAX_RUNNERS, f"연습 인원은 {MIN_RUNNERS}에서 {MAX_RUNNERS} 사이의 정수"),
    }


def load_options() -> dict[str, Any]:
    """저장한 설정(race.json). 없거나 잘못된 항목은 기본값."""
    saved = settings.load_data(DATA_FILE)
    options = copy.deepcopy(DEFAULTS)
    for key in DEFAULTS:
        if key in saved:
            try:
                options = check_options({key: saved[key]}, options)
            except RaceError:
                pass
    return options


def save_options(options: dict[str, Any]) -> None:
    settings.save_data(DATA_FILE, options)


def color_hex(key: str) -> str:
    """색 이름의 색. channel은 지금 방송 색의 주 색."""
    if key == "channel":
        from .overlay import theme

        return theme.load()["primary"]
    return COLORS[key][1]


def choices() -> dict[str, Any]:
    """조작 화면의 선택 목록."""
    return {"games": GAMES, "courses": COURSES, "formats": FORMATS, "surprises": SURPRISES, "events": EVENTS, "ranks": RANKS, "lengths": LENGTHS,
            "designs": DESIGNS, "colors": {key: {"label": label, "hex": color_hex(key)} for key, (label, _) in COLORS.items()},
            "fonts": {key: {"label": label, "css": css} for key, (label, css) in FONTS.items()}, "speed": list(SPEED),
            "limits": {"min": MIN_RUNNERS, "max": MAX_RUNNERS, "lanes": LANES, "at_once": MAX_AT_ONCE, "repeat": MAX_REPEAT, "name": MAX_NAME}}


# --------------------------------------------------------------------------- 참가자

REPEAT = re.compile(r"^(.*?)\s*\*\s*(\d+)$")


def parse_names(text: Any) -> list[tuple[str, int]]:
    """붙여 넣은 이름(줄바꿈이나 쉼표로 구분). ``이름*3`` 은 3번 참가. 틀리면 RaceError."""
    text = str(text or "")
    if len(text) > MAX_PASTE:
        raise RaceError(f"붙여 넣은 글이 너무 김({MAX_PASTE:,}자까지)")
    found: list[tuple[str, int]] = []
    for raw in re.split(r"[\n,]", text):
        item = raw.strip()
        if not item:
            continue
        count = 1
        match = REPEAT.match(item)
        if match:
            item, number = match.group(1).strip(), match.group(2)
            count = int(number) if len(number) <= 4 else 0
            if not 1 <= count <= MAX_REPEAT:
                raise RaceError(f"이름*N의 N은 1에서 {MAX_REPEAT} 사이: {raw.strip()[:30]}")
        if not item:
            raise RaceError(f"이름이 비어 있음: {raw.strip()[:30]}")
        if len(item) > MAX_NAME:
            raise RaceError(f"이름은 {MAX_NAME}자 이내: {item[:12]}...")
        found.append((item, count))
    return found


def make_tickets(pasted: list[tuple[str, int]], entries: Any = (), *, dedupe: bool = False) -> tuple[list[dict[str, Any]], list[str]]:
    """참가표: 추첨 명단(먼저 참가한 순서) 다음 붙여 넣은 이름. 같은 이름이 여러 장이면 화면에는 이름#2, 이름#3으로 구분.

    ``dedupe`` 이면 같은 이름은 한 장만(``이름*N`` 과 여러 플랫폼의 같은 닉네임도 1장).
    """
    raw = [(str(entry.get("name", "")), str(entry.get("source", "chat")), str(entry.get("platform", ""))) for entry in entries or ()]
    raw += [(name, "paste", "") for name, count in pasted for _ in range(count)]
    tickets: list[dict[str, Any]] = []
    seen: Counter[str] = Counter()
    used: set[str] = set()
    merged = 0
    for name, source, platform in raw:
        name = name.strip()[:MAX_NAME]
        if not name:
            continue
        if dedupe and seen[name]:
            merged += 1
            continue
        seen[name] += 1
        number = seen[name]
        display = name if number == 1 else f"{name}#{number}"
        while display in used:  # 원래 이름이 '이름#2'인 참가자와 겹치지 않게
            number += 1
            display = f"{name}#{number}"
        used.add(display)
        tickets.append({"name": display, "base": name, "source": source, "platform": "" if platform == "manual" else platform})
    notes = []
    if merged:
        notes.append(f"같은 이름 {merged}개는 한 번만 넣음")
    repeated = sum(1 for count in seen.values() if count > 1)
    if repeated:
        notes.append(f"여러 번 참가한 이름 {repeated}개(화면에는 이름#2처럼 구분, 참가한 만큼 당첨 기회)")
    return tickets, notes


def sample_tickets(count: int) -> list[dict[str, Any]]:
    """연습용 예시 이름."""
    names = [SAMPLE_NAMES[index % len(SAMPLE_NAMES)] + (str(index // len(SAMPLE_NAMES) + 1) if index >= len(SAMPLE_NAMES) else "") for index in range(count)]
    return [{"name": name, "base": name, "source": "practice", "platform": ""} for name in names]


# --------------------------------------------------------------------------- 계획(순위, 조, 도착 시각)


def _split(names: list[str], groups: int) -> list[list[str]]:
    """앞에서부터 고르게 나눔(인원 차이 최대 1명)."""
    size, extra = divmod(len(names), groups)
    found, start = [], 0
    for index in range(groups):
        end = start + size + (1 if index < extra else 0)
        found.append(names[start:end])
        start = end
    return found


def heat_sizes(count: int, format_: str = "heats") -> list[list[int]]:
    """달리기 경주의 라운드별 조 인원(마지막이 결승). 조마다 결승 8명을 채우도록 같은 수가 진출(최소 1명)."""
    rounds: list[list[int]] = []
    field = count
    while format_ == "heats" and field > LANES:
        groups = math.ceil(field / LANES)
        sizes = [len(group) for group in _split(list(range(field)), groups)]
        keep = max(1, LANES // groups)
        rounds.append(sizes)
        field = sum(min(keep, size) for size in sizes)
    rounds.append([field])
    return rounds


def _advancing(order: list[str], keep: int, rank: str) -> list[str]:
    """조의 도착 순서에서 다음 라운드 진출자. 꼴찌 당첨이면 느린 참가자가 진출."""
    return order[-keep:] if rank == "last" else order[:keep]


def finish_times(rng: random.Random, game: str, count: int, base: float) -> list[float]:
    """도착 순서별 시각(경주 초, 빠른 순). 서바이벌은 탈락 시각(1등은 끝까지 생존해 ``base``)."""
    if count == 1:
        return [float(base)]
    if game == "survival":
        first, last = base * rng.uniform(0.12, 0.18), base * rng.uniform(0.86, 0.92)
        weights = [rng.uniform(0.5, 1.5) for _ in range(count - 2)]
        total = sum(weights) or 1.0
        eliminated = [first]
        for weight in weights:
            eliminated.append(eliminated[-1] + (last - first) * weight / total)
        if count == 2:
            eliminated = [last]
        times = [float(base)] + [round(value, 2) for value in reversed(eliminated)]
    else:
        share = (0.16 + 0.3 * min(count, 60) / 60) if game == "marble" else (0.06 + 0.1 * min(count, MAX_AT_ONCE) / MAX_AT_ONCE)
        weights = [rng.uniform(0.15, 0.6)] + [rng.uniform(0.4, 1.6) for _ in range(count - 2)]
        total = sum(weights)
        times = [base * rng.uniform(0.97, 1.03)]
        for weight in weights:
            times.append(times[-1] + base * share * weight / total)
        times = [round(value, 2) for value in times]
        for index in range(1, len(times)):  # 반올림 뒤에도 순서 유지
            times[index] = max(times[index], round(times[index - 1] + 0.01, 2))
    return times


def _label(round_number: int, rounds: int, index: int, final: bool, rank: str) -> str:
    if rounds == 1:
        return ""
    if final:
        return "꼴찌 결승" if rank == "last" else "결승"
    if rounds == 2:
        return f"{index + 1}조"
    stage = "예선" if round_number == 0 else "준결승" if round_number == rounds - 2 else "본선"
    return f"{stage} {index + 1}조"


def build_plan(game: str, names: list[str], options: dict[str, Any], seed: int) -> dict[str, Any]:
    """시드로 전체 순위와 조, 도착 시각을 정한다. 같은 시드와 명단이면 언제나 같은 계획.

    전체 순위(``ranking``)는 실력 순서: 조마다 이 순서대로 도착하고, 조별 진출과 결승도 이 순서를 따른다.
    """
    if len(set(names)) != len(names):
        raise RaceError("참가자 이름이 겹침(이름#2처럼 구분해야 함)")
    rng = random.Random(seed)
    ranking = list(names)
    rng.shuffle(ranking)
    position = {name: index for index, name in enumerate(ranking)}
    base = SECONDS[game][options["length"]]
    rank = options["rank"]
    field = list(names)
    rng.shuffle(field)  # 출발 위치, 레인
    rounds: list[tuple[list[list[str]], int]] = []
    while game in LANE_GAMES and options["format"] == "heats" and len(field) > LANES:
        groups = _split(field, math.ceil(len(field) / LANES))
        keep = max(1, LANES // len(groups))
        rounds.append((groups, keep))
        field = [name for group in groups for name in _advancing(sorted(group, key=position.__getitem__), keep, rank)]
        rng.shuffle(field)
    rounds.append(([field], 0))
    heats: list[dict[str, Any]] = []
    for number, (groups, keep) in enumerate(rounds):
        final = number == len(rounds) - 1
        for index, group in enumerate(groups):
            order_names = sorted(group, key=position.__getitem__)
            lane = {name: slot for slot, name in enumerate(group)}
            by_place = finish_times(rng, game, len(group), base)
            times = [0.0] * len(group)
            for place, name in enumerate(order_names):
                times[lane[name]] = by_place[place]
            heats.append({"label": _label(number, len(rounds), index, final, rank), "round": number, "final": final, "names": group,
                          "order": [lane[name] for name in order_names], "times": times,
                          "advance": [] if final else sorted(lane[name] for name in _advancing(order_names, keep, rank)),
                          "end": max(by_place)})
    standing = _standing(heats, position, rank)
    final_size = len(heats[-1]["names"])
    if rank == "custom" and options["custom_rank"] > final_size:
        where = f"결승 인원({final_size}명)" if len(heats) > 1 else f"참가 인원({final_size}명)"
        raise RaceError(f"지정 순위는 {where} 이하")
    place = {"first": 1, "last": len(standing)}.get(rank, options.get("custom_rank", 1))
    label = {"first": "우승", "last": "꼴찌 당첨"}.get(rank, f"{place}등 당첨")
    return {"game": game, "game_label": GAMES[game], "course": options["course"] if game == "marble" else "",
            "course_label": COURSES[options["course"]] if game == "marble" else "", "format": options["format"] if game in LANE_GAMES else "all",
            "seed": seed, "count": len(names), "base": base, "heats": heats, "ranking": ranking, "standing": standing, "rank": rank,
            "rank_label": label, "winner": {"name": standing[place - 1], "place": place}}


def _standing(heats: list[dict[str, Any]], position: dict[str, int], rank: str) -> list[str]:
    """대회 전체 순위: 결승 순서, 그다음 늦은 라운드에서 탈락한 순서(같은 라운드는 조 안 순위, 실력 순). 꼴찌 당첨은 반대 방향."""
    final = heats[-1]
    finals = [final["names"][lane] for lane in final["order"]]
    out: dict[int, list[tuple[int, int, str]]] = {}
    for heat in heats[:-1]:
        advanced = set(heat["advance"])
        for place, lane in enumerate(heat["order"]):
            if lane not in advanced:
                name = heat["names"][lane]
                out.setdefault(heat["round"], []).append((place, position[name], name))
    groups = [[name for *_, name in sorted(rows)] for _, rows in sorted(out.items())]
    if rank == "last":
        return [name for group in groups for name in group] + finals
    return finals + [name for group in reversed(groups) for name in group]


# --------------------------------------------------------------------------- 결과


def _clock_text(stamp: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(stamp))


def _source_text(ticket: dict[str, Any] | None) -> str:
    if not ticket:
        return ""
    parts = [PLATFORM_LABELS.get(ticket.get("platform", ""), ticket.get("platform", "")), SOURCE_LABELS.get(ticket.get("source", ""), "")]
    return ", ".join(part for part in parts if part)


def result_line(result: dict[str, Any]) -> str:
    """채팅창 안내 한 줄."""
    return (f"참여 레이스 {result['rank_label']}: {result['winner']['name']}"
            f"({result['game_label']}, {result['count']}명, 시드 {result['seed']})")


def result_text(result: dict[str, Any]) -> str:
    """텍스트 파일로 저장할 결과(당첨, 전체 순위, 경기 기록)."""
    game = result["game_label"] + (f"({result['course_label']})" if result.get("course_label") else "")
    lines = ["debutkit 참여 레이스 결과", f"일시: {_clock_text(result['time'])}", f"게임: {game}", f"참가: {result['count']}명",
             f"시드: {result['seed']}", f"당첨({result['rank_label']}): {result['winner']['name']}"]
    if result.get("practice"):
        lines.append("연습 경기(방송 화면에 표시하지 않음)")
    lines += ["", "[전체 순위]"]
    for row in result["standing"]:
        source = f" ({row['from']})" if row.get("from") else ""
        lines.append(f"{row['place']:>4}. {row['name']}{source}")
    lines += ["", "[경기 기록]"]
    survival = result["game"] == "survival"
    for heat in result["heats"]:
        lines.append(f"- {heat['label']}")
        for row in heat["rows"]:
            if survival:
                mark = "생존" if row["place"] == 1 else f"{row['time']:.2f}초 탈락"
            else:
                mark = f"{row['time']:.2f}초"
            if row.get("advance"):
                mark += ", 진출"
            lines.append(f"{row['place']:>4}. {row['name']}  {mark}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- 상태


class RaceState:
    """참여 레이스 진행 상태. 계획을 ``race`` 실시간 항목으로 한 번 보내고, 조가 끝나면 상태만 바꿔 보낸다."""

    def __init__(self, notify: Callable[[str], None] | None = None, raffle: Any = None, rng: random.Random | None = None,
                 clock: Callable[[], float] = time.time, timers: bool = True) -> None:
        self._lock = threading.RLock()
        self._notify = notify or (lambda text: None)
        self._raffle = raffle
        self._rng = rng or random.SystemRandom()
        self.clock = clock
        self._timers = timers
        self._timer: threading.Timer | None = None
        self.options = load_options()
        self.phase = "idle"  # idle, running, between(다음 조 대기), done
        self.race: dict[str, Any] | None = None
        self.tickets: dict[str, dict[str, Any]] = {}
        self.heat = 0
        self.started = 0.0
        self.last_result: dict[str, Any] | None = None
        self._id = 0
        self._seq = 0
        self.channel = Channel(self._payload())

    # ------------------------------------------------------------------ 보내는 값
    def _sound(self) -> dict[str, Any]:
        return {"on": self.options["sound"], "volume": self.options["volume"], "listen": self.options["listen"]}

    def _payload(self) -> dict[str, Any]:
        self._seq += 1
        return {"seq": self._seq, "state": self.phase, "id": self._id, "race": self.race if self.phase != "idle" else None, "heat": self.heat,
                "started": self.started, "countdown": COUNTDOWN, "sound": self._sound()}

    def _publish(self) -> None:
        self.channel.publish(self._payload())

    def _heat_end(self) -> float:
        """지금 조의 결과가 확정되는 시각(실제 시각)."""
        assert self.race is not None
        heat = self.race["heats"][self.heat]
        return self.started + COUNTDOWN + heat["end"] / self.race["options"]["speed"] + SETTLE

    # ------------------------------------------------------------------ 설정
    def config(self, query: Any = None) -> dict[str, Any]:
        return {"options": copy.deepcopy(self.options), "choices": choices()}

    def save(self, data: dict[str, Any]) -> dict[str, Any]:
        """설정 저장. 소리 설정은 진행 중인 레이스에도 바로 적용."""
        with self._lock:
            self.options = check_options(data, self.options)
            save_options(self.options)
            if self.phase != "idle":
                self._publish()
        return self.config()

    # ------------------------------------------------------------------ 참가자
    def _raffle_entries(self) -> list[dict[str, Any]]:
        if self._raffle is None:
            return []
        try:
            return list(self._raffle.status().get("entries", []))
        except Exception:  # 추첨 상태를 읽지 못해도 붙여 넣은 이름으로 진행
            return []

    def _tickets(self, data: dict[str, Any], options: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], bool]:
        practice = bool(data.get("practice", False))
        if practice:
            return sample_tickets(options["practice_count"]), [f"연습: 예시 이름 {options['practice_count']}명"], True
        pasted = parse_names(data.get("paste", ""))
        entries = self._raffle_entries() if options["use_raffle"] else []
        tickets, notes = make_tickets(pasted, entries, dedupe=options["dedupe"])
        return tickets, notes, False

    def entries(self, data: dict[str, Any]) -> dict[str, Any]:
        """시작 전 확인: 참가 인원, 출처별 인원, 안내(중복, 제한)."""
        options = check_options(data, self.options)
        tickets, notes, practice = self._tickets(data, options)
        problem = ""
        try:
            self._check_count(options, tickets)
        except RaceError as error:
            problem = str(error)
        counts = Counter(ticket["source"] for ticket in tickets)
        return {"count": len(tickets), "names": [ticket["name"] for ticket in tickets[:MAX_RUNNERS + 20]], "sources": dict(counts),
                "notes": notes, "problem": problem, "practice": practice, "raffle": len(self._raffle_entries())}

    @staticmethod
    def _check_count(options: dict[str, Any], tickets: list[dict[str, Any]]) -> None:
        count = len(tickets)
        if count < MIN_RUNNERS:
            raise RaceError(f"참가자가 {MIN_RUNNERS}명 이상 필요(지금 {count}명): 추첨 명단을 모으거나 이름을 붙여 넣기")
        if count > MAX_RUNNERS:
            raise RaceError(f"참가자는 한 판에 {MAX_RUNNERS}명까지(지금 {count}명)")
        if options["game"] in LANE_GAMES and options["format"] == "all" and count > MAX_AT_ONCE:
            raise RaceError(f"모두 함께 달리기는 {MAX_AT_ONCE}명까지(지금 {count}명): 조별 경기를 선택")

    # ------------------------------------------------------------------ 진행
    def start(self, data: dict[str, Any]) -> dict[str, Any]:
        """새 레이스: 설정 확인, 참가표, 시드와 순위 결정, 첫 조(또는 한 판) 시작. 설정은 저장."""
        options = check_options(data, self.options)
        tickets, notes, practice = self._tickets(data, options)
        self._check_count(options, tickets)
        seed = self._rng.randint(100000, 999999)
        plan = build_plan(options["game"], [ticket["name"] for ticket in tickets], options, seed)
        chosen_hex = color_hex(options["color"])
        plan["practice"] = practice
        plan["options"] = {"surprise": options["surprise"], "events": options["events"][options["game"]], "design": options["design"],
                           "color": options["color"], "color_hex": chosen_hex, "font": options["font"], "font_css": FONTS[options["font"]][1],
                           "speed": options["speed"], "length": options["length"]}
        plan["notes"] = notes
        with self._lock:
            self._cancel()
            self.options = options
            save_options(options)
            self._id += 1
            plan["id"] = self._id
            self.race = plan
            self.tickets = {ticket["name"]: ticket for ticket in tickets}
            self.heat = 0
            self.started = self.clock()
            self.phase = "running"
            self._publish()
            self._schedule()
        return self.snapshot()

    def next(self, data: Any = None) -> dict[str, Any]:
        """다음 조 시작(지금 조가 끝난 뒤)."""
        with self._lock:
            self.settle()
            if self.phase == "idle" or self.race is None:
                raise RaceError("진행 중인 레이스가 없음: 먼저 시작")
            if self.phase == "running":
                raise RaceError("지금 조가 끝난 뒤 다음 조를 시작할 수 있음")
            if self.phase == "done":
                raise RaceError("모든 경기가 끝남: 새 레이스를 시작")
            self.heat += 1
            self.started = self.clock()
            self.phase = "running"
            self._publish()
            self._schedule()
        return self.snapshot()

    def stop(self, data: Any = None) -> dict[str, Any]:
        """방송 화면에서 내리기(진행 중이면 취소, 지난 결과는 유지)."""
        with self._lock:
            self._cancel()
            self.phase = "idle"
            self.race = None
            self.tickets = {}
            self.heat = 0
            self.started = 0.0
            self._publish()
        return self.snapshot()

    def settle(self) -> None:
        """시간이 지난 조를 끝냄: 결승(또는 한 판)이면 결과를 정리하고 채팅창에 한 줄 안내."""
        with self._lock:
            if self.phase != "running" or self.race is None or self.clock() < self._heat_end():
                return
            if self.heat < len(self.race["heats"]) - 1:
                self.phase = "between"
            else:
                self.phase = "done"
                self.last_result = self._result()
                if not self.race["practice"]:
                    self._notify(self.last_result["line"])
            self._publish()

    def _schedule(self) -> None:
        if not self._timers:
            return
        delay = max(0.0, self._heat_end() - self.clock()) + 0.05
        self._timer = threading.Timer(delay, self.settle)
        self._timer.daemon = True
        self._timer.start()

    def _cancel(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def close(self) -> None:
        with self._lock:
            self._cancel()

    # ------------------------------------------------------------------ 조회
    def _result(self) -> dict[str, Any]:
        race = self.race
        assert race is not None
        standing = [{"place": index + 1, "name": name, "from": _source_text(self.tickets.get(name))} for index, name in enumerate(race["standing"])]
        heats = []
        for heat in race["heats"]:
            advanced = set(heat["advance"])
            heats.append({"label": heat["label"] or "경기", "rows": [{"place": place + 1, "name": heat["names"][lane], "time": heat["times"][lane],
                                                                    "advance": lane in advanced} for place, lane in enumerate(heat["order"])]})
        result = {"id": race["id"], "time": round(self.clock(), 3), "game": race["game"], "game_label": race["game_label"],
                  "course_label": race["course_label"], "seed": race["seed"], "count": race["count"], "practice": race["practice"],
                  "rank": race["rank"], "rank_label": race["rank_label"], "winner": race["winner"], "standing": standing, "heats": heats}
        result["line"] = result_line(result)
        result["text"] = result_text(result)
        return result

    def snapshot(self, query: Any = None) -> dict[str, Any]:
        """조작 화면용 상태. 진행 중인 조의 결과는 끝난 뒤에만(조작 화면을 함께 보는 경우 미리 보이지 않게)."""
        self.settle()
        with self._lock:
            now = self.clock()
            state: dict[str, Any] = {"state": self.phase, "id": self._id, "now": round(now, 3), "options": copy.deepcopy(self.options),
                                     "raffle": len(self._raffle_entries()), "last_result": self.last_result, "countdown": COUNTDOWN}
            race = self.race
            if race is not None and self.phase != "idle":
                finished = self.heat if self.phase == "running" else self.heat + 1
                state.update(heat=self.heat, started=self.started, elapsed=round(now - self.started, 3), heat_end=round(self._heat_end(), 3),
                             race={key: race[key] for key in ("id", "game", "game_label", "course_label", "seed", "count", "practice", "rank_label", "notes")},
                             heats=[{"label": heat["label"] or "경기", "names": heat["names"], "final": heat["final"],
                                     "rows": [{"place": place + 1, "name": heat["names"][lane], "time": heat["times"][lane], "advance": lane in heat["advance"]}
                                              for place, lane in enumerate(heat["order"])] if index < finished else None}
                                    for index, heat in enumerate(race["heats"])])
            return state

    def sample(self, query: dict[str, list[str]]) -> dict[str, Any]:
        """미리보기 장면(?sample): 저장한 설정과 예시 이름으로 만든 계획. 방송 화면에는 보내지 않는다."""
        def value(name: str, fallback: Any = None) -> Any:
            return query.get(name, [fallback])[0]

        changes: dict[str, Any] = {key: value(key) for key in ("game", "course", "format", "surprise", "rank", "length", "design", "color", "font")
                                   if value(key)}
        for key in ("speed",):
            if value(key):
                try:
                    changes[key] = float(value(key))
                except ValueError as error:
                    raise RaceError("재생 속도는 숫자") from error
        options = check_options(changes, self.options)
        defaults = {"marble": 24, "run": 8, "survival": 30}
        try:
            count = int(value("n", defaults[options["game"]]))
            seed = int(value("seed", 482913))
        except ValueError as error:
            raise RaceError("n과 seed는 정수") from error
        count = max(MIN_RUNNERS, min(MAX_RUNNERS, count))
        tickets = sample_tickets(count)
        if options["game"] in LANE_GAMES and options["format"] == "all":
            tickets = tickets[:MAX_AT_ONCE]
        plan = build_plan(options["game"], [ticket["name"] for ticket in tickets], {**options, "custom_rank": 1}, seed)
        plan.update(id=0, practice=True, notes=[], options={"surprise": options["surprise"], "events": options["events"][options["game"]],
                                                            "design": options["design"], "color": options["color"], "color_hex": color_hex(options["color"]),
                                                            "font": options["font"], "font_css": FONTS[options["font"]][1], "speed": options["speed"],
                                                            "length": options["length"]})
        try:
            heat = max(0, min(len(plan["heats"]) - 1, int(value("heat", 0))))
        except ValueError:
            heat = 0
        return {"seq": 0, "state": "running", "id": 0, "race": plan, "heat": heat, "started": round(self.clock(), 3), "countdown": COUNTDOWN,
                "sound": self._sound()}


def feature(context: Any) -> Feature:
    """오버레이 서버에 등록할 참여 레이스 기능(feature.py의 default_features)."""
    state = RaceState(notify=context.notify, raffle=context.raffle)
    return Feature(
        name="race",
        static={"/race": "race.html", "/race.js": "race.js", "/race.css": "race.css", "/race/control": "race-control.html"},
        get={"/race/state": state.snapshot, "/race/config": state.config, "/race/sample": state.sample},
        post={"/race/start": state.start, "/race/next": state.next, "/race/stop": state.stop, "/race/config": state.save, "/race/entries": state.entries},
        feeds={"race": state.channel},
        body_limit={"/race/start": 32768, "/race/entries": 32768, "/race/config": 8192},
        stop=state.close,
    )
