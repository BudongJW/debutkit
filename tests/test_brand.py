"""브랜드와 마스코트: 로고 파일(packaging/build_brand.py 결과), 기본 캐릭터 데비, 화면용 마스코트 그림과 생성 기록."""

import http.client
import json
from pathlib import Path

import pytest

from debutkit import character
from debutkit.overlay import server as overlay_server
from debutkit.overlay.server import OverlayServer

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "assets" / "brand"
STATIC = ROOT / "src" / "debutkit" / "overlay" / "static"


def test_brand_files_are_built_and_in_sync():
    for name in ("symbol/symbol_light-bg", "symbol/symbol_dark-bg", "symbol/symbol-small_light-bg", "symbol/mai_light-bg", "wordmark/wordmark_light-bg",
                 "lockup/horizontal_light-bg", "lockup/vertical_dark-bg", "app-icon/app-icon_dark_rounded", "app-icon/app-icon_light"):
        assert (BRAND / f"{name}.svg").read_text(encoding="utf-8").startswith("<svg"), name
        assert (BRAND / f"{name}.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", name
    # 탭 아이콘은 브랜드 파비콘과 같은 파일, 작은 크기는 벡터(마이)
    favicon = (BRAND / "favicon" / "favicon.svg").read_text(encoding="utf-8")
    assert favicon == (STATIC / "favicon.svg").read_text(encoding="utf-8") and "<image" not in favicon
    assert (BRAND / "app-icon" / "debutkit.ico").read_bytes()[:4] == b"\x00\x00\x01\x00"
    readme = (BRAND / "README.txt").read_text(encoding="utf-8")  # 저장소 파일은 UTF-8
    assert "데비" in readme and "build_brand.py" in readme


def test_mascot_records_are_complete():
    manifest = json.loads((BRAND / "mascot" / "draft" / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) >= {"debi", "mai", "cue", "bubbles", "capsule", "cuckoo", "dessaengi"}
    for key, record in manifest.items():  # 같은 지시문과 시드로 다시 만들 수 있게
        assert record["license"].endswith("Apache-2.0") and record["prompt"] and isinstance(record["seed"], int), key
        assert (BRAND / "mascot" / "draft" / f"{key}.png").is_file(), key


def test_default_character_is_debi():
    sample = character.sample()
    assert sample.name.endswith("데비") and set(sample.files) == set(character.PNG_STATES)
    sizes = set()
    for state, name in sample.files.items():
        path = character.file_path(sample, name)
        width, height, transparent = character.png_info(path)
        sizes.add((width, height))
        assert transparent, state
    assert len(sizes) == 1  # 상태별 같은 크기(바꿔 보여도 흔들리지 않게)
    record = json.loads((STATIC / "character" / "sample" / "manifest.json").read_text(encoding="utf-8"))
    assert set(record["edits"]) == {"idle", "blink", "talk_blink"} and all(item["license"] == "Apache-2.0" for item in record["edits"].values())


@pytest.fixture
def port():
    srv = OverlayServer([], port=0).start()
    yield srv.port
    srv.stop()


def test_mascot_pictures_are_served(port):
    for name in overlay_server.MASCOTS:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", f"/mascot/{name}.png")
        response = conn.getresponse()
        body = response.read()
        conn.close()
        assert response.status == 200 and response.getheader("Content-Type") == "image/png" and body[:4] == b"\x89PNG", name
    assert "function mascot(" in (STATIC / "ui.js").read_text(encoding="utf-8")
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    assert '/mascot/debi.png' in page and '/mascot/cue.png' in page
    assert 'mascot("capsule"' in (STATIC / "draw-control.html").read_text(encoding="utf-8")
