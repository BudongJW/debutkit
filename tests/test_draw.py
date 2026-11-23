"""후원 추첨 연출: 설정 확인, 추첨 횟수 규칙, 확률, 결과 기록, 서버 주소, 명령줄."""

import http.client
import json
import random
import time
from collections import Counter

import pytest

from debutkit import cli, draw, settings
from debutkit.overlay.events import OverlayEvent, system_event
from debutkit.overlay.server import OverlayServer


def config(**changes):
    base = {"enabled": True, "prizes": [{"name": "꽝", "weight": 60}, {"name": "스티커", "weight": 36}, {"name": "소원", "weight": 4}],
            "rules": [{"min_won": 1000, "draws": 1}, {"min_won": 10000, "draws": 11}], "style": "card", "seconds": 8}
    return draw.from_request({**base, **changes})


def test_defaults_and_saved_values():
    first = draw.load_config()
    assert first.enabled is False and [prize.name for prize in first.prizes] == ["꽝", "감사 인사", "노래 한 곡", "소원 들어주기"]
    assert [(rule.min_won, rule.draws) for rule in first.rules] == [(10000, 11), (1000, 1)]
    draw.save_config(config(style="wheel", members=True, exact=True, seconds=12))
    saved = settings.load()
    assert saved["draw_prizes"] == ["60:꽝", "36:스티커", "4:소원"] and saved["draw_rules"] == ["10000:11", "1000:1"]
    loaded = draw.load_config()
    assert loaded.enabled and loaded.style == "wheel" and loaded.members and loaded.exact and loaded.seconds == 12
    entries = loaded.to_dict()["prizes"]
    assert [(entry["percent"], entry["rare"], entry["miss"]) for entry in entries] == [(60.0, False, True), (36.0, False, False), (4.0, True, False)]


def test_parse_skips_broken_saved_values():
    assert [prize.name for prize in draw.parse_prizes(["10:a:b", "x:y", "0:zero", "5:", "3:a:b", 7])] == ["a:b"]
    assert [(rule.min_won, rule.draws) for rule in draw.parse_rules(["1000:2", "1000:3", "a:1", "500:0", "500:31", "0:1"])] == [(1000, 3), (0, 1)]
    assert draw.load_config({"draw_style": "fireworks", "draw_seconds": 999}).style == "card"
    assert draw.load_config({"draw_seconds": 999}).seconds == 8


@pytest.mark.parametrize("changes, message", [
    ({"prizes": []}, "상품을 1개 이상"),
    ({"prizes": [{"name": " ", "weight": 1}]}, "상품 이름이 비어"),
    ({"prizes": [{"name": "가" * 41, "weight": 1}]}, "40자 이내"),
    ({"prizes": [{"name": "a", "weight": 1}, {"name": "a", "weight": 2}]}, "같은 이름의 상품"),
    ({"prizes": [{"name": "a", "weight": 0}]}, "0보다 큰 숫자"),
    ({"prizes": [{"name": "a", "weight": True}]}, "0보다 큰 숫자"),
    ({"prizes": [{"name": f"p{i}", "weight": 1} for i in range(31)]}, "30개까지"),
    ({"rules": []}, "규칙을 1개 이상"),
    ({"rules": [{"min_won": -1, "draws": 1}]}, "0 이상의 정수"),
    ({"rules": [{"min_won": 1000.5, "draws": 1}]}, "0 이상의 정수"),
    ({"rules": [{"min_won": 1000, "draws": 31}]}, "1에서 30"),
    ({"rules": [{"min_won": 1000, "draws": 1}, {"min_won": 1000, "draws": 2}]}, "같은 금액의 규칙"),
    ({"style": "slot"}, "card"),
    ({"seconds": 2}, "3초에서 60초"),
])
def test_invalid_settings_are_explained(changes, message):
    with pytest.raises(draw.DrawError, match=message):
        config(**changes)
    with pytest.raises(draw.DrawError):
        draw.from_request(["not", "a", "dict"])


def test_draw_counts_by_amount_unit_and_mode():
    at_least = config()
    assert draw.draws_for(at_least, "donation", 999, "원") == 0
    assert draw.draws_for(at_least, "donation", 1000, "원") == 1
    assert draw.draws_for(at_least, "donation", 9999, "원") == 1
    assert draw.draws_for(at_least, "donation", 100, "별풍선") == 11  # 별풍선 100개 = 10,000원
    assert draw.draws_for(at_least, "donation", 500, "bits") == 0  # 원으로 환산 못 하는 단위는 0원 규칙만
    assert draw.draws_for(config(rules=[{"min_won": 0, "draws": 2}]), "donation", 500, "bits") == 2
    exact = config(exact=True)
    assert draw.draws_for(exact, "donation", 1000, "원") == 1 and draw.draws_for(exact, "donation", 1500, "원") == 0
    assert draw.draws_for(exact, "donation", 10, "별풍선") == 1
    assert draw.draws_for(at_least, "member", 0, "") == 0 and draw.draws_for(config(members=True), "member", 0, "") == 1
    assert draw.draws_for(at_least, "chat", 5000, "원") == 0


def test_probabilities_follow_weights():
    rng = random.Random(7)
    found = Counter(item["name"] for item in draw.pick(config(), 20000, rng))
    assert abs(found["꽝"] / 20000 - 0.60) < 0.02 and abs(found["스티커"] / 20000 - 0.36) < 0.02 and abs(found["소원"] / 20000 - 0.04) < 0.01


def test_state_history_script_and_subscribers():
    state = draw.DrawState(history=3, rng=random.Random(1))
    subscriber, current = state.subscribe()
    assert current == {"seq": 0, "time": 0.0}
    result = state.run(config(), name="고양이집사", platform="soop", kind="donation", amount=100, unit="별풍선", count=11)
    assert result["seq"] == 1 and len(result["draws"]) == 11 and subscriber.get_nowait() is result
    assert result["script"].startswith("고양이집사 님 별풍선 100개 후원 감사합니다. 추첨 결과 ") and "회" in result["script"]
    assert [prize["name"] for prize in result["prizes"]] == ["꽝", "스티커", "소원"] and result["style"] == "card"
    member = state.run(config(), name="새 구독자", platform="chzzk", kind="member", amount=0, unit="", count=1)
    assert member["script"].startswith("새 구독자 님 구독 감사합니다. 추첨 결과 ")
    for _ in range(3):
        state.run(config(), name="a", platform="twitch", kind="donation", amount=500, unit="bits", count=99)
    recent = state.recent()
    assert len(recent) == 3 and recent[0]["seq"] == 5 and recent[0]["count"] == draw.MAX_DRAWS
    state.clear()
    assert state.recent() == []
    state.unsubscribe(subscriber)
    assert state._subscribers == []


def test_reactor_follows_saved_settings():
    state = draw.DrawState(rng=random.Random(3))
    reactor = draw.DrawReactor(state)
    donation = OverlayEvent("chzzk", "donation", "시청자", (("text", "응원"),), amount=10000.0, unit="원")
    reactor(donation)
    assert state.recent() == []  # 사용 꺼짐(기본)
    draw.save_config(config())
    reactor(donation)
    reactor(OverlayEvent("chzzk", "donation", "시청자", (), amount=500.0, unit="원"))  # 규칙 미달
    reactor(OverlayEvent("chzzk", "member", "구독자", ()))  # 구독 추첨 꺼짐
    reactor(OverlayEvent("chzzk", "chat", "시청자", (("text", "안녕"),)))
    reactor(system_event("연결"))
    reactor(OverlayEvent("demo", "donation", "테스트", (), amount=1000.0, unit="원"))
    recent = state.recent()
    assert [(item["count"], item["test"]) for item in recent] == [(1, True), (11, False)]


@pytest.fixture
def server():
    srv = OverlayServer([], port=0).start()
    yield srv
    srv.stop()


def request(srv, method, path, body=None, raw=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    payload = raw if raw is not None else json.dumps(body).encode() if body is not None else None
    conn.request(method, path, body=payload, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    return response.status, response.getheader("Content-Type"), response.read()


def test_pages_and_config_endpoints(server):
    for path, marker in (("/draw", b"/draw.js"), ("/draw/control", "후원 추첨".encode()), ("/draw.js", b"playWheel"), ("/draw.css", b".draw-card")):
        status, _, body = request(server, "GET", path)
        assert status == 200 and marker in body, path
    status, _, body = request(server, "GET", "/draw/config")
    assert status == 200 and json.loads(body)["enabled"] is False and json.loads(body)["styles"]["wheel"] == "룰렛"
    long = {"enabled": True, "prizes": [{"name": f"상품 이름이 조금 긴 경우 {i}번째", "weight": i + 1} for i in range(30)],
            "rules": [{"min_won": 1000, "draws": 1}], "style": "wheel", "seconds": 10}
    status, _, body = request(server, "POST", "/draw/config", long)
    assert status == 200 and len(json.loads(body)["prizes"]) == 30 and settings.load()["draw_style"] == "wheel"
    status, _, body = request(server, "POST", "/draw/config", {**long, "prizes": []})
    assert status == 400 and "상품을 1개 이상" in json.loads(body)["error"]
    assert request(server, "POST", "/draw/config", raw=b"not json")[0] == 400


def test_test_draw_history_clear_and_live_feed(server):
    request(server, "POST", "/draw/config", {"enabled": False, "prizes": [{"name": "스티커", "weight": 1}],
                                              "rules": [{"min_won": 1000, "draws": 1}, {"min_won": 10000, "draws": 3}]})
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.request("GET", "/live?feeds=draw")
    stream = conn.getresponse()

    def event():
        name = stream.fp.readline().decode().strip().removeprefix("event: ")
        data = json.loads(stream.fp.readline().decode().removeprefix("data: "))
        stream.fp.readline()
        return name, data

    assert event() == ("draw", {"seq": 0, "time": 0.0})  # draw만 요청하면 다른 항목은 보내지 않음
    status, _, body = request(server, "POST", "/draw/test", {"amount": 10000})
    result = json.loads(body)
    assert status == 200 and result["count"] == 3 and result["test"] and [item["name"] for item in result["draws"]] == ["스티커"] * 3
    name, data = event()
    assert name == "draw" and data["seq"] == result["seq"] and abs(data["time"] - time.time()) < 5
    status, _, body = request(server, "POST", "/draw/test", {"amount": 500})
    assert status == 400 and "규칙에 맞지 않는 금액" in json.loads(body)["error"]
    assert request(server, "POST", "/draw/test", {"amount": "많이"})[0] == 400
    assert len(json.loads(request(server, "GET", "/draw/history")[2])["results"]) == 1
    assert request(server, "POST", "/draw/clear", {})[0] == 200
    assert json.loads(request(server, "GET", "/draw/history")[2])["results"] == []
    stream.close()
    conn.close()


def test_donation_events_draw_when_enabled(server):
    request(server, "POST", "/draw/config", {"enabled": True, "prizes": [{"name": "스티커", "weight": 1}], "rules": [{"min_won": 1000, "draws": 2}]})
    server.hub.publish(OverlayEvent("soop", "donation", "별풍선 시청자", (), amount=10.0, unit="별풍선"))
    recent = json.loads(request(server, "GET", "/draw/history")[2])["results"]
    assert recent[0]["name"] == "별풍선 시청자" and recent[0]["count"] == 2 and recent[0]["platform"] == "soop"
    assert request(server, "POST", "/test", {"kind": "donation"})[0] == 200  # 설정 화면의 테스트 후원(1,000원)
    assert json.loads(request(server, "GET", "/draw/history")[2])["results"][0]["test"] is True


def test_default_live_feeds_unchanged(server):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.request("GET", "/live?feeds=unknown")
    stream = conn.getresponse()
    names = []
    for _ in range(3):
        names.append(stream.fp.readline().decode().strip().removeprefix("event: "))
        stream.fp.readline()
        stream.fp.readline()
    assert names == ["voice", "tracking", "motion"]
    stream.close()
    conn.close()


def test_scenes_include_the_draw_source():
    from debutkit.scenes import PREFIX, SceneOptions, build_scenes, default_kinds

    scenes = build_scenes(1920, 1080, default_kinds("Windows"), SceneOptions(os_name="Windows", draw_url="http://127.0.0.1:9000/draw"))
    with_draw = [scene.name for scene in scenes if any(item.source == f"{PREFIX}후원 추첨" for item in scene.items)]
    assert with_draw == ["대기 화면", "본방송", "토크", "자리 비움"]
    item = next(item for item in scenes[1].items if item.source == f"{PREFIX}후원 추첨")
    assert item.settings["url"] == "http://127.0.0.1:9000/draw" and item.transform["boundsWidth"] == 1920


def test_cli_show_set_and_test(capsys):
    assert cli.main(["draw", "show"]) == 0 and "사용 꺼짐" in capsys.readouterr().out
    assert cli.main(["draw", "set", "--on", "--prize", "90:꽝", "--prize", "10:사진", "--rule", "0:1", "--style", "wheel", "--members",
                     "--seconds", "5"]) == 0
    out = capsys.readouterr().out
    assert "사용 중" in out and "룰렛, 결과 표시 5초" in out and "1회 추첨" in out
    loaded = draw.load_config()
    assert [prize.name for prize in loaded.prizes] == ["꽝", "사진"] and loaded.members and loaded.seconds == 5
    assert cli.main(["draw", "set", "--off", "--exact", "--no-members"]) == 0
    loaded = draw.load_config()
    assert not loaded.enabled and loaded.exact and not loaded.members and [prize.name for prize in loaded.prizes] == ["꽝", "사진"]
    assert cli.main(["draw", "set", "--prize", "꽝"]) == 1 and "형식 오류" in capsys.readouterr().err
    assert cli.main(["draw", "set", "--rule", "1000:0"]) == 1 and "1에서 30" in capsys.readouterr().err
    srv = OverlayServer([], port=0).start()
    try:
        assert cli.main(["draw", "test", "--amount", "0", "--port", str(srv.port)]) == 0 and "시험 추첨 1회" in capsys.readouterr().out
        cli.main(["draw", "set", "--rule", "5000:2"])
        capsys.readouterr()
        assert cli.main(["draw", "test", "--amount", "1000", "--port", str(srv.port)]) == 1
        assert "규칙에 맞지 않는 금액" in capsys.readouterr().err
        port = srv.port
    finally:
        srv.stop()
    assert cli.main(["draw", "test", "--port", str(port)]) == 1 and "오버레이에 연결하지 못함" in capsys.readouterr().err
