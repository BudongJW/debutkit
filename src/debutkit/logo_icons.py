"""로고 심볼 아이콘 묶음과 마감(외곽선, 스티커 테두리).

- 아이콘: Microsoft Fluent Emoji(MIT)의 Flat(컬러 평면)과 High Contrast(단색), Phosphor Icons(MIT)의 굵기 6종.
  버튜버 주제(동물, 표정, 하트, 별과 달, 마이크와 헤드폰, 게임, 디저트 등)만 골라 한국어 이름과 검색어를 붙여 함께 배포
  (``packaging/build_icons.py`` 로 만든 ``overlay/static/vendor/icons/*.json.gz``). 인터넷 연결 없이 동작
- 채널 색 다시 칠하기: 컬러 아이콘은 가장 넓은 유채색을 주 색에 맞추고 다른 유채색은 원래 밝기 차이를 유지한 같은 계열 색으로,
  어두운 무채색(눈, 입)은 보조 색, 흰색과 회색은 그대로. 단색 아이콘은 주 색 한 가지
- 굵기 맞춤: Phosphor는 채널 이름 글꼴에 맞춰 굵기 자동 선택(Pretendard Bold는 bold, Black Han Sans는 fill)
- 마감: 심볼 전체 실루엣을 따라 외곽선과 스티커 흰 테두리. 도형을 복사해 한 색 채우기와 굵은 선으로 뒤에 깔아 만든다
  (SVG 기본 기능만 사용, 추가 라이브러리 없음). 기본 도형과 AI 심볼에도 같은 마감 적용
- 아이콘은 모든 사용자가 같은 그림을 쓰는 비독점 재료라 상표 독점력이 약하다(로고 화면과 사용 설명서에 안내)
"""

from __future__ import annotations

import copy
import gzip
import json
import math
import re
import xml.etree.ElementTree as ET
from functools import lru_cache
from importlib import resources
from typing import Any

SVG_NS = "http://www.w3.org/2000/svg"
SETS = {"fluent": "fluent-emoji.json.gz", "phosphor": "phosphor.json.gz"}
#: 채널 이름 글꼴에 맞춘 Phosphor 굵기
FONT_WEIGHTS = {"pretendard": "bold", "blackhan": "fill"}
COLOR_MODES = {"channel": "채널 색", "original": "원래 색"}
#: 마감: (외곽선 굵기, 흰 테두리 굵기) 심볼 크기 대비 비율
FINISHES = {"none": ("없음", 0.0, 0.0), "outline": ("외곽선", 0.03, 0.0), "bold": ("굵은 외곽선", 0.055, 0.0),
            "sticker": ("스티커(외곽선과 흰 테두리)", 0.03, 0.05), "white": ("흰 테두리", 0.0, 0.05)}
SHAPES = {"path", "circle", "ellipse", "rect", "polygon", "polyline", "line", "text"}
_SKIP_IN_COPY = {"defs", "clippath", "mask", "lineargradient", "radialgradient", "filter", "style", "title", "desc", "metadata", "symbol", "use"}
_HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
ET.register_namespace("", SVG_NS)


class IconError(ValueError):
    """아이콘 찾기, 처리 실패. 메시지는 한국어 안내."""


# --- 묶음 읽기 -----------------------------------------------------------------------------


@lru_cache(maxsize=4)
def bundle(set_id: str) -> dict[str, Any]:
    if set_id not in SETS:
        raise IconError(f"아이콘 묶음은 {', '.join(SETS)} 중 하나")
    source = resources.files("debutkit.overlay").joinpath("static", "vendor", "icons", SETS[set_id])
    return json.loads(gzip.decompress(source.read_bytes()).decode("utf-8"))


@lru_cache(maxsize=1)
def _index() -> dict[str, dict[str, Any]]:
    return {icon["id"]: icon for set_id in SETS for icon in bundle(set_id)["icons"]}


def find(icon_id: Any) -> dict[str, Any]:
    """아이콘 id(예: fluent/cat-face, phosphor/microphone). 묶음 이름 없이 주면 Fluent 먼저."""
    text = str(icon_id or "").strip().lower()
    index = _index()
    found = index.get(text) or index.get(f"fluent/{text}") or index.get(f"phosphor/{text}")
    if found is None:
        raise IconError(f"아이콘을 찾지 못함: {icon_id}. debutkit logo icons 검색어 로 목록 확인")
    return found


def set_of(icon: dict[str, Any]) -> dict[str, Any]:
    return bundle(icon["id"].split("/", 1)[0])


def catalog() -> dict[str, Any]:
    """화면용 목록(그림 없이 이름, 분류, 검색어, 고를 수 있는 종류)."""
    sets = {}
    icons = []
    for set_id in SETS:
        data = bundle(set_id)
        sets[set_id] = {"title": data["title"], "license": data["license"], "styles": data["styles"], "source": data["source"]}
        icons += [{"id": icon["id"], "set": set_id, "ko": icon["ko"], "name": icon["name"], "category": icon["category"],
                   "tags": icon["tags"], "styles": list(icon["svg"])} for icon in data["icons"]]
    return {"sets": sets, "categories": bundle("fluent")["categories"], "icons": icons, "color_modes": COLOR_MODES,
            "finishes": {key: value[0] for key, value in FINISHES.items()}, "font_weights": FONT_WEIGHTS}


def search(words: str, limit: int = 40) -> list[dict[str, Any]]:
    """한국어나 영어 검색어로 아이콘 찾기(이름, 검색어, 분류 이름 포함 여부)."""
    terms = [term for term in words.lower().split() if term]
    categories = bundle("fluent")["categories"]
    found = []
    for icon in _index().values():
        haystack = " ".join([icon["ko"], icon["name"], icon["id"], categories.get(icon["category"], ""), *icon["tags"]]).lower()
        if all(term in haystack for term in terms):
            found.append(icon)
    return found[:limit]


def credit(icon: dict[str, Any], style: str) -> dict[str, str]:
    """로고 기록과 SVG 설명에 남길 출처(세트, 아이콘 이름, 라이선스)."""
    data = set_of(icon)
    return {"set": data["title"], "icon": icon["name"], "id": icon["id"], "style": style, "license": data["license"],
            "copyright": data["copyright"], "source": data["source"], "version": str(data["version"])}


def pick_style(icon: dict[str, Any], style: Any, font: str | None) -> str:
    """고를 수 있는 종류 중 하나. 비었거나 auto면 Fluent는 컬러, Phosphor는 글꼴에 맞춘 굵기."""
    styles = list(icon["svg"])
    if style in styles:
        return str(style)
    if style not in (None, "", "auto"):
        raise IconError(f"{icon['ko']} 아이콘의 종류는 auto, " + ", ".join(styles) + " 중 하나")
    if icon["id"].startswith("phosphor/"):
        return FONT_WEIGHTS.get(font or "pretendard", "bold")
    return "flat"


# --- 색 ------------------------------------------------------------------------------------


def _linear(value: float) -> float:
    value /= 255.0
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _gamma(value: float) -> float:
    return 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055


def oklch(colour: str) -> tuple[float, float, float]:
    """#RRGGBB를 OKLCh(밝기 0에서 1, 채도, 색상 각도)로. 사람 눈 기준 밝기를 유지한 채 색상만 바꾸기 위해."""
    red, green, blue = (_linear(int(colour[index:index + 2], 16)) for index in (1, 3, 5))
    l_ = (0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue) ** (1 / 3)
    m_ = (0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue) ** (1 / 3)
    s_ = (0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue) ** (1 / 3)
    lightness = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return lightness, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def _rgb(lightness: float, chroma: float, hue: float) -> tuple[float, float, float]:
    a, b = chroma * math.cos(math.radians(hue)), chroma * math.sin(math.radians(hue))
    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_, -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
            -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_)


def from_oklch(lightness: float, chroma: float, hue: float) -> str:
    """OKLCh를 #RRGGBB로. 화면에 없는 색이면 밝기와 색상은 두고 채도만 줄인다."""
    lightness = min(max(lightness, 0.0), 1.0)
    low, high = 0.0, max(chroma, 0.0)
    if all(-1e-4 <= part <= 1 + 1e-4 for part in _rgb(lightness, high, hue)):
        low = high
    else:
        for _ in range(24):
            middle = (low + high) / 2
            if all(-1e-4 <= part <= 1 + 1e-4 for part in _rgb(lightness, middle, hue)):
                low = middle
            else:
                high = middle
    channels = [min(max(round(_gamma(min(max(part, 0.0), 1.0)) * 255), 0), 255) for part in _rgb(lightness, low, hue)]
    return "#" + "".join(f"{value:02X}" for value in channels)


def mix(colour: str, other: str, share: float) -> str:
    """두 색을 섞기(share는 other 쪽 비율)."""
    parts = [round(int(colour[index:index + 2], 16) * (1 - share) + int(other[index:index + 2], 16) * share) for index in (1, 3, 5)]
    return "#" + "".join(f"{value:02X}" for value in parts)


NEUTRAL = 0.045  # 이 채도보다 낮으면 무채색(흰색, 회색, 검정)
DARK = 0.42  # 이 밝기보다 어두운 무채색은 보조 색으로


def channel_palette(areas: dict[str, float], primary: str, accent: str) -> dict[str, str]:
    """컬러 아이콘의 원래 색별 새 색. 가장 넓은 유채색이 주 색이 되고 다른 유채색은 밝기와 채도 차이를 유지한 주 색 계열."""
    target = oklch(primary)
    accent_dark = oklch(accent)[0] < 0.5
    lch = {colour: oklch(colour) for colour in areas}
    chromatic = [colour for colour, value in lch.items() if value[1] >= NEUTRAL]
    group = chromatic or list(areas)  # 무채색만 있는 아이콘(흰 하트, 해골)은 전체를 주 색 계열로
    reference = max(group, key=lambda colour: areas[colour])
    ref_l, ref_c, _ = lch[reference]
    mapped = {}
    for colour, (lightness, chroma, _) in lch.items():
        if colour in group:
            new_l = min(max(lightness + (target[0] - ref_l), 0.12), 0.97)
            new_c = target[1] * (chroma / ref_c) if ref_c >= 0.02 else target[1]
            mapped[colour] = from_oklch(new_l, min(new_c, 0.37), target[2])
        elif lightness < DARK and accent_dark:
            mapped[colour] = accent.upper()
        else:
            mapped[colour] = colour
    return mapped


def recolor(svg: str, mapping: dict[str, str]) -> str:
    return _HEX.sub(lambda match: mapping.get(match.group(0).upper(), match.group(0)), svg)


def mono(svg: str, colour: str) -> str:
    """단색 아이콘을 한 색으로(밝은 보조 회색은 그 색의 옅은 색으로)."""
    light = mix(colour, "#FFFFFF", 0.55)
    svg = _HEX.sub(lambda match: light if oklch(match.group(0))[0] > 0.6 else colour, svg)  # 원래 색 기준(바꾼 색을 다시 바꾸지 않게)
    return svg.replace("currentColor", colour)


def icon_svg(icon_id: Any, *, style: Any = None, colors: Any = "channel", primary: str = "#FF4F8B", accent: str = "#1E2327",
             font: str | None = None) -> tuple[str, dict[str, str]]:
    """아이콘 SVG와 출처. ``colors`` 는 channel(채널 색) 또는 original(원래 색, 컬러 아이콘만)."""
    icon = find(icon_id)
    chosen = pick_style(icon, style, font)
    if colors not in COLOR_MODES:
        raise IconError("아이콘 색은 channel(채널 색) 또는 original(원래 색)")
    svg = icon["svg"][chosen]
    if chosen == "flat":
        if colors == "channel":
            svg = recolor(svg, channel_palette(icon["areas"], primary, accent))
    else:
        svg = mono(svg, primary)
    return svg, credit(icon, chosen)


# --- 마감(외곽선, 스티커 테두리) --------------------------------------------------------------


def _local(tag: Any) -> str:
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def _number(value: Any, default: float) -> float:
    match = re.match(r"\s*(-?[0-9.]+(?:e-?\d+)?)", str(value or ""))
    try:
        return float(match.group(1)) if match else default
    except ValueError:
        return default


def _style(element: ET.Element) -> dict[str, str]:
    """style 속성의 fill, stroke 등(속성보다 우선)."""
    found = {}
    for part in (element.get("style") or "").split(";"):
        if ":" in part:
            key, value = part.split(":", 1)
            found[key.strip().lower()] = value.strip()
    return found


def _scale(transform: str | None) -> float:
    """변환의 길이 배율(선 굵기를 화면 기준으로 맞추기 위해). 회전, 이동은 1."""
    factor = 1.0
    for name, raw in re.findall(r"(\w+)\s*\(([^)]*)\)", transform or ""):
        values = [float(part) for part in re.split(r"[\s,]+", raw.strip()) if part]
        if name == "scale" and values:
            factor *= math.sqrt(abs(values[0] * (values[1] if len(values) > 1 else values[0])))
        elif name == "matrix" and len(values) >= 4:
            factor *= math.sqrt(abs(values[0] * values[3] - values[1] * values[2]))
    return factor or 1.0


def _silhouette(children: list[ET.Element], colour: str, width: float, inherited: dict[str, Any]) -> list[ET.Element]:
    """도형을 복사해 한 색 채우기와 굵은 선으로(뒤에 깔면 전체 실루엣을 따라 테두리가 생김)."""
    out = []
    for child in children:
        name = _local(child.tag)
        if name in _SKIP_IN_COPY:
            continue
        style = _style(child)
        state = dict(inherited)
        for key in ("fill", "stroke", "stroke-width"):
            if key in style or child.get(key) is not None:
                state[key] = style.get(key, child.get(key))
        state["scale"] = inherited["scale"] * _scale(child.get("transform"))
        made = ET.Element(child.tag, {key: value for key, value in child.attrib.items()
                                      if key not in ("id", "style", "class", "opacity", "fill-opacity", "stroke-opacity", "filter")})
        if name in SHAPES:
            stroked = str(state["stroke"] or "none").lower() != "none"
            base = _number(state["stroke-width"], 1.0) if stroked else 0.0
            made.set("fill", "none" if str(state["fill"] or "").lower() == "none" else colour)
            made.set("stroke", colour)
            made.set("stroke-width", f"{base + 2 * width / state['scale']:.3f}")
            made.set("stroke-linejoin", "round")
            made.set("stroke-linecap", "round")
            made.text = child.text if name == "text" else None
            made.extend(copy.deepcopy(list(child)) if name == "text" else [])
        else:
            made.extend(_silhouette(list(child), colour, width, state))
        out.append(made)
    return out


def finish(svg: str, kind: Any = "none", colour: str = "#1E2327") -> str:
    """심볼 마감: outline(외곽선), bold(굵은 외곽선), sticker(외곽선과 흰 테두리), white(흰 테두리), none."""
    if kind in (None, "", "none"):
        return svg
    if kind not in FINISHES:
        raise IconError("마감은 " + ", ".join(FINISHES) + " 중 하나")
    _, line_share, white_share = FINISHES[kind]
    root = ET.fromstring(svg)
    from .logo import view_box  # 순환 가져오기 방지

    min_x, min_y, width, height = view_box(root)
    size = max(width, height)
    line, white = size * line_share, size * white_share
    edge = line + white
    pad = edge * 1.1
    inherited = {"fill": root.get("fill") or _style(root).get("fill") or "#000000", "stroke": root.get("stroke") or "none",
                 "stroke-width": root.get("stroke-width") or "1", "scale": 1.0}
    content = list(root)
    layers: list[ET.Element] = []
    if white:
        group = ET.Element(f"{{{SVG_NS}}}g")
        group.extend(_silhouette(content, "#FFFFFF", edge, inherited))
        layers.append(group)
    if line:
        group = ET.Element(f"{{{SVG_NS}}}g")
        group.extend(_silhouette(content, colour, line, inherited))
        layers.append(group)
    for child in content:
        root.remove(child)
    root.extend(layers + content)
    root.set("viewBox", f"{min_x - pad:.3f} {min_y - pad:.3f} {width + 2 * pad:.3f} {height + 2 * pad:.3f}")
    for key in ("width", "height"):
        root.attrib.pop(key, None)
    return ET.tostring(root, encoding="unicode")
