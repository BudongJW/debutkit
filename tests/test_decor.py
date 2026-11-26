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
                     "signature": (512, 512)}
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
