"""로고 아이콘 묶음(logo_icons.py): 묶음 내용과 라이선스, 검색, 채널 색 다시 칠하기, 굵기 맞춤, 외곽선과 스티커 마감, 출처 기록."""

from __future__ import annotations

import gzip
import json
import re
import xml.etree.ElementTree as ET
from importlib import resources

import pytest

from debutkit import logo, logo_icons

pytest.importorskip("fontTools")
pytest.importorskip("brotli")

SVG = "{http://www.w3.org/2000/svg}"
ICONS = resources.files("debutkit.overlay").joinpath("static", "vendor", "icons")


# --- 묶음 ---------------------------------------------------------------------------------


def test_bundles_are_small_licensed_and_tagged_in_korean():
    total = sum(len(ICONS.joinpath(name).read_bytes()) for name in logo_icons.SETS.values())
    assert total < 1_200_000  # 설치 파일 영향 약 1 MB 이하
    fluent, phosphor = logo_icons.bundle("fluent"), logo_icons.bundle("phosphor")
    assert 200 <= len(fluent["icons"]) <= 400 and len(phosphor["icons"]) >= 60
    for data, name in ((fluent, "fluent-emoji"), (phosphor, "phosphor")):
        assert data["license"] == "MIT" and data["source"].startswith("https://github.com/") and data["version"]
        notice = ICONS.joinpath(f"LICENSE-{name}.txt").read_text(encoding="utf-8")
        assert notice.startswith("MIT License") and data["copyright"] in notice and "WITHOUT WARRANTY" in notice
    hangul = re.compile("[가-힣]")
    ids = set()
    for icon in fluent["icons"] + phosphor["icons"]:
        assert icon["id"] not in ids and hangul.search(icon["ko"]) and any(hangul.search(tag) for tag in icon["tags"])
        assert icon["category"] in fluent["categories"]
        ids.add(icon["id"])
    for icon in fluent["icons"]:
        assert set(icon["svg"]) <= {"flat", "mono"} and "flat" in icon["svg"] and abs(sum(icon["areas"].values()) - 1) < 0.02
    for icon in phosphor["icons"]:
        assert list(icon["svg"]) == ["thin", "light", "regular", "bold", "fill", "duotone"]
        assert not icon["name"].endswith("-logo")  # 상표 로고 아이콘 없음


def test_every_icon_is_plain_safe_svg():
    for set_id in logo_icons.SETS:
        for icon in logo_icons.bundle(set_id)["icons"]:
            for style, svg in icon["svg"].items():
                lowered = svg.lower()
                for bad in ("<filter", "gradient", "<image", "<mask", "<script", "href=", "<style"):
                    assert bad not in lowered, (icon["id"], style, bad)
                clean = logo.sanitize_svg(svg)
                assert logo.view_box(ET.fromstring(clean))[2] in (32, 256), icon["id"]  # 원본 격자(일부 Fluent는 세로 33)


def test_search_and_find():
    cats = logo_icons.search("고양이")
    assert {"fluent/cat-face", "phosphor/cat"} <= {icon["id"] for icon in cats}
    assert {"fluent/studio-microphone", "fluent/microphone", "phosphor/microphone"} <= {icon["id"] for icon in logo_icons.search("마이크")}
    assert logo_icons.search("cat face")[0]["id"] == "fluent/cat-face"  # 영어 이름
    assert {icon["category"] for icon in logo_icons.search("음식과 디저트")} == {"food"}  # 분류 이름
    assert logo_icons.search("없는검색어") == []
    assert logo_icons.find("cat-face")["id"] == "fluent/cat-face" and logo_icons.find("phosphor/cat")["id"] == "phosphor/cat"
    assert logo_icons.find("headphones")["id"] == "phosphor/headphones"  # Fluent에 없으면 Phosphor
    with pytest.raises(logo_icons.IconError, match="찾지 못함"):
        logo_icons.find("remix/cat")
    catalog = logo_icons.catalog()
    assert len(catalog["icons"]) == len(logo_icons.bundle("fluent")["icons"]) + len(logo_icons.bundle("phosphor")["icons"])
    assert "svg" not in catalog["icons"][0] and catalog["sets"]["fluent"]["license"] == "MIT" and "sticker" in catalog["finishes"]


# --- 색 ------------------------------------------------------------------------------------


def test_oklch_round_trip_and_gamut():
    for colour in ("#FF4F8B", "#1E2327", "#FFFFFF", "#000000", "#22CC44", "#7B5CFF"):
        assert logo_icons.from_oklch(*logo_icons.oklch(colour)) == colour
    assert re.fullmatch(r"#[0-9A-F]{6}", logo_icons.from_oklch(0.9, 0.4, 140))  # 화면에 없는 색은 채도를 줄여 표시 가능한 색으로
    assert logo_icons.mix("#000000", "#FFFFFF", 0.5) == "#808080"


def test_channel_palette_keeps_lightness_steps():
    icon = logo_icons.find("cat-face")
    mapping = logo_icons.channel_palette(icon["areas"], "#FF4F8B", "#1E2327")
    assert mapping["#FFB02E"] == "#FF4F8B"  # 가장 넓은 유채색이 주 색
    assert mapping["#402A32"] == "#1E2327"  # 어두운 무채색(눈)은 보조 색
    darker = logo_icons.oklch(mapping["#BB1D80"])[0]
    assert darker < logo_icons.oklch("#FF4F8B")[0] and abs(logo_icons.oklch(mapping["#BB1D80"])[2] - logo_icons.oklch("#FF4F8B")[2]) < 3
    light_accent = logo_icons.channel_palette(icon["areas"], "#FF4F8B", "#FFFFFF")
    assert light_accent["#402A32"] == "#402A32"  # 밝은 보조 색이면 눈은 그대로
    ghost = logo_icons.channel_palette(logo_icons.find("white-heart")["areas"], "#3366FF", "#1E2327")
    assert any(logo_icons.oklch(colour)[1] > 0.1 for colour in ghost.values())  # 무채색만 있는 아이콘도 주 색 계열로


def test_icon_svg_styles_colours_and_weights():
    svg, credit = logo_icons.icon_svg("cat-face", primary="#FF4F8B", accent="#1E2327")
    assert "#FF4F8B" in svg and "#FFB02E" not in svg and credit["set"] == "Microsoft Fluent Emoji" and credit["icon"] == "Cat face"
    assert credit["license"] == "MIT" and credit["style"] == "flat"
    original, _ = logo_icons.icon_svg("cat-face", colors="original")
    assert "#FFB02E" in original
    mono, credit = logo_icons.icon_svg("cat-face", style="mono", primary="#7B5CFF")
    assert set(re.findall(r"#[0-9A-F]{6}", mono)) <= {"#7B5CFF", logo_icons.mix("#7B5CFF", "#FFFFFF", 0.55)} and credit["style"] == "mono"
    bold, credit = logo_icons.icon_svg("phosphor/microphone", primary="#FF4F8B", font="pretendard")
    assert credit["style"] == "bold" and "currentColor" not in bold and "#FF4F8B" in bold
    assert logo_icons.icon_svg("phosphor/microphone", font="blackhan")[1]["style"] == "fill"  # 굵은 글꼴에는 채운 아이콘
    assert logo_icons.icon_svg("phosphor/microphone", style="thin")[1]["style"] == "thin"
    with pytest.raises(logo_icons.IconError):
        logo_icons.icon_svg("cat-face", style="thin")
    with pytest.raises(logo_icons.IconError):
        logo_icons.icon_svg("cat-face", colors="rainbow")


# --- 마감 ----------------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["fluent", "phosphor", "template", "evil"])
def test_finish_adds_silhouette_layers(source):
    svg = {"fluent": lambda: logo_icons.icon_svg("crown")[0], "phosphor": lambda: logo_icons.icon_svg("phosphor/heart", style="duotone")[0],
           "template": lambda: logo.template_svg("star"), "evil": lambda: logo.sanitize_svg(_evil())}[source]()
    assert logo_icons.finish(svg, "none") == svg
    before = ET.fromstring(svg)
    width = float(re.split(r"[\s,]+", before.get("viewBox"))[2])
    sticker = ET.fromstring(logo_icons.finish(svg, "sticker", "#112233"))
    white, line, *rest = list(sticker)
    assert white.tag == f"{SVG}g" and line.tag == f"{SVG}g" and len(rest) == len(list(before))
    strokes = {shape.get("stroke") for shape in white.iter() if shape.get("stroke")}
    assert strokes == {"#FFFFFF"} and {shape.get("stroke") for shape in line.iter() if shape.get("stroke")} == {"#112233"}
    assert all(shape.get("id") is None and shape.get("opacity") is None for shape in list(white.iter()) + list(line.iter()))
    assert float(sticker.get("viewBox").split()[2]) > width  # 테두리가 잘리지 않게 넓힘
    outline = ET.fromstring(logo_icons.finish(svg, "outline", "#112233"))
    assert len(list(outline)) == len(list(before)) + 1
    widths = [float(shape.get("stroke-width")) for shape in list(outline)[0].iter() if shape.get("stroke-width")]
    assert widths and max(widths) >= 2 * 0.03 * width * 0.99
    with pytest.raises(logo_icons.IconError):
        logo_icons.finish(svg, "glow")


def _evil():
    """외부에서 받은 SVG처럼 그라데이션, 클래스 스타일, use, 변환, 투명도가 섞인 심볼."""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" onload="x()"><defs><linearGradient id="g"><stop offset="0" '
            'stop-color="#f00"/></linearGradient></defs><style>.a{fill:url(#g)}</style><g opacity="0.5" transform="scale(2)">'
            '<circle id="c" cx="16" cy="16" r="10" fill="url(#g)" class="a"/></g><use href="#c"/>'
            '<path d="M4 4L20 4" fill="none" stroke="#000" stroke-width="3"/></svg>')


def test_finished_icons_render_in_qt():
    QtSvg = pytest.importorskip("PySide6.QtSvg")
    from PySide6.QtCore import QByteArray

    for icon in logo_icons.catalog()["icons"]:
        for style in icon["styles"]:
            svg = logo_icons.finish(logo_icons.icon_svg(icon["id"], style=style)[0], "sticker")
            assert QtSvg.QSvgRenderer(QByteArray(svg.encode("utf-8"))).isValid(), (icon["id"], style)


# --- 로고 조합과 기록 -------------------------------------------------------------------------


def test_logo_with_icon_names_the_source_not_ai(tmp_path):
    studio = logo.LogoStudio(folder=tmp_path / "logos", clock=lambda: 1_800_000_000)
    request = {"name": "부동 채널", "font": "blackhan", "symbol": {"icon": "phosphor/microphone", "primary": "#FF4F8B", "accent": "#1E2327"},
               "finish": "sticker"}
    svg = studio.make(request)
    root = ET.fromstring(svg.split("\n", 1)[1])
    assert logo.AI_COMPOSITE not in svg and "Phosphor Icons의 microphone 아이콘(MIT 라이선스" in root.find(f"{SVG}desc").text
    rights = root.find(f"{SVG}metadata").find("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF")[0].find("{http://purl.org/dc/elements/1.1/}rights")
    assert "MIT License" in rights.text and "Phosphor Icons" in rights.text
    assert "#FFFFFF" in svg  # 스티커 흰 테두리
    entry = studio.record({**request, "file": "부동 채널.svg"})
    saved = json.loads((tmp_path / "logos" / "made.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert saved == entry and entry["time"] == 1_800_000_000 and entry["finish"] == "sticker" and entry["file"] == "부동 채널.svg"
    assert entry["symbol"]["kind"] == "icon" and entry["symbol"]["set"] == "Phosphor Icons" and entry["symbol"]["style"] == "fill"
    assert entry["symbol"]["license"] == "MIT" and entry["symbol"]["copyright"] == "Copyright (c) 2023 Phosphor Icons"
    template = studio.record({"name": "부동", "symbol": {"template": "moon"}})
    assert template["symbol"]["kind"] == "template" and template["symbol"]["template"] == "moon"
    preview = studio.preview({"icon": "cat-face", "primary": "112233", "finish": "outline"})
    assert "#112233" in preview
    for bad in ({"icon": "dragon-x"}, {"icon": "cat-face", "style": "thin"}, {"template": "star", "finish": "glow"}):
        with pytest.raises(logo.LogoError):
            studio.make({"name": "부동", "symbol": bad, "finish": bad.get("finish")})
    assert "비독점" in studio.status()["notice"] and "sticker" in studio.status()["finishes"]


def test_third_party_notice_lists_the_bundles():
    import hashlib

    readme = resources.files("debutkit.overlay").joinpath("static", "vendor", "README.txt").read_text(encoding="utf-8")
    for name in (*logo_icons.SETS.values(), "LICENSE-fluent-emoji.txt", "LICENSE-phosphor.txt"):
        assert f"{hashlib.sha256(ICONS.joinpath(name).read_bytes()).hexdigest()}  icons/{name}" in readme, name
    fluent = logo_icons.bundle("fluent")
    assert fluent["version"] in readme and "@phosphor-icons/core 2.1.1 (MIT" in readme
    assert "OpenMoji(CC BY-SA" in readme and "Remix Icon(라이선스가 로고 사용 금지)" in readme


def test_bundle_file_is_deterministic_gzip():
    raw = ICONS.joinpath(logo_icons.SETS["phosphor"]).read_bytes()
    assert raw[:2] == b"\x1f\x8b" and raw[4:8] == b"\x00\x00\x00\x00"  # 시각 정보 없음(같은 입력이면 같은 파일)
    assert json.loads(gzip.decompress(raw))["set"] == "phosphor"
