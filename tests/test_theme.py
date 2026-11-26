"""방송 색과 방송 스타일(overlay/theme.py): 스타일 묶음, 글꼴 선택, 내 글꼴 올리기, /theme.css."""

import base64
import http.client
import json

import pytest

from debutkit.overlay import theme
from debutkit.overlay.server import OverlayServer

WOFF2 = b"wOF2" + bytes(60)
KEYS = ("surface", "on-surface", "muted", "line", "line-width", "line-style", "radius", "shadow", "glow", "backdrop", "tag-bg", "tag-text",
        "display", "text", "enter-time", "enter-ease", "style", "tone")


def request(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, response.getheader("Content-Type"), data


@pytest.fixture
def port():
    server = OverlayServer([], port=0).start()
    yield server.port
    server.stop()


def test_every_style_has_all_tokens_and_an_entrance():
    assert list(theme.STYLES)[0] == "prop" and len(theme.STYLES) >= 8
    base = theme.load()
    assert base["style"] == "prop" and base["display_font"] == "" and base["fonts"] == []
    for key in theme.STYLES:
        values = theme.tokens({**base, "style": key})
        assert all(values.get(name) for name in KEYS), key
        assert values["style"] == key and values["enter-time"].endswith("s")
        sheet = theme.css({**base, "style": key})
        assert f"--dk-style: {key};" in sheet and "@keyframes dk-enter" in sheet and '"Black Han Sans"' in sheet
        assert "Black Han Sans\"; src" not in theme.css({**base, "style": key}, fonts=False)
    # 바탕 밝기(tone): 어두운 바탕은 밝은 글자, 밝은 바탕은 어두운 글자. 화면별 CSS가 tone으로 이름과 금액 색을 고름
    colors = theme.palette("#ff4f8b", "#ffd84d")
    for key in theme.STYLES:
        values = theme._style_tokens(key, colors)
        bright = theme.luminance(values["on-surface"])
        assert (bright > 0.7) if values["tone"] == "dark" else (bright < 0.1), key
        assert values["enter"] in theme.ENTERS, key
    assert {theme._style_tokens(key, colors)["tone"] for key in theme.GENRE_STYLES} == {"dark", "light"}
    assert set(theme.GENRE_STYLES) < set(theme.STYLES) and len(theme.STYLES) == 16


def test_font_choices_and_local_names():
    fonts = [{"id": "a" * 24, "ext": "woff2", "name": "내 글꼴"}]
    assert theme.check_font("", fonts) == "" and theme.check_font("blackhan", fonts) == "blackhan"
    assert theme.check_font(" local:나눔스퀘어 라운드 ", fonts) == "local:나눔스퀘어 라운드"
    assert theme.check_font(f"user:{'a' * 24}", fonts) == f"user:{'a' * 24}"
    for bad in ("comic", "local:", "local:<b>", 'local:x"; } body {', f"user:{'b' * 24}"):
        with pytest.raises(theme.ThemeError):
            theme.check_font(bad, fonts)
    assert theme.font_stack("local:나눔고딕", fonts).startswith('"나눔고딕", ')
    assert theme.font_stack(f"user:{'a' * 24}", fonts).startswith(f'"dk-user-{"a" * 24}"')
    assert theme.font_stack("", fonts) is None
    values = theme.tokens({**theme.load(), "display_font": "batang", "text_font": "local:나눔고딕"})
    assert values["display"].startswith('"Batang"') and values["text"].startswith('"나눔고딕"')


def test_font_files_are_checked(monkeypatch):
    assert theme.decode_font(base64.b64encode(WOFF2).decode()) == (WOFF2, "woff2")
    assert theme.decode_font("data:font/ttf;base64," + base64.b64encode(b"\x00\x01\x00\x00" + bytes(8)).decode())[1] == "ttf"
    assert theme.decode_font(base64.b64encode(b"OTTO" + bytes(8)).decode())[1] == "otf"
    for bad, message in (("", "비어 있음"), ("!!!", "읽지 못함"), (base64.b64encode(b"\x89PNG\r\n\x1a\n").decode(), "글꼴 파일이 아님")):
        with pytest.raises(theme.ThemeError, match=message):
            theme.decode_font(bad)
    monkeypatch.setattr(theme, "MAX_FONT", 10)
    with pytest.raises(theme.ThemeError, match="MB 이하"):
        theme.decode_font(base64.b64encode(WOFF2).decode())


def test_style_and_font_routes(port):
    status, _, body = request(port, "GET", "/theme")
    info = json.loads(body)
    assert status == 200 and set(info["styles"]) == set(theme.STYLES) and "blackhan" in info["font_choices"]
    assert info["styles"]["neon"]["name"] == "네온" and info["tokens"]["style"] == "prop"

    status, _, body = request(port, "POST", "/theme", {"style": "neon", "display_font": "gungsuh"})
    assert status == 200 and json.loads(body)["style"] == "neon"
    sheet = request(port, "GET", "/theme.css")[2].decode()
    assert "--dk-style: neon;" in sheet and '--dk-display: "Gungsuh"' in sheet
    assert "--dk-style: pixel;" in request(port, "GET", "/theme.css?style=pixel")[2].decode()  # 이 화면만 다른 스타일
    assert "@font-face" not in request(port, "GET", "/theme.css?fonts=0")[2].decode()
    status, _, body = request(port, "POST", "/theme", {"style": "rainbow"})
    assert status == 400 and "방송 스타일은" in json.loads(body)["error"]
    assert request(port, "POST", "/theme", {"text_font": "local:<script>"})[0] == 400

    data = base64.b64encode(WOFF2).decode()
    status, _, body = request(port, "POST", "/theme/font", {"name": "내손글씨.woff2", "data": data, "use": ["display", "text"]})
    answer = json.loads(body)
    font_id = answer["uploaded"]
    assert status == 200 and answer["fonts"] == [{"id": font_id, "ext": "woff2", "name": "내손글씨"}]
    assert answer["display_font"] == answer["text_font"] == f"user:{font_id}"
    sheet = request(port, "GET", "/theme.css?fonts=0")[2].decode()  # 내 글꼴 선언은 조작 화면에도
    assert f'font-family: "dk-user-{font_id}"; src: url("/theme/font?id={font_id}") format("woff2")' in sheet
    assert f'--dk-display: "dk-user-{font_id}"' in sheet
    status, kind, body = request(port, "GET", f"/theme/font?id={font_id}")
    assert status == 200 and kind == "font/woff2" and body == WOFF2
    status, _, body = request(port, "POST", "/theme/font", {"name": "그림", "data": base64.b64encode(b"GIF89a").decode()})
    assert status == 400 and "글꼴 파일이 아님" in json.loads(body)["error"]

    status, _, body = request(port, "POST", "/theme/font/remove", {"id": font_id})
    answer = json.loads(body)
    assert status == 200 and answer["fonts"] == [] and answer["display_font"] == answer["text_font"] == ""
    assert request(port, "GET", f"/theme/font?id={font_id}")[0] == 404
    assert request(port, "POST", "/theme/font/remove", {"id": font_id})[0] == 404
    assert not list(theme.font_folder().glob("*"))


def first_theme(port):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/live?feeds=theme")
    stream = conn.getresponse()
    assert stream.fp.readline().decode().strip() == "event: theme"
    value = json.loads(stream.fp.readline().decode().removeprefix("data: "))
    stream.close()
    conn.close()
    return value


def test_style_change_reaches_live_feed(port):
    # 서버를 켠 직후 값에도 색이 있어야 theme.js가 기준으로 삼아 첫 스타일 변경을 알아챔
    value = first_theme(port)
    assert value["seq"] == 0 and value["style"] == "prop" and value["palette"]["primary"] == "#ff4f8b"
    request(port, "POST", "/theme", {"style": "diary"})
    value = first_theme(port)
    assert value["seq"] == 1 and value["style"] == "diary" and value["palette"]["on-primary"] in (theme.INK, "#ffffff")
