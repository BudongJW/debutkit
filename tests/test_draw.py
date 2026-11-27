"""후원 추첨 연출: 설정 확인, 추첨 횟수 규칙, 확률, 결과 기록, 서버 주소, 명령줄."""

import http.client
import json
import random
import re
import time
from collections import Counter
from pathlib import Path

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
    for path, marker in (("/draw", b"/draw.js"), ("/draw/control", "후원 추첨".encode()), ("/draw.js", b"playWheel"), ("/draw.css", b".dk-card")):
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


def test_display_settings_validate_save_and_reach_results():
    draw.save_config(config(title="  벌칙 룰렛 ", position="right", scale=80, sound=True, show_percent=True))
    saved = settings.load()
    assert (saved["draw_title"], saved["draw_position"], saved["draw_scale"], saved["draw_sound"], saved["draw_show_percent"]) == ("벌칙 룰렛", "right", 80, True, True)
    loaded = draw.load_config()
    assert loaded.to_dict()["positions"]["right"] == "오른쪽 아래" and loaded.title == "벌칙 룰렛"
    result = draw.DrawState(rng=random.Random(2)).run(loaded, name="a", platform="chzzk", kind="donation", amount=1000, unit="원", count=1)
    assert (result["title"], result["position"], result["scale"], result["sound"], result["show_percent"]) == ("벌칙 룰렛", "right", 80, True, True)
    assert config(title="").title == draw.DEFAULT_TITLE
    for changes, message in (({"title": "가" * 21}, "20자 이내"), ({"position": "top"}, "center"), ({"scale": 150}, "60%에서 140%"), ({"scale": 85.5}, "60%에서 140%")):
        with pytest.raises(draw.DrawError, match=message):
            config(**changes)
    broken = draw.load_config({"draw_title": " ", "draw_position": "middle", "draw_scale": 999, "draw_sound": True})
    assert (broken.title, broken.position, broken.scale, broken.sound) == (draw.DEFAULT_TITLE, "center", 100, True)


def test_cli_display_flags(capsys):
    assert cli.main(["draw", "set", "--title", "벌칙 룰렛", "--position", "left", "--scale", "120", "--sound", "--show-percent"]) == 0
    out = capsys.readouterr().out
    assert "추첨 이름 벌칙 룰렛" in out and "왼쪽 아래, 크기 120%, 효과음 켬, 확률 표시" in out
    assert cli.main(["draw", "set", "--no-sound", "--no-show-percent"]) == 0
    loaded = draw.load_config()
    assert loaded.title == "벌칙 룰렛" and loaded.scale == 120 and not loaded.sound and not loaded.show_percent
    assert cli.main(["draw", "set", "--scale", "10"]) == 1 and "60%에서 140%" in capsys.readouterr().err


def test_fonts_are_bundled_and_served(server):
    css = request(server, "GET", "/draw.css")[2].decode()
    for name in ("BlackHanSans-Regular.woff2", "Pretendard-SemiBold.subset.woff2", "Pretendard-Bold.subset.woff2"):
        assert f"/vendor/fonts/{name}" in css
        status, kind, body = request(server, "GET", f"/vendor/fonts/{name}")
        assert status == 200 and kind == "font/woff2" and body[:4] == b"wOF2", name
    for license_ in ("OFL-BlackHanSans.txt", "OFL-Pretendard.txt"):
        assert b"SIL Open Font License" in request(server, "GET", f"/vendor/fonts/{license_}")[2]


# --------------------------------------------------------------------------- 연출 추가: 모양, 효과, 글꼴, 한마디, 대본 창, 기록 창


def test_look_defaults_and_round_trip():
    first = draw.load_config()
    assert (first.design, first.effect, first.name_font, first.name_size, first.caption_font, first.caption_size, first.advice, first.advice_lines) == (
        "basic", "none", "blackhan", "medium", "blackhan", "medium", True, [])
    draw.save_config(config(style="capsule", design="box", effect="stars", name_font="batang", name_size="large", caption_font="gungsuh",
                            caption_size="small", advice=False, advice_lines=[" 물 한 잔 ", "", "물 한 잔", "오늘도 좋은 날"]))
    saved = settings.load()
    assert (saved["draw_style"], saved["draw_design"], saved["draw_effect"], saved["draw_name_font"], saved["draw_name_size"]) == (
        "capsule", "box", "stars", "batang", "large")
    assert (saved["draw_caption_font"], saved["draw_caption_size"], saved["draw_advice"], saved["draw_advice_lines"]) == (
        "gungsuh", "small", False, ["물 한 잔", "오늘도 좋은 날"])
    loaded = draw.load_config()
    assert loaded.to_settings() == {key: value for key, value in saved.items() if key.startswith("draw_")}
    shown = loaded.to_dict()
    assert shown["designs"]["capsule"]["box"] == "네모 유리창" and shown["effects"]["none"] == "없음" and shown["sizes"]["large"] == "크게"
    assert {"blackhan", "pretendard", "batang", "gungsuh", "jua", "galmuri"} <= set(shown["fonts"]) and len(shown["fonts"]) >= 20  # 공통 글꼴 목록
    assert shown["font_css"]["jua"][0].startswith('"Jua"') and shown["advice_example"] == "물 한 잔"
    assert draw.load_config({"draw_name_font": "serif", "draw_caption_font": "text"}).name_font == "batang"  # 예전 이름은 새 이름으로
    assert set(draw.DESIGNS) == set(draw.STYLES) and all(len(draw.DESIGNS[style]) >= 3 for style in draw.STYLES if style not in ("card", "wheel"))
    assert len([effect for effect in draw.EFFECTS if effect != "none"]) >= 5


def test_saved_settings_from_before_load_unchanged():
    old = {"draw_enabled": True, "draw_prizes": ["90:꽝", "10:사진"], "draw_rules": ["0:1"], "draw_style": "wheel", "draw_seconds": 5, "draw_title": "벌칙 룰렛",
           "draw_position": "left", "draw_scale": 120, "draw_sound": True, "draw_show_percent": True}
    loaded = draw.load_config(old)
    assert (loaded.style, loaded.seconds, loaded.title, loaded.position, loaded.scale, loaded.sound, loaded.show_percent) == ("wheel", 5, "벌칙 룰렛", "left", 120, True, True)
    assert (loaded.design, loaded.effect, loaded.name_font, loaded.advice) == ("basic", "none", "blackhan", True)  # 예전 이름 display도
    broken = draw.load_config({"draw_style": "drum", "draw_design": "box", "draw_effect": "boom", "draw_name_font": "Comic Sans", "draw_name_size": "huge",
                               "draw_caption_font": 3, "draw_advice_lines": ["가" * 41, "좋은 날", 7]})
    assert (broken.design, broken.effect, broken.name_font, broken.name_size, broken.caption_font, broken.advice_lines) == (
        "classic", "none", "blackhan", "medium", "blackhan", ["좋은 날"])


@pytest.mark.parametrize("changes, message", [
    ({"style": "capsule", "design": "basic"}, "캡슐 뽑기 모양은 round"),
    ({"style": "drum", "design": "box"}, "추첨기 모양은 classic"),
    ({"effect": "boom"}, "효과는 none"),
    ({"name_font": "Comic Sans"}, "상품 이름 글꼴은 목록에서"),
    ({"caption_font": None}, "안내 글꼴은"),
    ({"name_size": "huge"}, "상품 이름 크기는 small"),
    ({"caption_size": 3}, "안내 글 크기는"),
    ({"advice_lines": [f"문장 {i}" for i in range(31)]}, "30개까지"),
    ({"advice_lines": ["가" * 41]}, "40자 이내"),
    ({"advice_lines": [3]}, "문장 목록"),
    ({"style": "fireworks"}, "tarot"),
])
def test_look_settings_are_explained(changes, message):
    with pytest.raises(draw.DrawError, match=message):
        config(**changes)


def test_missing_look_keys_keep_saved_values():
    draw.save_config(config(style="tarot", design="sun", effect="hearts", name_font="text", advice_lines=["좋은 날"]))
    kept = config(style="tarot", title="타로 추첨")  # 이 항목을 모르는 명령줄처럼
    assert (kept.design, kept.effect, kept.name_font, kept.advice_lines, kept.title) == ("sun", "hearts", "pretendard", ["좋은 날"], "타로 추첨")
    moved = config(style="scratch")  # 저장한 모양이 새 연출에 없으면 그 연출의 기본 모양
    assert moved.design == "classic" and moved.effect == "hearts"
    assert config(style="ticket", design="").design == "stub" and config(advice_lines="첫 줄\n\n둘째 줄").advice_lines == ["첫 줄", "둘째 줄"]


def test_results_carry_look_and_tarot_advice():
    state = draw.DrawState(rng=random.Random(5))
    tarot = config(style="tarot", design="pink", effect="fireworks", caption_font="serif", advice_lines=["하나", "둘"])
    result = state.run(tarot, name="a", platform="chzzk", kind="donation", amount=1000, unit="원", count=3)
    assert (result["style"], result["design"], result["effect"], result["caption_font"], result["name_size"]) == ("tarot", "pink", "fireworks", "batang", "medium")
    assert result["advice"] in ("하나", "둘") and result["script"].endswith(f". 오늘의 한마디 {result['advice']}")
    assert state.run(config(style="tarot"), name="a", platform="chzzk", kind="donation", amount=1000, unit="원", count=1)["advice"] in draw.ADVICE
    assert state.run(config(style="tarot", advice=False), name="a", platform="chzzk", kind="donation", amount=1000, unit="원", count=1)["advice"] == ""
    plain = state.run(config(style="capsule", advice_lines=["하나"]), name="a", platform="chzzk", kind="donation", amount=1000, unit="원", count=1)
    assert plain["advice"] == "" and "한마디" not in plain["script"]
    assert all(0 < len(line) <= draw.MAX_ADVICE_LENGTH for line in draw.ADVICE)


def test_every_style_design_effect_and_font_has_page_code(server):
    script = request(server, "GET", "/draw.js")[2].decode() + request(server, "GET", "/draw-props.js")[2].decode()
    css = request(server, "GET", "/draw.css")[2].decode()
    page = request(server, "GET", "/draw")[2].decode()
    assert page.index("/draw-props.js") < page.index("/draw.js")  # 소품 연출을 먼저 불러와야 draw.js가 목록에 넣음
    for style, designs in draw.DESIGNS.items():
        assert re.search(rf"\b{style}: play\w+", script), style
        for design in designs if style not in ("card", "wheel") else ():
            assert f'"{design}"' in script, (style, design)
    for effect in draw.EFFECTS:
        assert effect == "none" or re.search(rf"\n    {effect}\(", script), effect
        assert effect in ("none", "confetti") or f".dk-fx.{effect}" in css, effect
    # 글꼴은 서버가 보낸 CSS(공통 글꼴 목록)로. 예전 이름(display, text, gothic, serif)은 서버가 새 이름으로 바꿔 보냄
    assert "result.font_css" in script and "config.font_css" in script
    assert all(key in draw.FONTS for key in ("blackhan", "pretendard", "jua", "gowunbatang", "galmuri"))
    for size in draw.SIZES:
        assert f"{size}: " in script, size


def test_script_and_log_pages(server):
    status, kind, body = request(server, "GET", "/draw/script")
    assert status == 200 and kind.startswith("text/html") and b"/live?feeds=draw" in body and "추첨 대본".encode() in body
    status, kind, body = request(server, "GET", "/draw/log")
    assert status == 200 and kind.startswith("text/html") and b"/draw/history" in body and "상품별 합계".encode() in body
    for page in (body, request(server, "GET", "/draw/script")[2]):
        assert b"innerHTML" not in page  # 글은 textContent로만
    control = request(server, "GET", "/draw/control")[2].decode()
    assert "/draw/script" in control and "/draw/log" in control and 'id="sample-frame"' in control and 'id="design"' in control
    status, _, body = request(server, "POST", "/draw/config", {"enabled": False, "prizes": [{"name": "스티커", "weight": 1}],
                                                               "rules": [{"min_won": 0, "draws": 1}], "style": "drum", "design": "wood",
                                                               "effect": "spotlight", "advice_lines": ["좋은 날"]})
    assert status == 200 and json.loads(body)["design"] == "wood" and settings.load()["draw_effect"] == "spotlight"
    status, _, body = request(server, "POST", "/draw/config", {"prizes": [{"name": "a", "weight": 1}], "rules": [{"min_won": 0, "draws": 1}],
                                                               "style": "drum", "design": "night", "effect": "boom"})
    assert status == 400 and "효과는" in json.loads(body)["error"]
    result = json.loads(request(server, "POST", "/draw/test", {"amount": 0})[2])
    assert result["design"] == "wood" and result["effect"] == "spotlight" and result["advice"] == ""


def test_more_designs_for_every_prop():
    """미타도네이션 대응: 연출 디자인 32종(캡슐 8, 복권 6, 티켓 8, 추첨기 5, 타로 3, 카드와 룰렛 1). 새 디자인마다 그림 코드나 CSS."""
    import re

    sizes = {style: len(designs) for style, designs in draw.DESIGNS.items()}
    assert sizes == {"card": 1, "wheel": 1, "capsule": 8, "scratch": 6, "ticket": 8, "drum": 5, "tarot": 3} and sum(sizes.values()) == 32
    static = Path(__file__).resolve().parent.parent / "src" / "debutkit" / "overlay" / "static"
    props = (static / "draw-props.js").read_text(encoding="utf-8")
    css = (static / "draw.css").read_text(encoding="utf-8")
    capsule = props.split("const CAPSULE_LOOK = {", 1)[1].split("};", 1)[0]
    drum = props.split("const DRUM_LOOK = {", 1)[1].split("};", 1)[0]
    base = dict(re.findall(r'(\w+): "(\w+)"', props.split("const TICKET_BASE = {", 1)[1].split("};", 1)[0]))
    for design in draw.DESIGNS["capsule"]:
        assert f"{design}: {{" in capsule, design
    for design in draw.DESIGNS["drum"]:
        assert f"{design}: {{" in drum, design
    assert set(base) == set(draw.DESIGNS["ticket"]) and set(base.values()) == {"stub", "receipt", "coupon"}
    for design in ("concert", "movie", "boarding", "gift", "shop"):
        assert f".dk-ticket.{base[design]}.{design}" in css and f'.dk-printer[data-design="{design}"]' in css, design
    for design in ("pastel", "gold", "mint"):
        assert f'.dk-lotto[data-design="{design}"]' in css, design
    assert 'design === "gold" ? COATS.gold : COATS.silver' in props  # 금박 복권은 금색 막
