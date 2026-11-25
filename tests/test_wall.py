"""후원 벽: 칸 나누기, 시그니처, 오라, 저장과 비우기 되돌리기, 카드 옮기기, 그림 올리기 확인, 목표와 순위, 서버 주소, 여러 플랫폼 후원."""

import base64
import http.client
import json
import struct
import zlib

import pytest

from debutkit import settings, wall
from debutkit.overlay.events import OverlayEvent, system_event
from debutkit.overlay.server import OverlayServer


def png(width=2, height=2, extra=0):
    """작은 PNG(``extra`` 바이트만큼 뒤에 덧붙여 크기 시험)."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xff\x4f\x8b" * width for _ in range(height))
    body = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    return body + b"\x00" * extra


GIF = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"


def b64(data):
    return base64.b64encode(data).decode()


def card(amount, unit, name="시청자", platform="soop", **extra):
    return {"id": extra.pop("id", 1), "name": name, "amount": float(amount), "unit": unit, "platform": platform, "time": 1.0, **extra}


# --------------------------------------------------------------------------- 순수 계산


@pytest.mark.parametrize("unit, amount, mode, key, label", [
    ("별풍선", 34, "lead", "별풍선/10/30", ("30~39", "개")),
    ("별풍선", 44, "lead", "별풍선/10/40", ("40~49", "개")),
    ("별풍선", 340, "lead", "별풍선/100/300", ("300~399", "개")),
    ("별풍선", 5, "lead", "별풍선/1/5", ("5", "개")),
    ("별풍선", 34, "digits", "별풍선/d/10", ("10~99", "개")),
    ("별풍선", 59, "digits", "별풍선/d/10", ("10~99", "개")),
    ("별풍선", 34, "exact", "별풍선/0/34", ("34", "개")),
    ("별풍선", 34, "10", "별풍선/10/30", ("30~39", "개")),
    ("별풍선", 7, "10", "별풍선/10/0", ("1~9", "개")),
    ("별풍선", 1234, "100", "별풍선/100/1200", ("1,200~1,299", "개")),
    ("애드벌룬", 1500, "1000", "애드벌룬/1000/1000", ("1천", "개대")),  # 긴 범위(1,000~1,999) 대신
    ("별풍선", 12000, "lead", "별풍선/10000/10000", ("1만", "개대")),
    ("별풍선", 500, "1000", "별풍선/1000/0", ("1천", "개 미만")),
    ("별풍선", 3400, "digits", "별풍선/d/1000", ("천", "개대")),
    ("원", 5000, "lead", "원/1000/5000", ("5천", "원대")),
    ("원", 34000, "lead", "원/10000/30000", ("3만", "원대")),
    ("원", 12000, "1000", "원/1000/12000", ("1만 2천", "원대")),
    ("원", 500, "1000", "원/1000/0", ("1천", "원 미만")),
    ("원", 150000, "10000", "원/10000/150000", ("15만", "원대")),
    ("원", 34000, "digits", "원/d/10000", ("만", "원대")),
    ("원", 1004, "exact", "원/0/1004", ("1,004", "원")),
    ("bits", 500, "lead", "bits/100/500", ("500~599", "비트")),
    ("bits", 10000, "lead", "bits/10000/10000", ("1만", "비트대")),
    ("USD", 4.99, "exact", "USD/0/4.99", ("4.99", "")),
    ("USD", 15.5, "10", "USD/10/10", ("10~19.99", "")),
    ("미션", 3, "lead", "미션/1/3", ("3", "")),  # 앞으로 생길 단위(SOOP 미션 등)도 이름 그대로 칸
])
def test_bucketing_per_unit_and_mode(unit, amount, mode, key, label):
    assert wall.bucket_key(unit, amount, mode) == key
    info = wall.column_info(key, wall.load_config({}))
    assert (info["number"], info["suffix"]) == label and info["kind"] == "bucket" and info["unit"] == unit


def test_units_and_texts():
    assert [wall.unit_of(raw) for raw in ("별풍선", "원", "KRW", "BITS", "usd", "미션", "", "a/b", "sig", "외화", "x" * 11)] == \
        ["별풍선", "원", "원", "bits", "USD", "미션", None, None, None, None, None]
    assert [wall.amount_text(amount, unit) for amount, unit in ((34, "별풍선"), (5000, "원"), (500, "bits"), (4.99, "USD"), (3, "미션"))] == \
        ["34개", "5,000원", "500비트", "USD 4.99", "미션 3"]
    assert wall.won_short(120_000_000) == "1억 2,000만" and wall.won_short(1234) == "1,234" and wall.won_short(30_000) == "3만"
    config = wall.load_config({"buckets": {"원": "10000", "외화": "10"}})
    assert wall.natural_column(card(34000, "원"), config) == "원/10000/30000"
    assert wall.natural_column(card(15, "JPY"), config) == "JPY/10/10"  # 통화 코드는 외화 설정


def test_signature_routing_and_hidden_number():
    config = wall.load_config({})
    config["signatures"] = [{"id": "aaaa1111", "unit": "별풍선", "amount": 1004.0, "title": "천사", "hide_number": True, "image": ""},
                            {"id": "bbbb2222", "unit": "원", "amount": 10000.0, "title": "", "hide_number": False, "image": ""}]
    assert wall.natural_column(card(1004, "별풍선"), config) == "sig/aaaa1111"
    assert wall.natural_column(card(1003, "별풍선"), config) == "별풍선/1000/1000"
    assert wall.natural_column(card(10000, "원"), config) == "sig/bbbb2222"
    assert wall.natural_column(card(100, "별풍선"), config) == "별풍선/100/100"  # 같은 원 금액이어도 단위가 다르면 시그니처 아님
    info = wall.column_info("sig/aaaa1111", config)
    assert info["kind"] == "sig" and info["hide_number"] and info["title"] == "천사" and info["tag"] == "시그니처"
    assert wall.column_info("sig/zzzz9999", config) is None


def test_aura_tier_selection():
    tiers = wall.load_config({})["auras"]
    assert wall.aura_for("별풍선", 99, tiers) is None
    assert wall.aura_for("별풍선", 100, tiers) == {"effect": "glow", "strength": 100, "tier": 1, "tiers": 4}
    assert wall.aura_for("별풍선", 999, tiers)["effect"] == "shimmer"
    assert wall.aura_for("별풍선", 50000, tiers)["effect"] == "gold" and wall.aura_for("별풍선", 50000, tiers)["tier"] == 4
    assert wall.aura_for("원", 100000, tiers)["effect"] == "stardust"
    assert wall.aura_for("USD", 1000, tiers) is None
    custom = wall.update_config(wall.load_config({}), {"auras": [{"unit": "USD", "min": 5, "effect": "gold", "strength": 200},
                                                                {"unit": "USD", "min": 1, "effect": "glow", "strength": 30}]})["auras"]
    assert [tier["min"] for tier in custom] == [1, 5] and wall.aura_for("USD", 4.99, custom)["strength"] == 30


@pytest.mark.parametrize("changes, message", [
    ({"buckets": {"별풍선": "10000"}}, "칸 나누기 방식"),
    ({"buckets": {"a/b": "lead"}}, "알 수 없는 단위"),
    ({"auras": [{"unit": "별풍선", "min": 0, "effect": "glow"}]}, "0보다 큰 숫자"),
    ({"auras": [{"unit": "별풍선", "min": 10, "effect": "fire"}]}, "오라 효과"),
    ({"auras": [{"unit": "별풍선", "min": 10, "effect": "glow", "strength": 250}]}, "30%에서 200%"),
    ({"auras": [{"unit": "원", "min": 10, "effect": "glow"}, {"unit": "원", "min": 10, "effect": "gold"}]}, "같은 단위, 같은 금액"),
    ({"entrance": "explode"}, "등장 연출"),
    ({"idle": "spin"}, "대기 효과"),
    ({"fast_after": 1}, "빠른 진행"),
    ({"names": "yes"}, "참 또는 거짓"),
    ({"goal": {"basis": "won", "target": 0}}, "목표는 0보다 큰"),
    ({"goal": {"basis": "USD", "target": 10}}, "목표 기준"),
    ({"goal": {"basis": "won", "target": 100, "milestones": [{"at": 200}]}}, "목표 이하"),
    ({"goal": {"basis": "won", "target": 100, "title": "가" * 21}}, "20자 이내"),
    ({"rank": {"count": 0}}, "1에서 20"),
    ({"rank": {"count": 5, "others": "convert"}}, "separate"),
])
def test_invalid_settings_are_explained(changes, message):
    with pytest.raises(wall.WallError, match=message):
        wall.update_config(wall.load_config({}), changes)


def test_broken_saved_values_fall_back_per_field():
    config = wall.load_config({"entrance": "nope", "idle": "sway", "buckets": "x", "signatures": [{"unit": "별풍선", "amount": -1}, {"id": "abcd1234", "unit": "원",
                                                                                                                                "amount": 5000, "image": "../x.png"}],
                               "columns": {"원/0/5": {"image": "../../evil.png"}}})
    assert config["entrance"] == "pop" and config["idle"] == "sway" and config["buckets"] == wall.DEFAULT_BUCKETS
    assert [(item["id"], item["image"]) for item in config["signatures"]] == [("abcd1234", "")] and config["columns"] == {}


def test_goal_and_rank_math():
    cards = [card(100, "별풍선", "고양이집사", id=1), card(5000, "원", "고양이집사", "chzzk", id=2), card(20000, "원", "새벽감성", "youtube", id=3),
             card(30, "별풍선", "고양이집사", id=4), card(500, "bits", "Haru", "twitch", id=5), card(5, "USD", "lurker", "youtube", id=6),
             card(1000, "애드벌룬", "숲속토끼", id=7), card(13000, "원", "도토리", "chzzk", id=8)]
    goal = wall.goal_progress(cards, {"title": "목표", "basis": "won", "target": 50000, "milestones": [{"at": 30000, "label": "노래"}, {"at": 50000, "label": ""}]})
    assert goal["current"] == 13000 + 5000 + 20000 + 13000 and goal["percent"] == 102.0 and goal["reached"]
    assert [item["reached"] for item in goal["milestones"]] == [True, True] and goal["milestones"][0]["position"] == 60.0
    balloons = wall.goal_progress(cards, {"title": "별풍선", "basis": "별풍선", "target": 1000, "milestones": [{"at": 500, "label": ""}]})
    assert balloons["current"] == 130 and balloons["percent"] == 13.0 and balloons["next"]["at"] == 500 and balloons["target_text"] == "1,000개"
    rank = wall.ranking(cards, {"title": "순위", "count": 3, "others": "separate"})
    # SOOP 고양이집사(별풍선 130개 = 13,000원)와 치지직 고양이집사(5,000원)는 다른 사람. 같은 합계는 같은 순위, 먼저 후원한 사람이 위
    assert [(entry["rank"], entry["name"], entry["platform"], entry["won"]) for entry in rank["entries"]] == \
        [(1, "새벽감성", "youtube", 20000), (2, "고양이집사", "soop", 13000), (2, "도토리", "chzzk", 13000)]
    assert [entry["text"] for entry in rank["others"]] == ["애드벌룬 1,000개", "500비트", "USD 5"] and rank["excluded"] == 3
    assert wall.ranking(cards, {"title": "순위", "count": 3, "others": "exclude"})["others"] == []


def test_export_text_counts_per_donor():
    cards = [card(10, "별풍선", "치즈냥", id=1), card(34, "별풍선", "치즈냥", id=2), card(5000, "원", "고양이집사", "chzzk", id=3, test=True)]
    text = wall.export_text(cards, [{"title": "", "tag": "별풍선", "number": "30~39", "suffix": "개", "count": 1}], now=0)
    assert "카드 3장" in text and "[별풍선] 2건, 합계 별풍선 44개" in text and "1. 치즈냥(SOOP) 2건, 별풍선 44개" in text
    assert "고양이집사(치지직 시험) 1건, 5,000원" in text and "별풍선 30~39개: 1건" in text
    assert "카드 없음" in wall.export_text([], [])


def test_arrange_flows_columns_and_keeps_pinned():
    columns = [{"key": f"별풍선/1/{i}", "kind": "bucket"} for i in range(12)] + [{"key": "sig/a", "kind": "sig"}]
    wall.arrange(columns, {"별풍선/1/3": {"x": 900, "y": 700, "w": 300, "h": 300}})
    pinned = next(column for column in columns if column["key"] == "별풍선/1/3")
    assert pinned["pinned"] and (pinned["x"], pinned["w"]) == (900, 300)
    auto = [column for column in columns if not column["pinned"]]
    assert all(column["x"] + column["w"] <= 1920 - wall.MARGIN + 1 for column in auto) and len({column["y"] for column in auto}) == 2
    assert all(column["y"] + column["h"] <= 1080 - wall.MARGIN + 1 for column in auto)


# --------------------------------------------------------------------------- 상태, 저장


def test_cards_persist_and_clear_undo_timing():
    now = [100.0]
    state = wall.Wall(clock=lambda: now[0])
    state.add("치즈냥", 34, "별풍선", "soop")
    state.add("", 5000, "원", "chzzk")
    assert state.add("x", 0, "원", "chzzk") is None and state.add("x", 10, "", "chzzk") is None
    state.flush()
    saved = settings.load_data("wall.json")
    assert [(item["name"], item["amount"], item["unit"], item["platform"]) for item in saved["cards"]] == [("치즈냥", 34, "별풍선", "soop"), ("익명", 5000, "원", "chzzk")]
    again = wall.Wall(clock=lambda: now[0])
    assert len(again.cards) == 2 and again.seq == 2
    assert again.clear() == {"cleared": 2, "undo": wall.UNDO_SECONDS}
    assert settings.load_data("wall.json")["cards"] == []  # 비우면 파일에서 바로 지움(되돌리기 전 카드는 메모리에만)
    again.add("새 후원", 10, "별풍선", "soop")  # 비운 뒤 온 후원은 되돌려도 남는다
    now[0] += wall.UNDO_SECONDS - 0.1
    assert again.undo()["restored"] == 2 and [item["id"] for item in again.cards] == [1, 2, 3]
    with pytest.raises(wall.WallError, match="되돌릴 비우기가 없음"):
        again.undo()
    again.clear()
    now[0] += wall.UNDO_SECONDS + 0.1
    with pytest.raises(wall.WallError, match="8초"):
        again.undo()
    assert again.cards == [] and settings.load_data("wall.json")["cards"] == []


def test_auto_clear_when_overlay_starts():
    notes = []
    state = wall.Wall(notify=notes.append)
    state.add("a", 10, "별풍선", "soop")
    state.update({"auto_clear": True})
    restarted = wall.Wall(notify=notes.append)
    assert restarted.cards == [] and "오버레이 시작 때 비움" in notes[-1] and restarted.undo()["restored"] == 1


def test_detach_restore_and_remove():
    state = wall.Wall()
    first = state.add("a", 34, "별풍선", "soop")
    second = state.add("b", 59, "별풍선", "soop")
    state.add("c", 5000, "원", "chzzk")
    assert state.detach({"card": first["id"], "column": "별풍선/10/50"})["column"] == "별풍선/10/50"
    columns, placed = state._columns()
    assert placed[first["id"]] == "별풍선/10/50" and {column["key"] for column in columns} == {"별풍선/10/50", "원/1000/5000"}
    assert next(column for column in columns if column["key"] == "별풍선/10/50")["count"] == 2
    state.detach({"card": second["id"], "column": "solo"})
    columns, placed = state._columns()
    assert placed[second["id"]] == f"solo/{second['id']}" and next(c for c in columns if c["kind"] == "solo")["number"] == "59"
    with pytest.raises(wall.WallError, match="옮길 칸 없음"):
        state.detach({"card": first["id"], "column": "별풍선/10/90"})
    with pytest.raises(wall.WallError, match="카드 없음"):
        state.detach({"card": 999, "column": "solo"})
    state.restore({"card": first["id"]})
    state.restore({"card": second["id"]})
    assert state._columns()[1] == {1: "별풍선/10/30", 2: "별풍선/10/50", 3: "원/1000/5000"}
    state.add("t", 10, "별풍선", "demo", test=True)
    assert state.remove({"tests": True})["removed"] == 1 and state.remove({"card": 3})["cards"] == 2


def test_names_hidden_in_broadcast_view_only():
    state = wall.Wall()
    state.add("치즈냥", 100, "별풍선", "soop")
    state.update({"names": False})
    view = state.view()
    assert view["cards"][0]["name"] == "" and view["options"]["names"] is False
    assert state.view(part="rank")["rank"]["entries"][0]["name"] == ""
    assert state.status()["cards"][0]["name"] == "치즈냥"  # 조작 화면(이 PC)에는 그대로


def test_image_upload_validation_and_storage():
    state = wall.Wall()
    with pytest.raises(wall.WallError, match="PNG, GIF, WebP, JPEG"):
        state.save_signature({"unit": "별풍선", "amount": 1004, "image": b64(b"<svg onload=alert(1)>")})
    with pytest.raises(wall.WallError, match="8MB"):
        state.save_signature({"unit": "별풍선", "amount": 1004, "image": b64(png(extra=wall.MAX_IMAGE))})
    with pytest.raises(wall.WallError, match="읽지 못함"):
        state.save_signature({"unit": "별풍선", "amount": 1004, "image": "!!!"})
    assert not (wall.image_folder().exists() and any(wall.image_folder().iterdir()))  # 거절한 그림은 저장하지 않음
    saved = state.save_signature({"unit": "별풍선", "amount": 1004, "title": "천사", "hide_number": True, "filename": "../../evil.png",
                                  "image": "data:image/png;base64," + b64(png())})["signature"]
    name = saved["image"]
    assert wall._IMAGE_NAME.fullmatch(name) and name.endswith(".png") and (wall.image_folder() / name).read_bytes() == png()
    assert list(wall.image_folder().iterdir()) == [wall.image_folder() / name]
    updated = state.save_signature({"id": saved["id"], "unit": "별풍선", "amount": 1004, "image": b64(GIF)})["signature"]
    assert updated["image"].endswith(".gif") and not (wall.image_folder() / name).exists()  # 바꾼 그림의 옛 파일은 지움
    with pytest.raises(wall.WallError, match="같은 금액의 시그니처"):
        state.save_signature({"unit": "별풍선", "amount": 1004})
    raw = state.image({"name": [updated["image"]]})
    assert raw.content_type == "image/gif" and raw.body == GIF and "sandbox" in raw.policy
    for trick in ("../wall.json", "wall.json", "..\\x.png", updated["image"].upper(), updated["image"] + "\n", "/etc/passwd", ""):
        with pytest.raises(wall.WallError, match="그림 없음"):
            state.image({"name": [trick]})
    state.remove_signature({"id": saved["id"]})
    assert state.config["signatures"] == [] and list(wall.image_folder().iterdir()) == []


# --------------------------------------------------------------------------- 서버


@pytest.fixture
def server():
    srv = OverlayServer([], port=0).start()
    yield srv
    srv.stop()


def request(srv, method, path, body=None, raw=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    payload = raw if raw is not None else json.dumps(body).encode() if body is not None else None
    conn.request(method, path, body=payload, headers={"Content-Type": "application/json", **(headers or {})})
    response = conn.getresponse()
    return response.status, response.getheader("Content-Type"), response.read()


def call(srv, path, body=None):
    status, _, data = request(srv, "POST", path, body or {})
    return status, json.loads(data)


def test_pages_and_static_files(server):
    for path, marker in (("/wall", b"/wall.js"), ("/wall/goal", b"/wall.js"), ("/wall/rank", b"/wall.js"), ("/wall/control", "후원 벽".encode()),
                         ("/wall.js", b"wallView"), ("/wall.css", b".wl-card")):
        status, _, body = request(server, "GET", path)
        assert status == 200 and marker in body, path
    assert request(server, "GET", "/wall/state", headers={"Origin": "https://evil.example"})[0] == 403
    css = request(server, "GET", "/wall.css")[2].decode()
    for name in ("BlackHanSans-Regular.woff2", "Pretendard-Bold.subset.woff2"):
        assert f"/vendor/fonts/{name}" in css


def test_events_from_all_platforms_reach_the_wall(server):
    events = [OverlayEvent("soop", "donation", "숲속토끼", (), amount=34.0, unit="별풍선"), OverlayEvent("soop", "donation", "밤하늘", (), amount=1000.0, unit="애드벌룬"),
              OverlayEvent("chzzk", "donation", "치즈냥", (("text", "응원"),), amount=5000.0, unit="원"),
              OverlayEvent("youtube", "donation", "별빛", (), amount=10000.0, unit="원"), OverlayEvent("youtube", "donation", "lurker", (), amount=4.99, unit="USD"),
              OverlayEvent("twitch", "donation", "Haru", (), amount=500.0, unit="bits"),
              OverlayEvent("chzzk", "chat", "치즈냥", (("text", "안녕"),)), OverlayEvent("chzzk", "member", "구독자", ()), system_event("연결")]
    for event in events:
        server.hub.publish(event)
    state = json.loads(request(server, "GET", "/wall/state")[2])
    assert [(item["platform"], item["unit"]) for item in reversed(state["cards"])] == [("soop", "별풍선"), ("soop", "애드벌룬"), ("chzzk", "원"), ("youtube", "원"),
                                                                                         ("youtube", "USD"), ("twitch", "bits")]
    assert {column["key"] for column in state["columns"]} == {"별풍선/10/30", "애드벌룬/1000/1000", "원/1000/5000", "원/10000/10000", "USD/0/4.99", "bits/100/500"}
    assert state["goal"]["current"] == 3400 + 5000 + 10000 and state["rank"]["excluded"] == 3
    assert request(server, "POST", "/test", {"kind": "donation"})[0] == 200  # 설정 화면의 테스트 후원(1,000원)은 시험 카드
    assert json.loads(request(server, "GET", "/wall/state")[2])["cards"][0]["test"] is True


def test_live_feed_state_add_replay_and_clear(server):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
    conn.request("GET", "/live?feeds=wall")
    stream = conn.getresponse()

    def event():
        name = stream.fp.readline().decode().strip().removeprefix("event: ")
        data = json.loads(stream.fp.readline().decode().removeprefix("data: "))
        stream.fp.readline()
        return name, data

    name, first = event()
    assert name == "wall" and first["type"] == "state" and first["cards"] == [] and first["options"]["entrance"] == "pop"
    status, result = call(server, "/wall/test", {"unit": "별풍선", "amount": 1004, "name": "시험 시청자"})
    assert status == 200 and result["added"] == 1
    name, added = event()
    assert added["type"] == "add" and added["rev"] == first["rev"] + 1 and added["card"]["name"] == "시험 시청자" and added["card"]["test"]
    assert added["card"]["column"] == "별풍선/1000/1000" and added["columns"][0]["count"] == 1 and added["card"]["aura"]["effect"] == "stardust"
    assert call(server, "/wall/replay")[1] == {"replay": added["card"]["id"]}
    assert event()[1] == {"type": "replay", "rev": added["rev"] + 1, "id": added["card"]["id"]}
    status, cleared = call(server, "/wall/clear")
    assert cleared == {"cleared": 1, "undo": 8.0}
    state = event()[1]
    assert state["type"] == "state" and state["cards"] == [] and state["columns"] == []
    assert call(server, "/wall/undo")[1]["restored"] == 1 and len(event()[1]["cards"]) == 1
    stream.close()
    conn.close()


def test_config_layout_and_errors_over_http(server):
    server.hub.publish(OverlayEvent("soop", "donation", "a", (), amount=34.0, unit="별풍선"))
    status, saved = call(server, "/wall/config", {"entrance": "tape", "idle": "sway", "buckets": {"별풍선": "digits"}, "names": False})
    assert status == 200 and saved["config"]["entrance"] == "tape" and saved["columns"][0]["key"] == "별풍선/d/10"
    status, error = call(server, "/wall/config", {"entrance": "explode"})
    assert status == 400 and "등장 연출" in error["error"]
    assert request(server, "POST", "/wall/config", raw=b"not json")[0] == 200  # 빈 요청(바꿀 항목 없음)
    status, layout = call(server, "/wall/layout", {"key": "별풍선/d/10", "x": 600, "y": 300, "w": 260, "h": 500})
    assert status == 200 and layout["layout"]["별풍선/d/10"] == {"x": 600, "y": 300, "w": 260, "h": 500}
    column = json.loads(request(server, "GET", "/wall/view")[2])["columns"][0]
    assert column["pinned"] and (column["x"], column["y"]) == (600, 300)
    assert call(server, "/wall/layout", {"key": "없는 칸", "x": 1, "y": 1, "w": 200, "h": 300})[0] == 404
    assert call(server, "/wall/layout", {"key": "별풍선/d/10", "x": "왼쪽"})[0] == 400
    assert call(server, "/wall/layout", {"reset": True})[1]["layout"] == {}
    assert call(server, "/wall/detach", {"card": 999, "column": "solo"})[0] == 404
    assert call(server, "/wall/test", {"unit": "별풍선", "amount": -5})[0] == 400
    assert call(server, "/wall/test", {"mix": True})[1]["added"] == 12
    goal = json.loads(request(server, "GET", "/wall/view?part=goal")[2])
    assert set(goal) == {"rev", "goal"} and goal["goal"]["basis"] == "won"
    rank = json.loads(request(server, "GET", "/wall/view?part=rank")[2])["rank"]
    assert rank["entries"] and all(entry["name"] == "" for entry in rank["entries"])  # 닉네임 표시 끔
    status, kind, text = request(server, "GET", "/wall/export")
    assert status == 200 and kind.startswith("text/plain") and "[별풍선]" in text.decode() and "a(SOOP)" in text.decode()


def test_upload_routes_and_image_serving(server):
    status, result = call(server, "/wall/signature", {"unit": "원", "amount": 10000, "title": "만원의 행복", "image": b64(png())})
    assert status == 200 and result["signature"]["image"].endswith(".png")
    name = result["signature"]["image"]
    status, kind, body = request(server, "GET", f"/wall/image?name={name}")
    assert status == 200 and kind == "image/png" and body == png()
    for trick in ("..%2Fwall.json", "%2E%2E%2F%2E%2E%2Fdebutkit-settings.json", "wall.json", f"{name}%00.png"):
        assert request(server, "GET", f"/wall/image?name={trick}")[0] == 404
    assert call(server, "/wall/signature", {"unit": "원", "amount": 20000, "image": b64(b"MZ\x90\x00" + b"\x00" * 64)})[0] == 400
    big = b64(png(extra=wall.MAX_IMAGE + 1))  # 8MB를 조금 넘는 그림(요청 본문 한도 안)
    status, error = call(server, "/wall/signature", {"unit": "원", "amount": 20000, "image": big})
    assert status == 400 and "8MB" in error["error"]
    server.hub.publish(OverlayEvent("chzzk", "donation", "만원 후원자", (), amount=10000.0, unit="원"))
    server.hub.publish(OverlayEvent("chzzk", "donation", "오천 후원자", (), amount=5000.0, unit="원"))
    view = json.loads(request(server, "GET", "/wall/view")[2])
    signature = next(column for column in view["columns"] if column["kind"] == "sig")
    assert signature["title"] == "만원의 행복" and signature["image"] == f"/wall/image?name={name}"
    status, column = call(server, "/wall/column", {"key": "원/1000/5000", "image": b64(GIF)})
    assert status == 200 and column["image"].endswith(".gif")
    assert call(server, "/wall/column", {"key": "없는/0/1", "image": b64(GIF)})[0] == 404
    assert call(server, "/wall/column", {"key": "원/1000/5000", "image": ""})[1]["image"] == ""
    assert sorted(path.suffix for path in wall.image_folder().iterdir()) == [".png"]


def test_wall_survives_a_new_server():
    first = OverlayServer([], port=0).start()
    try:
        first.hub.publish(OverlayEvent("soop", "donation", "숲속토끼", (), amount=100.0, unit="별풍선"))
        first.hub.publish(OverlayEvent("twitch", "donation", "Haru", (), amount=1000.0, unit="bits"))
        request(first, "POST", "/wall/config", {"idle": "beat"})
        request(first, "POST", "/wall/layout", {"key": "bits/1000/1000", "x": 1500, "y": 100, "w": 220, "h": 400})
    finally:
        first.stop()  # 멈출 때 모아 둔 카드를 저장
    second = OverlayServer([], port=0).start()
    try:
        state = json.loads(request(second, "GET", "/wall/state")[2])
        assert [item["name"] for item in state["cards"]] == ["Haru", "숲속토끼"] and state["config"]["idle"] == "beat"
        assert next(column for column in state["columns"] if column["key"] == "bits/1000/1000")["x"] == 1500
    finally:
        second.stop()
