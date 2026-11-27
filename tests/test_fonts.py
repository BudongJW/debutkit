"""공통 글꼴 목록: 함께 배포한 한글 글꼴(google/fonts OFL, 2,350자 woff2), 모든 도구가 같은 목록, 예전 이름, 내 글꼴, 방송 이미지의 글꼴."""

import sys
from pathlib import Path

import pytest

from debutkit import draw, pick, race, settings
from debutkit.overlay import theme

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "src" / "debutkit" / "overlay" / "static" / "vendor" / "fonts"
STATIC = FONTS.parent.parent
sys.path.insert(0, str(ROOT / "packaging"))
import build_fonts  # noqa: E402


def test_bundled_fonts_ship_with_license_and_face():
    assert len(theme.BUNDLED_FONTS) == 14
    for key, (family, file, _, _) in theme.BUNDLED_FONTS.items():
        assert (FONTS / file).stat().st_size < 450_000, file  # 2,350자만 남겨 작게
        assert (FONTS / file).read_bytes()[:4] == b"wOF2", file
        assert f'font-family: "{family}"; src: url("/vendor/fonts/{file}")' in theme.FONTS and "font-weight: 100 900" in theme.FONTS
        assert key in theme.FONT_CHOICES
    for _, file, name in build_fonts.SOURCES:
        license_text = (FONTS / f"OFL-{name}.txt").read_text(encoding="utf-8")
        assert "SIL Open Font License" in license_text and not build_fonts.reserved_name(license_text), name
        assert file.replace(".ttf", ".subset.woff2") in (STATIC / "vendor" / "README.txt").read_text(encoding="utf-8")
    assert not any("Nanum" in file for _, file, _ in build_fonts.SOURCES)  # 예약 글꼴 이름이 있어 줄일 수 없음


def test_subset_keeps_common_hangul_only():
    fontTools = pytest.importorskip("fontTools.ttLib")
    hangul = build_fonts.ksx1001_hangul()
    assert len(hangul) == 2350 and ord("가") in hangul and ord("똠") not in hangul
    cmap = fontTools.TTFont(str(FONTS / "Jua-Regular.subset.woff2")).getBestCmap()
    assert all(ord(char) in cmap for char in "가나다봄힝A1!?♥★") and ord("똠") not in cmap and ord("뷁") not in cmap  # 2,350자 밖은 다음 글꼴로
    assert build_fonts.reserved_name("Copyright (c) 2010, NHN Corporation, with Reserved Font Name Nanum\n\nThis Font Software is licensed")
    assert not build_fonts.reserved_name("Copyright 2018 The Jua Project Authors\n\nThis Font Software is licensed ... Reserved Font Name ...")


def test_catalog_groups_every_choice_and_adds_my_fonts():
    catalog = theme.font_catalog([{"id": "a" * 24, "ext": "ttf", "name": "내 손글씨"}])
    assert set(theme.FONT_CHOICES) <= set(catalog) and len(theme.FONT_CHOICES) == 23
    assert [catalog[key]["group"] for key in ("jua", "gowundodum", "gamja", "songmyung", "galmuri")] == ["제목", "고딕", "손글씨", "명조", "도트"]
    assert catalog["jua"]["src"] == "/vendor/fonts/Jua-Regular.subset.woff2" and catalog["malgun"]["src"] == ""  # 이 PC 글꼴은 파일 없음
    mine = catalog["user:" + "a" * 24]
    assert mine["group"] == "내 글꼴" and mine["src"] == f"/theme/font?id={'a' * 24}" and mine["css"].startswith('"dk-user-')
    assert catalog["blackhan"]["weight"] == 400 and catalog["jua"]["weight"] == 700  # 굵기 파일 없는 제목 글꼴은 가짜 굵게 없이


def test_tool_font_names_old_and_deleted():
    catalog = theme.tool_fonts({"impact": ("Impact(영문)", "Impact, sans-serif")})
    assert catalog["impact"]["group"] == "이 PC" and catalog["jua"]["label"] == "제목: 주아"
    assert theme.tool_font("serif", catalog, {"serif": "batang"}) == "batang"
    assert theme.tool_font("user:" + "b" * 24, catalog) == "blackhan"  # 지운 내 글꼴은 기본 글꼴로
    assert theme.tool_font("Comic Sans", catalog) is None
    assert theme.font_face("없음", catalog) == theme.font_face("blackhan", catalog)


def test_every_tool_offers_the_same_list():
    common = set(theme.FONT_CHOICES)
    assert common <= set(pick.fonts()) and common <= set(draw.fonts()) and common <= set(race.fonts())
    board = pick.parse_config({"font": "jua"})
    assert board.display()["font_css"][0].startswith('"Jua"')
    assert pick.parse_config({"font": "serif"}).font == "batang"  # 예전 이름
    with pytest.raises(pick.PickError, match="글꼴은 목록에서"):
        pick.parse_config({"font": "Comic Sans"})
    options = race.check_options({"font": "gamja"})
    assert options["font"] == "gamja" and race.check_options({"font": "impact"})["font"] == "impact"  # 레이스만의 이 PC 글꼴도
    assert race.choices()["fonts"]["gamja"]["css"].startswith('"Gamja Flower"')


def test_my_font_reaches_tools(tmp_path, monkeypatch):
    settings.save_data(theme.DATA, {"fonts": [{"id": "c" * 24, "ext": "woff2", "name": "방송 글씨"}]})
    key = "user:" + "c" * 24
    assert pick.options()["fonts"][key] == "내 글꼴: 방송 글씨"
    assert pick.parse_config({"font": key}).display()["font_css"][0].startswith(f'"dk-user-{"c" * 24}"')
    assert draw.load_config({"draw_name_font": key}).name_font == key


def test_image_maker_loads_the_chosen_font_before_drawing():
    page = (STATIC / "decor.html").read_text(encoding="utf-8")
    script = (STATIC / "decor.js").read_text(encoding="utf-8")
    assert 'id="title-font"' in page and 'id="text-font"' in page
    assert "new FontFace(item.family" in script and "font_catalog" in script and "optgroup" in script
    assert "'\"Black Han Sans\", sans-serif', size, maxWidth)" not in script  # 고른 글꼴로
