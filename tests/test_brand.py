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


def _load(name):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, ROOT / "packaging" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_debi_scene_prompts_keep_hands_simple():
    """2D 장면 그림(보류: 손이 뭉개져 다시 만들기 전까지 배포하지 않음): 지시문에 손 두 개, 발 두 개 규칙. 기록이 있으면 파일, 라이선스와 맞는지."""
    builder = _load("build_debi_scenes")
    assert "exactly two arms, two hands and two feet" in builder.DESIGN
    for key, (group, title, prompt, seed) in builder.SCENES.items():
        assert group in ("방송 중", "방송 준비", "일상") and title and prompt and isinstance(seed, int), key
    record_file = BRAND / "mascot" / "scenes.json"
    for key, item in (json.loads(record_file.read_text(encoding="utf-8")) if record_file.is_file() else {}).items():
        assert (ROOT / item["file"]).is_file() and item["license"] == "Apache-2.0" and item["prompt"].endswith(builder.DESIGN), key


def test_promo_pictures_use_3d_debi_and_are_on_the_site():
    """서비스 소개 그림(1600x900): 기본 3D 데비와 실제 화면으로 만든 장면마다 파일이 있고 소개 페이지와 사이트 복사 목록에 있음."""
    from PIL import Image

    promo = _load("build_promo")
    site = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    copies = _load("build_site").ASSETS
    for key in promo.SLIDES:
        picture = ROOT / "docs" / "images" / f"promo-{key}.jpg"
        with Image.open(picture) as image:
            assert image.size == (1600, 900), key
        assert copies[f"assets/promo/{key}.jpg"] == f"docs/images/promo-{key}.jpg", key
    for key in ("live", "prep", "character", "fun"):
        assert f"assets/promo/{key}.jpg" in site, key
    assert "assets/shots/promo-hero.jpg" in site and "assets/promo/hero.jpg" in site  # 화면 모음 첫 장, 공유 그림
    assert "assets/debi/" not in site  # 2D 장면 그림은 보류


def test_builtin_3d_debi_is_complete_and_recorded():
    import hashlib

    debi = character.sample_3d()
    model = character.file_path(debi, "debi.vrm")
    assert debi.builtin and debi.kind == "vrm" and model is not None and character.file_path(debi, "thumbnail.png") is not None
    assert model.stat().st_size < 10 * 1024 * 1024  # 함께 배포하는 크기(텍스처 1024px)
    gltf, binary = character.read_glb(model)
    meta = gltf["extensions"]["VRM"]["meta"]
    assert meta["title"] == "데비" and meta["licenseName"] == "CC0" and meta["allowedUserName"] == "Everyone" and meta["commercialUssageName"] == "Allow"
    check = character.vrm_check(gltf, binary)  # 캐릭터 화면과 그림 시트가 쓰는 표정이 모두 있음
    assert check["emotions"] == list(character.EMOTIONS) and len(check["vowels"]) == 5 and check["blink"] == "both" and check["warnings"] == []
    assert check["textures"]["largest"] <= character.LIGHT_TEXTURE
    record = json.loads((model.parent / "manifest.json").read_text(encoding="utf-8"))
    assert record["file"]["sha256"] == hashlib.sha256(model.read_bytes()).hexdigest() and "CC0" in record["base"]["license"]
    assert record["tool"] == "packaging/build_debi3d.py" and record["changes"]


def test_props_use_mai_not_the_old_cat_ear_emblem():
    """추첨 카드와 소품(draw.js), 뽑기판 덮개(pick.js), 레이스 달리기(race.js)는 마스코트 마이(망 두 줄, 꼭대기 불, 띠)."""
    from debutkit import pick

    cat_ears = "M38 32 L42 9 L56 21 Z"
    for name in ("draw.js", "pick.js"):
        script = (STATIC / name).read_text(encoding="utf-8")
        assert cat_ears not in script and "마이(리본 마이크) 문양" in script, name
        assert 'cx: 60, cy: 9, r: 4' in script and 'x: 40, y: 66, width: 40' in script, name  # 꼭대기 불, 아래 띠
    race = (STATIC / "race.js").read_text(encoding="utf-8")
    assert "// 귀" not in race and "망 머리" in race and '"#ff6f6f"' in race
    assert "고양이" not in (STATIC / "race-control.html").read_text(encoding="utf-8")
    assert pick.COVERS["emblem"] == "마이 문양"


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
    # 빈 화면은 뽀글이들(레이스 참가자, 후원 벽 카드, 커뮤니티 처음), 방송 직전 점검의 마이크는 마이
    assert 'mascot("bubbles"' in (STATIC / "race-control.html").read_text(encoding="utf-8")
    assert 'mascot("bubbles"' in (STATIC / "wall-control.html").read_text(encoding="utf-8")
    assert '/mascot/bubbles.png' in (STATIC / "community-control.html").read_text(encoding="utf-8")
    assert 'id="c-mic"><span class="dot"></span><b><img class="cast-mini" src="/mascot/mai.png"' in page


def test_missing_page_is_cue_for_browsers(port):
    def get(accept):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/no-such-screen", headers={"Accept": accept})
        response = conn.getresponse()
        body = response.read()
        conn.close()
        return response.status, response.getheader("Content-Type"), body

    status, kind, body = get("text/html,application/xhtml+xml")
    page = body.decode("utf-8")
    assert status == 404 and kind.startswith("text/html") and "/mascot/cue.png" in page and "대본에 없는 장면" in page and 'href="/"' in page
    assert get("*/*") == (404, "text/plain; charset=utf-8", b"not found")  # 브라우저가 아닌 요청은 그대로
