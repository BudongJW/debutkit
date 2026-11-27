"""주사위 판(board.py, /board): 판 칸, 설정 확인, 참가자, 굴리기와 특별한 칸, 행운 카드, 채팅으로 굴리기, 서버 주소."""

import http.client
import json
import random
from collections import Counter
from pathlib import Path

import pytest

from debutkit import board, raffle
from debutkit.overlay.events import OverlayEvent
from debutkit.overlay.server import OverlayServer

STATIC = Path(__file__).resolve().parent.parent / "src" / "debutkit" / "overlay" / "static"


class Dice(random.Random):
    """정해 둔 눈과 행운 카드를 차례로 내는 난수(섞기는 그대로 두기)."""

    def __init__(self, rolls, cards=()):
        super().__init__(1)
        self.rolls = list(rolls)
        self.cards = list(cards)

    def randint(self, low, high):
        return self.rolls.pop(0)

    def choice(self, items):
        items = list(items)
        if self.cards and self.cards[0] in items:
            return self.cards.pop(0)
        return items[0]

    def shuffle(self, items):
        pass


def game(rolls, cards=(), players="가\n나\n다", **config):
    state = board.BoardState(rng=Dice(rolls, cards), clock=lambda: 1000.0)
    if config:
        state.save(config)
    state.start({"players": players, "use_raffle": False})
    return state


def test_layout_specials_and_missions():
    for size, special in board.SPECIAL_AT.items():
        cells = board.layout(board.check_config({"size": size}))
        assert len(cells) == size and cells[0]["kind"] == "start"
        assert {at: cell["kind"] for at, cell in enumerate(cells) if cell["kind"] not in ("start", "mission")} == special
    mine = board.layout(board.check_config({"size": 16, "cells": "노래\n\n  춤   추기 \n" + "가" * 40}))
    missions = [cell["text"] for cell in mine if cell["kind"] == "mission"]
    assert missions[:4] == ["노래", "춤 추기", "가" * board.MAX_CELL, "노래"]  # 빈 줄 빼고, 24자로, 모자라면 처음부터
    assert board.layout(board.check_config({}))[1]["text"] == board.DEFAULT_CELLS[0]


@pytest.mark.parametrize("data, message", [
    ({"size": 18}, "판 크기는"), ({"size": True}, "판 크기는"), ({"design": "gold"}, "디자인은"), ({"command": "주사위"}, "!로 시작"),
    ({"command": "!" + "가" * 11}, "!로 시작"), ({"cells": ["a"] * 41}, "40개까지"), ("문자열", "형식"),
])
def test_config_is_checked(data, message):
    with pytest.raises(board.BoardError, match=message):
        board.check_config(data)


def test_players_from_paste_and_raffle():
    box = raffle.Raffle(rng=random.Random(1))
    box.start()
    for name in ("추첨1", "가", "추첨2"):
        box.add(name, "chzzk", "chat")
    state = board.BoardState(raffle=box, rng=Dice([]))
    started = state.start({"players": "가, 나\n가\n" + "\n".join(f"p{i}" for i in range(10))})
    names = [player["name"] for player in started["players"]]
    assert len(names) == board.MAX_PLAYERS and names[:3] == ["가", "나", "p0"] and len(set(names)) == len(names)
    assert started["players"][0] == {"name": "가", "color": board.COLORS[0], "pos": 0, "rest": 0, "laps": 0}
    only = state.start({"players": "", "use_raffle": True})
    assert [player["name"] for player in only["players"]] == ["추첨1", "가", "추첨2"]
    with pytest.raises(board.BoardError, match="참가자가 없음"):
        board.BoardState(rng=Dice([])).start({"players": "  ", "use_raffle": False})
    with pytest.raises(board.BoardError, match="진행 중인 게임이 없음"):
        board.BoardState(rng=Dice([1])).roll()


def test_roll_moves_and_wraps_with_laps():
    state = game([4, 6, 2, 6, 6, 6, 3], size=16)
    event = state.roll()["event"]
    assert (event["name"], event["dice"], event["path"], event["kind"], event["next"]) == ("가", 4, [1, 2, 3, 4], "again", 0)  # 4번: 한 번 더
    event = state.roll()["event"]
    assert event["path"] == [5, 6, 7, 8, 9, 10] and event["next"] == 1 and state.players[0]["pos"] == 10
    state.roll()  # 나: 2칸
    state.roll()  # 다: 6칸
    event = state.roll()["event"]  # 가: 10 -> 16(0)
    assert event["path"][-1] == 0 and event["laps"] == 1 and state.players[0]["laps"] == 1 and event["kind"] == "start"


def test_back_and_rest_cells():
    state = game([7, 1, 1, 3], size=20)  # 20칸: 7번 뒤로 2칸, 10번 한 번 쉬기
    event = state.roll()["event"]
    assert event["kind"] == "back" and event["back"] == [6, 5] and event["at"] == 5 and state.players[0]["pos"] == 5
    assert event["text"].startswith("뒤로 2칸: ")
    state.players[1]["pos"] = 9
    event = state.roll()["event"]  # 나: 9 -> 10 한 번 쉬기
    assert event["kind"] == "rest" and state.players[1]["rest"] == 1
    state.roll()  # 다
    state.roll()  # 가
    event = state.roll()["event"]  # 나는 쉼(주사위 없음)
    assert event["kind"] == "rested" and event["dice"] == 0 and state.players[1]["rest"] == 0 and event["next"] == 2


@pytest.mark.parametrize("card, check", [
    ("forward", lambda state, event: state.players[0]["pos"] == 15 and event["more"] == [13, 14, 15]),
    ("home", lambda state, event: state.players[0]["pos"] == 0),
    ("everyone", lambda state, event: [player["pos"] for player in state.players] == [13, 1, 1]),
    ("swap", lambda state, event: state.players[0]["pos"] == 0 and state.players[1]["pos"] == 12 and event["swap"] == "나"),
    ("again", lambda state, event: event["again"] and event["next"] == 0),
    ("nothing", lambda state, event: state.players[0]["pos"] == 12 and not event["again"]),
])
def test_lucky_cards(card, check):
    state = game([12], [card, "나"], size=16)  # 16칸: 12번 행운 카드
    event = state.roll()["event"]
    assert event["kind"] == "lucky" and event["card"] == card and event["card_text"] == board.LUCKY[card]
    assert check(state, event)


def test_chat_roll_only_for_the_current_player():
    clock = [1000.0]
    state = board.BoardState(rng=Dice([3, 5, 2]), clock=lambda: clock[0])
    state.save({"chat_roll": True, "command": "!주사위"})
    state.start({"players": "가\n나", "use_raffle": False})
    chat = lambda name, text: OverlayEvent("chzzk", "chat", name, (("text", text),))  # noqa: E731
    state.handle(chat("나", "!주사위"))  # 차례가 아님
    state.handle(chat("가", "주사위"))  # 명령이 아님
    assert state.last is None
    clock[0] += 10
    state.handle(chat("가", "!주사위 가자"))
    assert state.last["by"] == "가" and state.last["dice"] == 3
    state.handle(chat("나", "!주사위"))  # 3초 안
    assert state.last["name"] == "가"
    clock[0] += 3.5
    state.handle(chat("나", "!주사위"))
    assert state.last["name"] == "나" and state.last["dice"] == 5
    state.save({"chat_roll": False})
    clock[0] += 10
    state.handle(chat("가", "!주사위"))
    assert state.last["name"] == "나"


def test_dice_are_fair():
    state = board.BoardState(rng=random.Random(7))
    state.start({"players": "가", "use_raffle": False})
    counts = Counter(state.roll()["event"]["dice"] for _ in range(1800))
    rolled = {face: count for face, count in counts.items() if face}
    assert set(rolled) == {1, 2, 3, 4, 5, 6} and all(220 < count < 390 for count in rolled.values())


def request(srv, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, data


def test_routes_pages_and_menu():
    server = OverlayServer([], port=0).start()
    try:
        for path in ("/board", "/board/control", "/board.js", "/board.css"):
            assert request(server, "GET", path)[0] == 200, path
        status, body = request(server, "POST", "/board/roll", {})
        assert status == 400 and "진행 중인 게임이 없음" in json.loads(body)["error"]
        status, body = request(server, "POST", "/board/start", {"players": "가\n나", "use_raffle": False})
        assert status == 200 and json.loads(body)["playing"]
        status, body = request(server, "POST", "/board/roll", {})
        assert status == 200 and 1 <= json.loads(body)["event"]["dice"] <= 6
        state = json.loads(request(server, "GET", "/board/state")[1])
        assert state["choices"]["sizes"]["20"] and len(state["log"]) == 1 and state["config"]["size"] == 20
    finally:
        server.stop()
    script = (STATIC / "board.js").read_text(encoding="utf-8")
    assert "innerHTML" not in script and "https://" not in script and 'subscribe(["board", "theme"]' in script
    assert '["/board/control", "주사위 판"' in (STATIC / "ui.js").read_text(encoding="utf-8")
