"""주사위 판: 방송 화면(``/board``)에 띄우는 주사위 말판 게임. 판을 돌며 칸의 미션을 하고, 특별한 칸(한 번 더, 뒤로 2칸, 한 번 쉬기, 행운 카드)이 판을 뒤집는다.

- 판은 정사각형 둘레 16, 20, 24, 28칸. 0번은 출발, 특별한 칸의 자리는 판 크기마다 정해 두고 나머지 칸에 스트리머가 적은 미션(비면 기본 미션)
- 참가자는 붙여 넣은 이름과 참여 추첨 명단(최대 8명). 주사위는 서버가 운영체제 난수로 굴리고, 방송 화면은 그 결과(지나간 칸 순서)를 그대로 그린다
- 굴리기: 조작 화면 단추, 또는 시청자 굴리기를 켜면 차례인 참가자가 채팅에 명령(기본 ``!주사위``)을 쓰면 굴림(같은 이름, 3초 간격)
- 설정은 board.json(settings.save_data). 진행 중인 게임과 기록은 메모리에만
"""

from __future__ import annotations

import random
import re
import threading
import time
from typing import Any, Callable

from . import settings
from .overlay.feature import Channel, Feature, FeatureError

DATA_FILE = "board.json"
#: 판 크기(둘레 칸 수) -> 이름. 한 변의 칸 수는 칸 수 / 4 + 1
SIZES = {16: "16칸(한 변 5칸)", 20: "20칸(한 변 6칸)", 24: "24칸(한 변 7칸)", 28: "28칸(한 변 8칸)"}
DESIGNS = {"pastel": "파스텔", "night": "밤하늘", "paper": "종이 공작"}
SPECIALS = {"start": "출발", "again": "한 번 더", "back": "뒤로 2칸", "rest": "한 번 쉬기", "lucky": "행운 카드"}
#: 판 크기마다 특별한 칸 자리(0번은 출발)
SPECIAL_AT = {16: {4: "again", 8: "rest", 12: "lucky"}, 20: {5: "again", 7: "back", 10: "rest", 15: "lucky"},
              24: {6: "again", 9: "back", 12: "rest", 18: "lucky"}, 28: {7: "again", 10: "back", 14: "rest", 21: "lucky", 24: "back"}}
DEFAULT_CELLS = ["노래 한 소절", "애교 3초", "성대모사", "팬에게 한마디", "랜덤 질문 답하기", "춤 10초", "물 한 잔", "삼행시", "칭찬 릴레이",
                 "목소리 바꿔 인사", "좋아하는 음식 소개", "웃음 참기 10초", "윙크", "다음 방송 예고", "하트 만들기", "최애 노래 한 줄",
                 "감사 인사", "방송 꿀팁 하나", "옛날 이야기", "아무 말 10초", "랜덤 표정", "추억의 게임", "오늘 기분 점수", "시청자 이름 부르기",
                 "효과음 흉내", "캐릭터 따라 하기", "칭찬 한마디"]
LUCKY = {"forward": "앞으로 3칸", "home": "출발로", "everyone": "모두 1칸 앞으로", "swap": "다른 참가자와 자리 바꾸기", "again": "한 번 더 굴리기",
         "nothing": "아무 일도 없음"}
COLORS = ["#ff4f8b", "#3ba7f0", "#f2b705", "#1f9d67", "#8e5cf0", "#ff8a3d", "#20b2aa", "#a0673d"]
MAX_PLAYERS = 8
MIN_PLAYERS = 1
MAX_CELL = 24
MAX_TITLE = 20
MAX_NAME = 20
MAX_LOG = 30
ROLL_GAP = 3.0  # 채팅으로 굴릴 때 최소 간격(초): 방송 화면 연출이 끝나기 전에 다시 굴리지 않게
DEFAULTS: dict[str, Any] = {"title": "주사위 판", "size": 20, "cells": [], "design": "pastel", "chat_roll": False, "command": "!주사위",
                            "use_raffle": True}
_COMMAND = re.compile(r"^![0-9A-Za-z가-힣]{1,10}$")


class BoardError(FeatureError):
    """잘못된 주사위 판 요청. 메시지는 한국어 안내(400)."""


def _text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def check_config(data: Any, base: dict[str, Any] | None = None) -> dict[str, Any]:
    """설정 확인. 주지 않은 항목은 ``base`` (없으면 기본값). 틀리면 BoardError."""
    if not isinstance(data, dict):
        raise BoardError("설정 형식이 올바르지 않음")
    merged = {**DEFAULTS, **(base or {}), **{key: value for key, value in data.items() if key in DEFAULTS}}
    title = _text(merged["title"], MAX_TITLE) or DEFAULTS["title"]
    size = merged["size"]
    if isinstance(size, bool) or size not in SIZES:
        raise BoardError("판 크기는 " + ", ".join(str(key) for key in SIZES) + "칸 중 하나")
    cells = merged["cells"]
    if isinstance(cells, str):
        cells = cells.splitlines()
    if not isinstance(cells, list) or len(cells) > 40:
        raise BoardError("칸 미션은 한 줄에 하나씩 40개까지")
    cells = [text for text in (_text(cell, MAX_CELL) for cell in cells) if text]
    if merged["design"] not in DESIGNS:
        raise BoardError("디자인은 " + ", ".join(DESIGNS) + " 중 하나")
    command = str(merged["command"] or "").strip()
    if not _COMMAND.match(command):
        raise BoardError("굴리기 명령은 !로 시작하는 10자 이하(예: !주사위)")
    return {"title": title, "size": size, "cells": cells, "design": merged["design"], "chat_roll": bool(merged["chat_roll"]), "command": command,
            "use_raffle": bool(merged["use_raffle"])}


def load_options() -> dict[str, Any]:
    try:
        return check_config(settings.load_data(DATA_FILE))
    except BoardError:
        return dict(DEFAULTS)


def layout(config: dict[str, Any]) -> list[dict[str, str]]:
    """판의 칸: [{"kind": start|mission|again|back|rest|lucky, "text"}]. 미션은 적은 순서대로(모자라면 기본 미션)."""
    size = config["size"]
    special = SPECIAL_AT[size]
    missions = config["cells"] or DEFAULT_CELLS
    found: list[dict[str, str]] = []
    index = 0
    for at in range(size):
        if at == 0:
            found.append({"kind": "start", "text": SPECIALS["start"]})
        elif at in special:
            found.append({"kind": special[at], "text": SPECIALS[special[at]]})
        else:
            found.append({"kind": "mission", "text": missions[index % len(missions)]})
            index += 1
    return found


def parse_players(text: Any) -> list[str]:
    names = []
    for line in str(text or "").replace(",", "\n").splitlines():
        name = _text(line, MAX_NAME)
        if name and name not in names:
            names.append(name)
    return names


class BoardState:
    """판 설정, 진행 중인 게임(참가자 자리, 차례), 기록. 바뀌면 /live?feeds=board 로 보낸다."""

    def __init__(self, raffle: Any = None, rng: random.Random | None = None, clock: Callable[[], float] = time.time,
                 notify: Callable[[str], None] | None = None) -> None:
        self._lock = threading.Lock()
        self._rng = rng or random.SystemRandom()
        self._clock = clock
        self._raffle = raffle
        self._notify = notify or (lambda text: None)
        self.config = load_options()
        self.cells = layout(self.config)
        self.players: list[dict[str, Any]] = []
        self.turn = 0
        self.seq = 0
        self.log: list[dict[str, Any]] = []
        self.last: dict[str, Any] | None = None
        self.last_roll = 0.0
        self.channel = Channel(self._payload())

    # ------------------------------------------------------------------ 상태
    def _payload(self) -> dict[str, Any]:
        return {"seq": self.seq, "title": self.config["title"], "size": self.config["size"], "design": self.config["design"], "cells": self.cells,
                "players": [dict(player) for player in self.players], "turn": self.turn if self.players else None, "event": self.last,
                "playing": bool(self.players), "command": self.config["command"] if self.config["chat_roll"] else ""}

    def _publish(self) -> None:
        self.channel.publish(self._payload())

    def snapshot(self, _: Any = None) -> dict[str, Any]:
        with self._lock:
            raffle = len(self._raffle_names())
            return {**self._payload(), "config": dict(self.config), "log": list(self.log), "raffle": raffle,
                    "choices": {"sizes": {str(key): label for key, label in SIZES.items()}, "designs": DESIGNS, "specials": SPECIALS,
                                "lucky": LUCKY, "default_cells": DEFAULT_CELLS, "max_players": MAX_PLAYERS}}

    def _raffle_names(self) -> list[str]:
        if self._raffle is None:
            return []
        try:
            return [str(entry.get("name", "")) for entry in self._raffle.status().get("entries", [])]
        except Exception:  # 추첨 명단을 읽지 못해도 게임은 붙여 넣은 이름으로
            return []

    # ------------------------------------------------------------------ 설정과 시작
    def save(self, data: dict[str, Any]) -> dict[str, Any]:
        config = check_config(data, self.config)
        with self._lock:
            self.config = config
            self.cells = layout(config)
            settings.save_data(DATA_FILE, config)
            for player in self.players:  # 판 크기가 줄면 칸 안으로
                player["pos"] %= config["size"]
            self.seq += 1
            self._publish()
        return self.snapshot()

    def start(self, data: dict[str, Any]) -> dict[str, Any]:
        """새 게임: 붙여 넣은 이름과(켜 두면) 참여 추첨 명단에서 앞의 8명. 순서는 섞음."""
        if not isinstance(data, dict):
            raise BoardError("요청 형식이 올바르지 않음")
        names = parse_players(data.get("players", ""))
        use_raffle = data.get("use_raffle", self.config["use_raffle"]) is not False
        if use_raffle:
            names += [name for name in (_text(name, MAX_NAME) for name in self._raffle_names()) if name and name not in names]
        if len(names) < MIN_PLAYERS:
            raise BoardError("참가자가 없음: 이름을 적거나 참여 추첨으로 모집")
        names = names[:MAX_PLAYERS]
        with self._lock:
            self._rng.shuffle(names)
            self.players = [{"name": name, "color": COLORS[index % len(COLORS)], "pos": 0, "rest": 0, "laps": 0} for index, name in enumerate(names)]
            self.turn = 0
            self.log = []
            self.last = None
            self.seq += 1
            self._publish()
        return self.snapshot()

    def reset(self, _: Any = None) -> dict[str, Any]:
        with self._lock:
            self.players = []
            self.last = None
            self.seq += 1
            self._publish()
        return self.snapshot()

    # ------------------------------------------------------------------ 굴리기
    def _step(self, start: int, count: int) -> tuple[list[int], int]:
        """start에서 count칸(음수면 뒤로) 한 칸씩 지난 자리와, 출발을 지나 한 바퀴 돈 횟수."""
        size = self.config["size"]
        path, laps, at = [], 0, start
        for _ in range(abs(count)):
            at = (at + (1 if count > 0 else -1)) % size
            if count > 0 and at == 0:
                laps += 1
            path.append(at)
        return path, laps

    def roll(self, data: Any = None, *, by: str = "") -> dict[str, Any]:
        """차례인 참가자가 주사위를 굴림. 결과(지나간 칸, 도착 칸, 특별한 칸과 행운 카드)를 함께 보냄."""
        with self._lock:
            if not self.players:
                raise BoardError("진행 중인 게임이 없음: 먼저 시작")
            player = self.players[self.turn]
            event: dict[str, Any] = {"player": self.turn, "name": player["name"], "color": player["color"], "by": by, "time": round(self._clock(), 3)}
            if player["rest"]:
                player["rest"] = 0
                event.update(kind="rested", dice=0, path=[], at=player["pos"], text=f"{player['name']} 한 번 쉬기")
                self._finish(event, again=False)
                return self.snapshot_locked()
            dice = self._rng.randint(1, 6)
            path, laps = self._step(player["pos"], dice)
            player["pos"], player["laps"] = path[-1], player["laps"] + laps
            cell = self.cells[player["pos"]]
            event.update(kind=cell["kind"], dice=dice, path=path, laps=laps, text=cell["text"])
            again = False
            if cell["kind"] == "again":
                again = True
            elif cell["kind"] == "back":
                back, _ = self._step(player["pos"], -2)
                player["pos"] = back[-1]
                event.update(back=back, text=f"뒤로 2칸: {self.cells[player['pos']]['text']}")
            elif cell["kind"] == "rest":
                player["rest"] = 1
            elif cell["kind"] == "lucky":
                again = self._lucky(event, player)
            event["at"] = player["pos"]
            self._finish(event, again=again)
            return self.snapshot_locked()

    def _lucky(self, event: dict[str, Any], player: dict[str, Any]) -> bool:
        card = self._rng.choice(list(LUCKY))
        event["card"] = card
        event["card_text"] = LUCKY[card]
        if card == "forward":
            more, laps = self._step(player["pos"], 3)
            player["pos"], player["laps"] = more[-1], player["laps"] + laps
            event["more"] = more
            event["text"] = f"앞으로 3칸: {self.cells[player['pos']]['text']}"
        elif card == "home":
            player["pos"] = 0
            event["text"] = "출발로 돌아감"
        elif card == "everyone":
            for other in self.players:
                more, laps = self._step(other["pos"], 1)
                other["pos"], other["laps"] = more[-1], other["laps"] + laps
            event["text"] = "모두 1칸 앞으로"
        elif card == "swap" and len(self.players) > 1:
            other = self._rng.choice([item for item in self.players if item is not player])
            player["pos"], other["pos"] = other["pos"], player["pos"]
            event["swap"] = other["name"]
            event["text"] = f"자리 바꾸기: {other['name']}"
        elif card == "again":
            event["text"] = "한 번 더 굴리기"
            return True
        else:
            event["text"] = "아무 일도 없음"
        return False

    def _finish(self, event: dict[str, Any], *, again: bool) -> None:
        self.seq += 1
        event["seq"] = self.seq
        event["again"] = again
        event["positions"] = [player["pos"] for player in self.players]
        if not again:
            self.turn = (self.turn + 1) % len(self.players)
        event["next"] = self.turn
        self.last = event
        self.last_roll = self._clock()
        self.log = [event, *self.log][:MAX_LOG]
        self._publish()

    def snapshot_locked(self) -> dict[str, Any]:
        return {**self._payload(), "config": dict(self.config), "log": list(self.log)}

    # ------------------------------------------------------------------ 채팅으로 굴리기
    def handle(self, event: Any) -> None:
        """차례인 참가자가 채팅에 굴리기 명령을 쓰면 굴림(시청자 굴리기를 켰을 때)."""
        if not self.config["chat_roll"] or getattr(event, "kind", "") != "chat" or getattr(event, "platform", "") == "system":
            return
        text = str(getattr(event, "text", "")).strip()
        if text.split(" ", 1)[0] != self.config["command"]:
            return
        name = _text(getattr(event, "name", ""), MAX_NAME)
        with self._lock:
            if not self.players or self.players[self.turn]["name"] != name or self._clock() - self.last_roll < ROLL_GAP:
                return
        try:
            self.roll(by=name)
        except BoardError:
            pass


def feature(context: Any) -> Feature:
    state = BoardState(raffle=getattr(context, "raffle", None), notify=getattr(context, "notify", None))
    return Feature(
        name="board",
        static={"/board": "board.html", "/board/control": "board-control.html", "/board.js": "board.js", "/board.css": "board.css"},
        get={"/board/state": state.snapshot},
        post={"/board/config": state.save, "/board/start": state.start, "/board/roll": lambda data: state.roll(data), "/board/reset": state.reset},
        feeds={"board": state.channel},
        taps=[state.handle],
        body_limit={"/board/config": 8192, "/board/start": 8192},
    )
