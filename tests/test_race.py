"""참여 레이스: 이름 붙여 넣기, 참가표, 시드와 순위, 당첨 순위, 조별 경기, 설정 확인과 저장, 결과, 서버 주소와 실시간 항목."""

import http.client
import json
import random

import pytest

from debutkit import race, raffle, settings
from debutkit.overlay import feature
from debutkit.overlay.events import system_event
from debutkit.overlay.server import OverlayServer

NAMES = [f"시청자{index}" for index in range(30)]


def options(**changes):
    return race.check_options(changes)


# --------------------------------------------------------------------------- 참가자


def test_parse_names_repeat_and_limits():
    assert race.parse_names("고양이*3\n 새벽 , 별빛구름 *2\n\n,") == [("고양이", 3), ("새벽", 1), ("별빛구름", 2)]
    assert race.parse_names("a*b, 별*표") == [("a*b", 1), ("별*표", 1)]  # 숫자가 아니면 이름의 일부
    assert race.parse_names(None) == []
    for bad, message in (("이름*0", "1에서 10 사이"), ("이름*11", "1에서 10 사이"), ("이름*99999999", "1에서 10 사이"), ("*3", "비어 있음"),
                         ("가" * 41, "40자 이내")):
        with pytest.raises(race.RaceError, match=message):
            race.parse_names(bad)
    with pytest.raises(race.RaceError, match="너무 김"):
        race.parse_names("가," * 15000)


def test_tickets_mark_duplicates_and_dedupe():
    entries = [{"name": "고양이", "platform": "chzzk", "source": "chat"}, {"name": "고양이", "platform": "soop", "source": "donation"},
               {"name": "직접", "platform": "manual", "source": "manual"}]
    tickets, notes = race.make_tickets(race.parse_names("고양이*2\n새벽\n고양이#2"), entries)
    assert [ticket["name"] for ticket in tickets] == ["고양이", "고양이#2", "직접", "고양이#3", "고양이#4", "새벽", "고양이#2#2"]
    assert [ticket["source"] for ticket in tickets[:3]] == ["chat", "donation", "manual"] and tickets[2]["platform"] == ""
    assert any("이름#2처럼 구분" in note for note in notes)
    once, notes = race.make_tickets(race.parse_names("고양이*2\n새벽"), entries, dedupe=True)
    assert [ticket["name"] for ticket in once] == ["고양이", "직접", "새벽"] and any("3개는 한 번만" in note for note in notes)
    assert len({ticket["name"] for ticket in race.sample_tickets(100)}) == 100


def test_raffle_entries_become_tickets():
    box = raffle.Raffle(rng=random.Random(1))
    box.start()
    for name, platform in (("치지직시청자", "chzzk"), ("숲시청자", "soop"), ("유튜브시청자", "youtube"), ("트위치시청자", "twitch")):
        assert box.add(name, platform, "chat")
    box.add("직접추가", "manual")
    state = race.RaceState(raffle=box, rng=random.Random(2), timers=False)
    found = state.entries({"paste": "붙임*2"})
    assert found["count"] == 7 and found["raffle"] == 5 and found["sources"] == {"chat": 4, "manual": 1, "paste": 2} and found["problem"] == ""
    assert state.entries({"paste": "붙임", "use_raffle": False})["problem"].startswith("참가자가 2명 이상 필요")
    practice = state.entries({"practice": True, "practice_count": 40})
    assert practice["practice"] and practice["count"] == 40 and practice["sources"] == {"practice": 40}
    started = state.start({"paste": "붙임"})
    assert started["race"]["count"] == 6
    assert race._source_text(state.tickets["숲시청자"]) == "SOOP, 채팅" and race._source_text(state.tickets["붙임"]) == "붙여넣기"


# --------------------------------------------------------------------------- 설정


@pytest.mark.parametrize("changes, message", [
    ({"game": "horse"}, "marble(구슬 레이스)"),
    ({"course": "loop"}, "zigzag(지그재그 경사로)"),
    ({"format": "groups"}, "heats(8명씩"),
    ({"surprise": "lots"}, "none(없음)"),
    ({"events": {"marble": ["tornado"]}}, "구슬 레이스의 깜짝 요소가 올바르지 않음: tornado"),
    ({"events": {"chess": []}}, "게임 이름이 올바르지 않음"),
    ({"events": ["wind"]}, "게임별 목록"),
    ({"rank": "middle"}, "first(1등)"),
    ({"custom_rank": 0}, "1에서 100 사이"),
    ({"custom_rank": 2.5}, "1에서 100 사이"),
    ({"length": "epic"}, "short(짧게)"),
    ({"speed": 0.5}, "0.7에서 2.2 사이"),
    ({"speed": True}, "0.7에서 2.2 사이"),
    ({"design": "neon"}, "wood(나무 장난감)"),
    ({"color": "#ff0000"}, "색은 channel, pink"),
    ({"font": "comic"}, "글꼴은 blackhan"),
    ({"volume": 101}, "0에서 100 사이"),
    ({"practice_count": 1}, "2에서 100 사이"),
])
def test_invalid_options_are_explained(changes, message):
    with pytest.raises(race.RaceError, match=message.replace("(", r"\(").replace(")", r"\)")):
        race.check_options(changes)


def test_options_merge_and_persist():
    assert race.load_options() == race.DEFAULTS
    state = race.RaceState(timers=False)
    saved = state.save({"game": "run", "events": {"run": ["dive", "sprint", "dive"]}, "speed": 1.55, "color": "sky", "volume": 30, "unknown": 1})
    assert saved["options"]["events"]["run"] == ["sprint", "dive"] and saved["options"]["events"]["marble"] == race.DEFAULTS["events"]["marble"]
    data = settings.load_data(race.DATA_FILE)
    assert data["game"] == "run" and data["speed"] == 1.55 and data["color"] == "sky" and "unknown" not in data
    again = race.RaceState(timers=False)
    assert again.options["game"] == "run" and again.options["volume"] == 30
    settings.save_data(race.DATA_FILE, {**data, "speed": 9, "design": "x"})  # 손상된 항목만 기본값
    loaded = race.load_options()
    assert loaded["speed"] == 1.0 and loaded["design"] == "wood" and loaded["color"] == "sky"
    assert state.config()["choices"]["colors"]["sky"]["hex"].startswith("#") and len(state.config()["choices"]["colors"]) >= 12


# --------------------------------------------------------------------------- 순위, 조별 경기


def test_same_seed_and_names_give_the_same_plan():
    first = race.build_plan("marble", NAMES, options(), 123456)
    assert first == race.build_plan("marble", NAMES, options(), 123456)
    assert sorted(first["ranking"]) == sorted(NAMES) and first["standing"] == first["ranking"]
    others = {tuple(race.build_plan("marble", NAMES, options(), seed)["ranking"]) for seed in range(100000, 100020)}
    assert len(others) == 20
    heat = first["heats"][0]
    assert [heat["names"][lane] for lane in heat["order"]] == first["ranking"]
    by_place = [heat["times"][lane] for lane in heat["order"]]
    assert by_place == sorted(by_place) and len(set(by_place)) == len(by_place) and heat["end"] == by_place[-1]
    with pytest.raises(race.RaceError, match="겹침"):
        race.build_plan("marble", ["a", "a"], options(), 1)


def test_survival_times_are_eliminations():
    plan = race.build_plan("survival", NAMES[:10], options(game="survival"), 7)
    heat = plan["heats"][0]
    by_place = [heat["times"][lane] for lane in heat["order"]]
    assert by_place[0] == heat["end"] == race.SECONDS["survival"]["normal"]
    assert by_place[1:] == sorted(by_place[1:], reverse=True) and by_place[-1] < by_place[1] < heat["end"]


@pytest.mark.parametrize("count, sizes", [
    (2, [[2]]), (8, [[8]]), (9, [[5, 4], [8]]), (20, [[7, 7, 6], [6]]), (64, [[8] * 8, [8]]),
    (100, [[8] * 9 + [7] * 4, [7, 6], [8]]),
])
def test_heat_sizes(count, sizes):
    assert race.heat_sizes(count) == sizes
    plan = race.build_plan("run", NAMES[:count] if count <= 30 else [f"v{i}" for i in range(count)], options(game="run"), 99)
    assert [len(heat["names"]) for heat in plan["heats"]] == [size for round_ in sizes for size in round_]
    assert plan["heats"][-1]["final"] and plan["heats"][-1]["advance"] == []
    assert race.heat_sizes(count, "all") == [[count]]


def test_heats_follow_the_ranking_and_labels():
    names = [f"v{i}" for i in range(100)]
    plan = race.build_plan("run", names, options(game="run"), 4321)
    position = {name: index for index, name in enumerate(plan["ranking"])}
    labels = [heat["label"] for heat in plan["heats"]]
    assert labels[0] == "예선 1조" and labels[13] == "준결승 1조" and labels[-1] == "결승"
    for heat in plan["heats"]:
        order = [heat["names"][lane] for lane in heat["order"]]
        assert order == sorted(order, key=position.__getitem__)
        assert [heat["names"][lane] for lane in heat["order"][: len(heat["advance"])]] == [heat["names"][lane] for lane in sorted(heat["advance"], key=heat["order"].index)]
    assert plan["winner"] == {"name": plan["ranking"][0], "place": 1} and plan["standing"][0] == plan["ranking"][0]
    assert sorted(plan["standing"]) == sorted(names) and len(plan["standing"]) == 100
    small = race.build_plan("run", NAMES[:20], options(game="run"), 5)
    assert [heat["label"] for heat in small["heats"]] == ["1조", "2조", "3조", "결승"]
    together = race.build_plan("run", NAMES, options(game="run", format="all"), 5)
    assert len(together["heats"]) == 1 and together["heats"][0]["label"] == ""


def test_rank_selection_first_last_custom():
    first = race.build_plan("marble", NAMES, options(), 11)
    last = race.build_plan("marble", NAMES, options(rank="last"), 11)
    third = race.build_plan("marble", NAMES, options(rank="custom", custom_rank=3), 11)
    assert first["ranking"] == last["ranking"] == third["ranking"]
    assert (first["winner"]["name"], first["rank_label"]) == (first["ranking"][0], "우승")
    assert (last["winner"], last["rank_label"]) == ({"name": first["ranking"][-1], "place": 30}, "꼴찌 당첨")
    assert (third["winner"], third["rank_label"]) == ({"name": first["ranking"][2], "place": 3}, "3등 당첨")
    with pytest.raises(race.RaceError, match=r"참가 인원\(30명\) 이하"):
        race.build_plan("marble", NAMES, options(rank="custom", custom_rank=31), 11)
    # 꼴찌 당첨의 조별 경기: 조마다 느린 참가자가 꼴찌 결승에 진출하고, 결승 꼴찌가 전체 꼴찌
    names = [f"v{i}" for i in range(40)]
    slow = race.build_plan("run", names, options(game="run", rank="last"), 8)
    final = slow["heats"][-1]
    assert final["label"] == "꼴찌 결승" and slow["winner"]["name"] == slow["ranking"][-1] == final["names"][final["order"][-1]]
    assert slow["standing"][-1] == slow["winner"]["name"] and slow["winner"]["place"] == 40
    for heat in slow["heats"][:-1]:
        assert sorted(heat["advance"]) == sorted(heat["order"][-len(heat["advance"]):])
    with pytest.raises(race.RaceError, match=r"결승 인원\(5명\) 이하"):
        race.build_plan("run", names, options(game="run", rank="custom", custom_rank=6), 8)
    assert race.build_plan("run", names, options(game="run", rank="custom", custom_rank=2), 8)["winner"]["place"] == 2


# --------------------------------------------------------------------------- 진행, 결과


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


def test_start_heats_next_and_result():
    notes = []
    clock = Clock()
    state = race.RaceState(notify=notes.append, rng=random.Random(3), clock=clock, timers=False)
    subscriber, current = state.channel.subscribe()
    assert current["state"] == "idle" and current["race"] is None
    paste = "\n".join(NAMES[:20])
    with pytest.raises(race.RaceError, match="진행 중인 레이스가 없음"):
        state.next()
    with pytest.raises(race.RaceError, match="모두 함께 달리기는 30명까지"):
        state.start({"game": "run", "format": "all", "paste": "\n".join(f"n{i}" for i in range(31))})
    with pytest.raises(race.RaceError, match="100명까지"):
        state.start({"paste": "\n".join(f"n{i}" for i in range(101))})
    snapshot = state.start({"game": "run", "paste": paste, "speed": 2.0, "design": "paper"})
    assert snapshot["state"] == "running" and snapshot["heat"] == 0 and len(snapshot["heats"]) == 4 and snapshot["heats"][0]["rows"] is None
    published = subscriber.get_nowait()
    plan = published["race"]
    assert published["state"] == "running" and published["started"] == clock.now and published["countdown"] == race.COUNTDOWN
    assert 100000 <= plan["seed"] <= 999999 and plan["options"]["speed"] == 2.0 and plan["options"]["design"] == "paper"
    assert plan["options"]["font_css"].startswith('"Black Han Sans"') and plan["options"]["events"] == list(race.EVENTS["run"])
    assert race.build_plan("run", NAMES[:20], state.options, plan["seed"])["ranking"] == plan["ranking"]  # 시드로 다시 확인할 수 있음
    with pytest.raises(race.RaceError, match="지금 조가 끝난 뒤"):
        state.next()
    end = state.started + race.COUNTDOWN + plan["heats"][0]["end"] / 2.0 + race.SETTLE
    clock.now = end - 0.01
    state.settle()
    assert state.phase == "running"
    clock.now = end
    snapshot = state.snapshot()
    assert snapshot["state"] == "between" and snapshot["heats"][0]["rows"][0]["place"] == 1 and snapshot["heats"][1]["rows"] is None
    assert subscriber.get_nowait()["state"] == "between"
    for index in range(1, 4):
        clock.now += 5
        assert state.next()["heat"] == index
        clock.now = state.started + race.COUNTDOWN + plan["heats"][index]["end"] / 2.0 + race.SETTLE
        state.settle()
    assert state.phase == "done" and notes == [state.last_result["line"]]
    result = state.last_result
    assert result["winner"] == plan["winner"] and result["rank_label"] == "우승" and len(result["standing"]) == 20 and len(result["heats"]) == 4
    assert result["line"] == f"참여 레이스 우승: {plan['winner']['name']}(달리기 경주, 20명, 시드 {plan['seed']})"
    text = result["text"]
    assert text.startswith("debutkit 참여 레이스 결과\n") and f"시드: {plan['seed']}" in text and f"당첨(우승): {plan['winner']['name']}" in text
    assert "[전체 순위]" in text and "[경기 기록]" in text and "- 1조" in text and "- 결승" in text and ", 진출" in text and "붙여넣기" in text
    with pytest.raises(race.RaceError, match="모든 경기가 끝남"):
        state.next()
    stopped = state.stop()
    assert stopped["state"] == "idle" and stopped["last_result"] == result and state.channel.current["race"] is None


def test_practice_is_not_announced_and_survival_text():
    notes = []
    clock = Clock()
    state = race.RaceState(notify=notes.append, rng=random.Random(4), clock=clock, timers=False)
    state.start({"game": "survival", "practice": True, "practice_count": 12, "rank": "last"})
    assert state.race["practice"] and state.race["count"] == 12
    clock.now += 500
    state.settle()
    assert state.phase == "done" and notes == [] and state.last_result["practice"]
    text = state.last_result["text"]
    assert "연습 경기" in text and "생존" in text and "초 탈락" in text and "당첨(꼴찌 당첨)" in text


def test_sound_options_update_a_running_race():
    clock = Clock()
    state = race.RaceState(rng=random.Random(5), clock=clock, timers=False)
    state.start({"paste": "가\n나\n다"})
    subscriber, current = state.channel.subscribe()
    assert current["sound"] == {"on": True, "volume": 70, "listen": False}
    state.save({"listen": True, "volume": 40})
    update = subscriber.get_nowait()
    assert update["sound"] == {"on": True, "volume": 40, "listen": True} and update["race"]["id"] == current["race"]["id"]
    assert update["started"] == current["started"]  # 같은 경기(화면은 다시 그리지 않음)


def test_timer_settles_without_polling():
    notes = []
    clock = Clock()
    state = race.RaceState(notify=notes.append, rng=random.Random(6), clock=clock)
    state.start({"paste": "가\n나", "length": "short", "speed": 2.2})
    assert state._timer is not None and state._timer.daemon
    state.close()
    assert state._timer is None


# --------------------------------------------------------------------------- 서버


def request(srv, method, path, body=None, raw=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    payload = raw if raw is not None else json.dumps(body).encode() if body is not None else None
    conn.request(method, path, body=payload, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    return response.status, response.getheader("Content-Type"), response.read()


@pytest.fixture
def server():
    srv = OverlayServer([], port=0).start()
    yield srv
    srv.stop()


def race_state(srv):
    return next(part for part in srv.features if part.name == "race").post["/race/start"].__self__


def test_feature_is_registered_by_default():
    context = feature.Context(notify=lambda text: None, raffle=raffle.Raffle())
    parts = feature.default_features(context)
    found = next(part for part in parts if part.name == "race")
    assert "race" in found.feeds and found.static["/race"] == "race.html" and found.stop is not None


def test_pages_and_routes(server):
    for path, marker in (("/race", b"/race.js"), ("/race/control", "참여 레이스".encode()), ("/race.js", b"marbleSim"), ("/race.css", b".race-card")):
        status, _, body = request(server, "GET", path)
        assert status == 200 and marker in body, path
    status, _, body = request(server, "GET", "/race/config")
    config = json.loads(body)
    assert status == 200 and config["options"]["game"] == "marble" and config["choices"]["games"]["survival"] == "서바이벌"
    status, _, body = request(server, "POST", "/race/config", {"design": "metal", "rank": "last"})
    assert status == 200 and json.loads(body)["options"]["design"] == "metal" and settings.load_data(race.DATA_FILE)["rank"] == "last"
    status, _, body = request(server, "POST", "/race/config", {"speed": 3})
    assert status == 400 and "0.7에서 2.2" in json.loads(body)["error"]
    status, _, body = request(server, "POST", "/race/entries", {"paste": "가*2\n나"})
    assert status == 200 and json.loads(body)["count"] == 3
    status, _, body = request(server, "GET", "/race/sample?game=run&n=20&heat=2&design=paper")
    sample = json.loads(body)
    assert status == 200 and sample["race"]["practice"] and sample["heat"] == 2 and len(sample["race"]["heats"]) == 4
    assert request(server, "GET", "/race/sample?game=chess")[0] == 400
    assert request(server, "POST", "/race/next", {})[0] == 400
    status, _, body = request(server, "POST", "/race/start", {"paste": "가"})
    assert status == 400 and "2명 이상" in json.loads(body)["error"]


def test_start_live_feed_mid_race_join_and_chat_notice(server):
    server.raffle.start()
    server.raffle.add("치지직시청자", "chzzk", "chat")
    server.raffle.add("숲시청자", "soop", "donation")
    status, _, body = request(server, "POST", "/race/start", {"paste": "붙임1\n붙임2", "game": "survival", "length": "short"})
    started = json.loads(body)
    assert status == 200 and started["state"] == "running" and started["race"]["count"] == 4
    # 경기 중에 연 화면: 첫 값이 지금 계획과 시작 시각(이어서 그릴 수 있음)
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.request("GET", "/live?feeds=race")
    stream = conn.getresponse()
    assert stream.fp.readline().decode().strip() == "event: race"
    joined = json.loads(stream.fp.readline().decode().removeprefix("data: "))
    stream.close()
    conn.close()
    assert joined["state"] == "running" and joined["heat"] == 0 and joined["started"] == started["started"]
    assert joined["race"]["seed"] == started["race"]["seed"] and joined["race"]["game"] == "survival" and joined["countdown"] == race.COUNTDOWN
    assert sorted(joined["race"]["heats"][0]["names"]) == sorted(["치지직시청자", "숲시청자", "붙임1", "붙임2"])
    state = json.loads(request(server, "GET", "/race/state")[2])
    assert state["state"] == "running" and 0 <= state["elapsed"] < 5 and state["heat_end"] > state["now"] and state["raffle"] == 2
    # 시간이 지나면 결과 확정과 채팅창 안내(debutkit 시스템 줄)
    seen = []
    server.hub.taps.append(seen.append)
    machine = race_state(server)
    real = machine.clock
    machine.clock = lambda: real() + 600
    done = json.loads(request(server, "GET", "/race/state")[2])
    assert done["state"] == "done" and done["last_result"]["winner"]["name"] in joined["race"]["standing"]
    assert seen and seen[-1].platform == "system" and seen[-1].text.startswith("참여 레이스 우승: ")
    assert seen[-1].text == system_event(done["last_result"]["line"]).text
    assert json.loads(request(server, "POST", "/race/stop", {})[2])["state"] == "idle"
