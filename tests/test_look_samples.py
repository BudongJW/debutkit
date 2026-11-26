"""모양 고르기의 그림 견본과 처음 상태로: 화면별 예시 그리기(?still, ?sample), 기본값 주소, 조작 화면의 그림 단추."""

import http.client
import json
import re

import pytest

from debutkit import draw, pick, race, settings, wall
from debutkit.overlay.server import OverlayServer


@pytest.fixture
def server():
    srv = OverlayServer([], port=0).start()
    yield srv
    srv.stop()


def get(srv, path):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    conn.request("GET", path)
    response = conn.getresponse()
    body = response.read()
    conn.close()
    return response.status, body


def get_json(srv, path):
    status, body = get(srv, path)
    assert status == 200, path
    return json.loads(body)


# --------------------------------------------------------------------------- 처음 상태로(기본값)


def test_draw_defaults_are_first_run_values_without_choices():
    values = draw.defaults()
    assert "enabled" not in values and not set(draw.CHOICE_KEYS) & set(values)
    assert values["style"] == "card" and values["seconds"] == 8 and values["title"] == draw.DEFAULT_TITLE
    assert [prize["name"] for prize in values["prizes"]] == [item.split(":", 1)[1] for item in draw.DEFAULT_PRIZES]
    assert sorted(rule["min_won"] for rule in values["rules"]) == [1000, 10000]


def test_defaults_reach_the_control_pages(server):
    settings.save({**settings.load(), "draw_style": "tarot", "draw_seconds": 20})
    config = get_json(server, "/draw/config")
    assert config["style"] == "tarot" and config["defaults"]["style"] == "card" and config["defaults"]["seconds"] == 8
    assert get_json(server, "/race/config")["defaults"] == race.DEFAULTS
    secret = get_json(server, "/pick/secret")
    assert secret["defaults"]["theme"] == "card" and secret["defaults"]["cover"] == "number" and secret["defaults"]["palette"]
    assert set(get_json(server, "/wall/state")["defaults"]) == set(wall.LOOK_KEYS)


# --------------------------------------------------------------------------- 그림 견본


def test_wall_sample_uses_example_cards_and_changes_nothing():
    state = wall.Wall()
    state.add("진짜 후원", 34, "별풍선", "soop")
    before = settings.load_data("wall.json")
    view = state.sample({"entrance": ["jelly"], "idle": ["bob"]})
    assert view["options"]["entrance"] == "jelly" and view["options"]["idle"] == "bob"
    assert view["options"]["sound"] is False and view["options"]["names"] is True
    assert [card["name"] for card in view["cards"]] == [name for name, *_ in wall.SAMPLE_CARDS]
    assert any(card["aura"] for card in view["cards"])  # 큰 후원은 오라 단계가 붙은 모습
    # 실제 벽의 카드, 설정, 저장 파일은 그대로
    assert [card["name"] for card in state.cards] == ["진짜 후원"] and state.config["entrance"] == "pop"
    assert settings.load_data("wall.json") == before
    # 모르는 값은 무시하고 지금 설정을 쓴다
    assert state.sample({"entrance": ["<script>"], "idle": ["spin"]})["options"]["entrance"] == "pop"


def test_sample_routes_answer(server):
    view = get_json(server, "/wall/sample?entrance=stamp")
    assert view["options"]["entrance"] == "stamp" and len(view["cards"]) == len(wall.SAMPLE_CARDS)
    assert get_json(server, "/wall/state")["summary"]["cards"] == 0  # 견본은 벽에 붙지 않음
    status, body = get(server, "/race/sample?game=survival&design=paper&n=12")
    assert status == 200 and json.loads(body)["race"]


@pytest.mark.parametrize("path, markers", [
    ("/overlay.js", ['params.has("still")', 'document.documentElement.classList.add("still")']),
    ("/overlay.css", ["html.still"]),
    ("/race.js", ['params.has("still")', "stillFrames"]),
    ("/pick.js", ['params.has("sample")', 'tier: "miss"']),
    ("/wall.js", ["/wall/sample?", '{ type: "replay", id: last }']),
    ("/draw.js", ['params.has("mute") ? false']),
    ("/ui.js", ["function thumb(", "function looks(", "dataset.view", "thumb, looks"]),
    ("/ui.css", [".dk-thumb", ".dk-looks", "details.dk-more"]),
])
def test_still_and_sample_modes_are_served(server, path, markers):
    status, body = get(server, path)
    text = body.decode()
    assert status == 200
    for marker in markers:
        assert marker in text, (path, marker)


@pytest.mark.parametrize("path, markers", [
    ("/alerts/control", ['id="presets"', 'id="layouts"', "debutkitUi.thumb(", "still: \"1\""]),
    ("/stage", ["debutkitUi.thumb(", "layoutThumb(", 'still: "1"']),
    ("/draw/control", ['id="style-tiles"', 'id="design-tiles"', 'id="prize-presets"', 'id="reset"', 'class="dk-more"']),
    ("/race/control", ['id="games"', 'id="course-tiles"', 'id="design-tiles"', 'id="presets"', 'id="reset"', 'class="dk-more"']),
    ("/wall/control", ['id="look-preview"', 'id="presets"', 'id="reset"', 'class="dk-more"']),
    ("/pick/control", ['id="theme-tiles"', 'id="cover-tiles"', 'id="reset"']),
])
def test_control_pages_show_pictures_for_looks(server, path, markers):
    status, body = get(server, path)
    page = body.decode()
    assert status == 200
    for marker in markers:
        assert marker in page, (path, marker)
    # 조작 스크립트가 debutkitUi를 바로 쓰므로 ui.js를 먼저 불러온다
    inline = re.search(r"<script>\s", page)
    assert inline and page.index('<script src="/ui.js">') < inline.start(), path


def test_choice_lists_cover_every_sample_value():
    # 그림 단추는 고르기 목록의 모든 값을 그린다(목록에 없는 값을 주소로 보내지 않음)
    assert set(draw.DESIGNS) == set(draw.STYLES)
    assert set(race.choices()["courses"]) == set(race.COURSES) and set(race.choices()["designs"]) == set(race.DESIGNS)
    assert set(pick.options()["themes"]) == set(pick.THEMES) and set(pick.options()["covers"]) == set(pick.COVERS)
