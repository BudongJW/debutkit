"""방송 이미지 만들기(overlay/decor.py, /decor): 그림 종류와 규격, 그림이 있는 캐릭터 목록, 화면과 이동 막대."""

import http.client
import json
from pathlib import Path

import pytest

from debutkit import character
from debutkit.overlay import decor
from debutkit.overlay.server import OverlayServer

STATIC = Path(__file__).resolve().parent.parent / "src" / "debutkit" / "overlay" / "static"


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
    return response.status, response.getheader("Content-Type"), body


def test_formats_and_character_pictures(server):
    status, _, body = get(server, "/decor/characters")
    data = json.loads(body)
    assert status == 200
    sizes = {key: (item["width"], item["height"]) for key, item in data["formats"].items()}
    assert sizes == {"profile": (1024, 1024), "thumbnail": (1280, 720), "youtube": (2560, 1440), "twitch": (1200, 480), "soop": (720, 150),
                     "signature": (512, 512), "cheki": (1080, 1350), "soop-link": (720, 450), "shorts": (1080, 1920), "fourcut": (600, 1800),
                     "bangsel": (1920, 1080), "custom": (1280, 720)}
    pictures = {item["id"]: item for item in data["characters"]}
    # 2D 데비는 입 다문 그림, 3D 데비는 미리보기 그림. 방송에 쓰는 캐릭터 표시
    assert pictures[character.SAMPLE_ID]["picture"] == "/character/files/debutkit/idle.png" and pictures[character.SAMPLE_ID]["active"]
    assert pictures[character.SAMPLE_3D_ID]["picture"] == "/character/files/debutkit-3d/thumbnail.png"
    for item in data["characters"]:
        status, kind, image = get(server, item["picture"])
        assert status == 200 and kind == "image/png" and image[:4] == b"\x89PNG", item["id"]


def test_characters_without_pictures_are_left_out(tmp_path):
    folder = character.library_dir() / "no-picture"
    folder.mkdir(parents=True)
    plain = character.Character("no-picture", "그림 없음", "vrm", {"model": "a.vrm"})
    (folder / "character.json").write_text(json.dumps(plain.to_dict(), ensure_ascii=False), encoding="utf-8")
    assert "no-picture" not in {item["id"] for item in decor.characters()["characters"]}


def _png_url(color, size=(64, 64)):
    import base64
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


def post(srv, path, body):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=30)
    conn.request("POST", path, body=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    data = json.loads(response.read())
    conn.close()
    return response.status, data


def test_animated_profile_is_made_from_frames(server):
    import base64
    import io

    image_module = pytest.importorskip("PIL.Image")
    frames = [_png_url(color) for color in ((169, 139, 247), (69, 214, 184), (255, 201, 60))]
    status, data = post(server, "/decor/animate", {"frames": frames, "delay": 80})
    gif = base64.b64decode(data["gif"].split(",", 1)[1])
    assert status == 200 and gif[:6] == b"GIF89a" and data["bytes"] == len(gif)
    with image_module.open(io.BytesIO(gif)) as picture:
        assert picture.n_frames == 3 and picture.info.get("loop") == 0 and picture.info.get("duration") == 80
    for body, message in (({"frames": frames[:1]}, "장면은 2에서"), ({"frames": frames, "delay": 5}, "장면 사이 시간"),
                          ({"frames": [frames[0], "data:image/jpeg;base64,AAAA"]}, "PNG 그림만"),
                          ({"frames": [frames[0], _png_url((0, 0, 0), (32, 32))]}, "크기가 모두 같아야"),
                          ({"frames": [frames[0], "data:image/png;base64,***"]}, "올바르지 않음")):
        status, data = post(server, "/decor/animate", body)
        assert status == 400 and message in data["error"], message


def test_page_draws_locally_and_is_in_the_menu(server):
    status, kind, body = get(server, "/decor")
    page = body.decode("utf-8")
    assert status == 200 and kind.startswith("text/html") and 'id="canvas"' in page and "/decor.js" in page
    script = (STATIC / "decor.js").read_text(encoding="utf-8")
    assert "innerHTML" not in script and "https://" not in script  # 올린 그림은 브라우저 안에서만(createObjectURL)
    assert "URL.createObjectURL(file)" in script and "200 * 1024" in script and '"image/jpeg"' in script  # SOOP 배너는 JPEG 200KB 이하
    # 움짤 프사(이 PC 서버에서 GIF), 시그니처 풍선 그림은 후원 벽에 등록(같은 단위와 금액이면 바꿈)
    assert '"/decor/animate"' in script and '"/wall/signature"' in script and "body.id = existing.id" in script
    menu = (STATIC / "ui.js").read_text(encoding="utf-8")
    assert '["/decor", "방송 이미지"' in menu and '["/character/sheet", "캐릭터 그림"' in menu


def _card_url(size=64, shift=0):
    """가운데만 칠하고 바깥은 투명한 PNG(시그니처 카드처럼). 같은 장면은 Pillow가 하나로 합치므로 shift로 다르게."""
    import base64
    import io

    from PIL import Image, ImageDraw

    picture = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(picture).rectangle((size // 4 + shift, size // 4, size * 3 // 4 + shift, size * 3 // 4), fill=(169, 139, 247, 255))
    out = io.BytesIO()
    picture.save(out, "PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


def test_signature_gif_keeps_the_outside_transparent(server):
    import base64
    import io

    image_module = pytest.importorskip("PIL.Image")
    status, data = post(server, "/decor/animate", {"frames": [_card_url(), _card_url(shift=6)], "delay": 80, "transparent": True})
    assert status == 200
    with image_module.open(io.BytesIO(base64.b64decode(data["gif"].split(",", 1)[1]))) as picture:
        assert picture.info.get("transparency") == 255
        assert picture.getpixel((1, 1)) == 255 and picture.getpixel((32, 32)) != 255  # 바깥은 투명, 카드는 색
        picture.seek(1)  # 둘째 장부터 Pillow는 RGBA로 풀어 줌
        assert picture.convert("RGBA").getpixel((1, 1))[3] == 0 and picture.convert("RGBA").getpixel((40, 32))[3] == 255
    status, data = post(server, "/decor/animate", {"frames": [_card_url(), _card_url(shift=6)], "delay": 80})
    with image_module.open(io.BytesIO(base64.b64decode(data["gif"].split(",", 1)[1]))) as picture:
        assert "transparency" not in picture.info  # 프사, 배너는 투명 없음


def _js_table(script, name):
    import re

    body = re.search(rf"const {name} = \{{(.*?)\}};", script, re.S).group(1)
    return re.findall(r"(\w+): ", body)


def test_decorations_presets_and_pens():
    """미타데코 대응: 테두리 12종과 없음, 파티클 9종, 자막 10종, 움직임 7종, 완성 프리셋 9종, 손그림 펜 5종, 체키, 움짤과 영상 입력."""
    import re

    from debutkit.overlay import theme

    fx = (STATIC / "decor-fx.js").read_text(encoding="utf-8")
    borders, particles, captions = _js_table(fx, "BORDERS"), _js_table(fx, "PARTICLES"), _js_table(fx, "CAPTIONS")
    motions, pens = _js_table(fx, "MOTIONS"), _js_table(fx, "PENS")
    assert len(borders) == 13 and "none" in borders and {"wreath", "snowcrown", "neon", "hearts"} <= set(borders)
    assert len(particles) == 10 and len(captions) == 10 and len(motions) == 8 and pens == ["pen", "highlighter", "neon", "cream", "dotted"]
    presets = re.findall(r'(\w+): \{ name: "([^"]+)", border: "(\w+)", particles: "(\w+)", caption: "(\w+)", motion: "(\w+)", pattern: "(\w+)", '
                         r'title: "(\w+)", text: "(\w+)" \}', fx)
    assert len(presets) == 9
    for _, name, border, particle, caption, motion, pattern, title, text in presets:
        assert border in borders and particle in particles and caption in captions and motion in motions, name
        assert pattern in ("stars", "dots", "stripes", "none") and title in theme.FONT_CHOICES and text in theme.FONT_CHOICES, name
    for kind in borders:  # 테두리마다 그리는 코드
        assert kind == "none" or f'"{kind}"' in fx.split("function border(")[1].split("function bow(")[0], kind
    page = (STATIC / "decor.html").read_text(encoding="utf-8")
    for element in ('id="preset"', 'id="border"', 'id="particles"', 'id="caption"', 'id="motion"', 'id="cheki-ratio"', 'id="cheki-date"',
                    'id="pen-on"', 'id="pen"', 'id="pen-color"', 'id="pen-undo"', 'id="pen-clear"', 'id="place"', 'id="wall-gif"',
                    "image/gif,video/mp4,video/webm", '<script src="/decor-fx.js"></script>'):
        assert element in page, element
    assert page.index("/decor-fx.js") < page.index('src="/decor.js"')
    script = (STATIC / "decor.js").read_text(encoding="utf-8")
    assert "new ImageDecoder(" in script and 'document.createElement("video")' in script and "transparent" in script
    assert "innerHTML" not in script and "innerHTML" not in fx and "https://" not in fx


def test_more_formats_frames_and_shapes():
    """미타크래프트 대응: SOOP 연결 배너(720x150 3장, 6장으로 나눠 JPEG 200KB 이하), 쇼츠 커버, 네컷(1x4, 2x2), 방셀 액자 10종, 원하는 크기, 시그니처 판 모양 5종."""
    fx = (STATIC / "decor-fx.js").read_text(encoding="utf-8")
    shapes, frames = _js_table(fx, "SHAPES"), _js_table(fx, "FRAMES")
    assert shapes == ["card", "circle", "heart", "star", "badge"] and len(frames) == 10
    papers = fx.split("const papers = {")[1].split("};")[0]
    for kind in frames:  # 액자마다 바탕 색과 꾸밈 코드
        assert f"{kind}:" in papers and f'kind === "{kind}"' in fx, kind
    script = (STATIC / "decor.js").read_text(encoding="utf-8")
    assert "async function saveLinked()" in script and "piece.width = 720;" in script and "piece.height = 150;" in script
    assert 'piece.toBlob(resolve, "image/jpeg", quality)' in script and "data.size <= 200 * 1024" in script
    assert 'whole("custom-w", 64, 4096, 1280)' in script and "slice(0, 4)" in script
    for key in ("soop-link", "shorts", "fourcut", "bangsel", "custom"):
        assert key in decor.FORMATS, key
    page = (STATIC / "decor.html").read_text(encoding="utf-8")
    for element in ('id="link-count"', 'id="fourcut-layout"', 'id="fourcut-paper"', 'id="photos" multiple', 'id="bangsel-frame"',
                    'id="bangsel-orient"', 'id="custom-w"', 'id="custom-h"', 'id="sig-shape"'):
        assert element in page, element
