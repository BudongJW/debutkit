"""방송 로고 만들기: 심볼과 채널 이름을 조합한 SVG 로고.

- 심볼: 기본 도형(무료, 인터넷 연결 없음) 또는 사용자 본인의 API 키로 생성형 AI가 만든 SVG(Claude가 SVG 코드를 직접 작성,
  OpenAI GPT-Image-2.6, Recraft V4.1 Vector). AI에는 글자 없는 심볼만 맡긴다(생성 이미지 안의 한글은 자모가 틀리기 쉬움)
- 채널 이름: 함께 배포한 글꼴(Pretendard, Black Han Sans, SIL Open Font License)의 윤곽선으로 넣어 글꼴 설치 없이 어디서나 같게 보인다
- 외부에서 받은 SVG는 정리(스크립트, 외부 연결, 내장 이미지 제거)한 뒤에만 쓴다
- AI가 만든 심볼이 들어간 로고에는 생성 방식(IPTC 디지털 소스 유형)과 사용한 서비스를 파일 메타데이터로 남긴다(인공지능 기본법 표시 취지)
- API 키는 사용자 것만 쓴다(공용 키 없음). secret.KeyBox로 암호화 보관. 설명 문장은 선택한 AI 서비스로 전송된다
"""

from __future__ import annotations

import base64
import json
import math
import re
import secrets as random_ids
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Callable

from . import __version__, settings
from .secret import KeyBox

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
IPTC_NS = "http://iptc.org/std/Iptc4xmpExt/2008-02-29/"
#: IPTC 디지털 소스 유형: AI 심볼에 사람이 고른 글꼴 글자를 합친 결과
AI_COMPOSITE = "http://cv.iptc.org/newscodes/digitalsourcetype/compositeWithTrainedAlgorithmicMedia"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)
ET.register_namespace("rdf", RDF_NS)
ET.register_namespace("Iptc4xmpExt", IPTC_NS)

NAME_LIMIT = 30
DESCRIPTION_LIMIT = 300
SVG_LIMIT = 3_000_000  # 받은 SVG 최대 크기(바이트)
KEEP = 30  # 메모리에 두는 최근 심볼 수


class LogoError(ValueError):
    """로고 만들기 실패. 메시지는 한국어 안내."""


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    models: dict[str, str]  # fast, best
    price: dict[str, str]
    terms: str
    key_hint: str
    endpoint: str


CLAUDE_MODEL = "claude-opus-5-5"
#: Claude는 그림 모델이 아니므로 SVG 코드를 직접 쓰게 한다(단순한 평면 도형 위주)
CLAUDE_SYSTEM = ("You design simple flat vector logo symbols for live-streaming channels. Reply with exactly one complete SVG document and "
                 "nothing else: start with <svg and end with </svg>, no markdown fences, no explanation. Use xmlns=\"http://www.w3.org/2000/svg\" "
                 "and viewBox=\"0 0 100 100\". Use only basic shapes (path, circle, ellipse, rect, polygon, g) with solid fills or simple "
                 "linear gradients, at most about 40 elements. Never use text, letters, numbers, <image>, <foreignObject>, scripts, CSS "
                 "imports or external references. Keep a strong silhouette that reads at 32 pixels.")

PROVIDERS: dict[str, Provider] = {
    "claude": Provider("claude", "Claude", {"fast": CLAUDE_MODEL, "best": CLAUDE_MODEL},
                       {"fast": "토큰 과금(Claude Opus 5.5, 노력 낮음). 1개 약 0.02~0.1달러(추정)",
                        "best": "토큰 과금(Claude Opus 5.5, 노력 높음). 1개 약 0.05~0.3달러(추정)"},
                       "Anthropic 이용 약관과 사용 정책 적용. Claude는 그림 대신 SVG 코드를 직접 작성하므로 단순한 도형 위주",
                       "platform.claude.com의 API keys 화면", "https://api.anthropic.com/v1/messages"),
    "openai": Provider("openai", "OpenAI", {"fast": "gpt-image-2.6-flare", "best": "gpt-image-2.6-sunburst"},
                       {"fast": "토큰 과금(참조 이미지와 SVG 작성 합산, 고정가 없음)", "best": "토큰 과금(빠름보다 비쌈)"},
                       "OpenAI 이용 약관 적용: 이미지 모델은 조직 인증(Organization verification) 필요, 만 18세 미만은 보호자 동의 필요",
                       "platform.openai.com의 API keys 화면", "https://api.openai.com/v1/images/generations"),
    "recraft": Provider("recraft", "Recraft", {"fast": "recraftv4_1_vector", "best": "recraftv4_1_pro_vector"},
                        {"fast": "1장 0.08달러", "best": "1장 0.30달러"},
                        "Recraft 이용 약관 적용: API는 만 18세 이상만 사용 가능",
                        "recraft.ai의 API 화면에서 발급한 토큰", "https://external.api.recraft.ai/v1/images/generations"),
}
QUALITIES = {"fast": "빠름", "best": "고품질"}
STYLES = {
    "cute": ("귀여운", "cute and friendly, rounded shapes"),
    "minimal": ("단순한", "minimal geometric shapes, very few details"),
    "bold": ("강렬한", "bold silhouette, high contrast, thick outlines"),
    "retro": ("레트로", "retro badge feeling, limited colors"),
}
LAYOUTS = {"horizontal": "가로(심볼 왼쪽)", "vertical": "세로(심볼 위)", "symbol": "심볼만", "name": "이름만"}


@dataclass(frozen=True)
class Font:
    id: str
    name: str
    file: str


FONTS = {
    "pretendard": Font("pretendard", "Pretendard Bold", "Pretendard-Bold.subset.woff2"),
    "blackhan": Font("blackhan", "Black Han Sans", "BlackHanSans-Regular.woff2"),
}
_COLOR = re.compile(r"^#?([0-9a-fA-F]{6})$")


def check_color(value: Any) -> str:
    match = _COLOR.match(value.strip()) if isinstance(value, str) else None
    if not match:
        raise LogoError("색은 16진수 6자리(예: #FF4F8B)")
    return "#" + match.group(1).upper()


def check_colors(values: Any) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list) or len(values) > 4:
        raise LogoError("색은 최대 4개")
    return [check_color(value) for value in values]


def check_name(value: Any) -> str:
    text = " ".join(value.split()) if isinstance(value, str) else ""
    if len(text) > NAME_LIMIT or any(ord(ch) < 32 for ch in text):
        raise LogoError(f"채널 이름은 {NAME_LIMIT}자 이하")
    return text


def check_description(value: Any) -> str:
    text = " ".join(value.split()) if isinstance(value, str) else ""
    if not text or len(text) > DESCRIPTION_LIMIT:
        raise LogoError(f"심볼 설명은 1에서 {DESCRIPTION_LIMIT}자(예: 고양이 귀가 달린 헤드폰)")
    return text


def check_key(value: Any) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not 8 <= len(text) <= 300 or any(not 33 <= ord(ch) <= 126 for ch in text):
        raise LogoError("API 키가 올바르지 않음: 서비스 화면의 키를 그대로 복사해 붙여 넣기")
    return text


def check_choice(value: Any, choices: dict[str, Any], label: str) -> str:
    if value not in choices:
        raise LogoError(f"{label}은(는) " + ", ".join(choices) + " 중 하나")
    return str(value)


def build_prompt(description: str, style: str, colors: list[str]) -> str:
    """글자 없는 심볼 요청. 채널 이름은 debutkit이 실제 글꼴로 넣는다."""
    palette = ", ".join(colors) if colors else "a small harmonious palette"
    return (f"A logo symbol for a VTuber live-streaming channel. Subject: {description}. Style: {STYLES[style][1]}. "
            f"Flat vector shapes with a clear silhouette that stays readable at 32 pixels, centered, on a plain empty background. "
            f"Use only these colors: {palette}. Absolutely no text, letters, numbers, signatures or watermarks. "
            f"Do not imitate existing logos, trademarks or known characters.")


# --- 외부 SVG 정리 --------------------------------------------------------------------------

_ALLOWED = {"svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "defs", "lineargradient", "radialgradient",
            "stop", "clippath", "mask", "title", "desc", "use", "symbol", "text", "tspan", "style", "filter", "fegaussianblur", "feoffset",
            "feblend", "fecolormatrix", "fecomposite", "feflood", "femerge", "femergenode", "femorphology", "fedropshadow"}
_URL = re.compile(r"url\(\s*['\"]?([^)'\"]*)", re.IGNORECASE)


def _local(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def _safe_value(value: str) -> bool:
    lowered = value.lower()
    if "javascript:" in lowered or "data:" in lowered or "@import" in lowered or "expression(" in lowered:
        return False
    return all(target.strip().startswith("#") for target in _URL.findall(value))


def _clean(element: ET.Element) -> None:
    for child in list(element):
        tag = child.tag if isinstance(child.tag, str) else ""
        if not tag.startswith("{" + SVG_NS + "}") or _local(tag).lower() not in _ALLOWED:
            element.remove(child)
            continue
        if _local(tag).lower() == "style" and not _safe_value(child.text or ""):
            element.remove(child)
            continue
        for key in list(child.attrib):
            name, value = _local(key).lower(), child.attrib[key]
            if name.startswith("on") or (name == "href" and not value.startswith("#")) or not _safe_value(value):
                del child.attrib[key]
        _clean(child)


def sanitize_svg(text: str) -> str:
    """외부에서 받은 SVG에서 SVG 도형, 그라디언트, 글자만 남긴다(스크립트, 이벤트, 외부 주소, 내장 이미지 제거)."""
    if not isinstance(text, str) or not text.strip():
        raise LogoError("받은 SVG가 비어 있음")
    if len(text.encode("utf-8")) > SVG_LIMIT:
        raise LogoError("받은 SVG가 너무 큼(3 MB 초과)")
    lowered = text.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise LogoError("받은 SVG에 허용하지 않는 선언(DOCTYPE)이 있음")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise LogoError(f"받은 SVG를 읽지 못함: {error}") from error
    if root.tag != "{" + SVG_NS + "}svg":
        raise LogoError("받은 파일이 SVG가 아님")
    for key in list(root.attrib):
        name, value = _local(key).lower(), root.attrib[key]
        if name.startswith("on") or name == "href" or not _safe_value(value):
            del root.attrib[key]
    _clean(root)
    return ET.tostring(root, encoding="unicode")


def view_box(root: ET.Element) -> tuple[float, float, float, float]:
    """SVG의 좌표 영역(viewBox, 없으면 width와 height, 그것도 없으면 1024)."""
    raw = root.get("viewBox")
    if raw:
        parts = [float(part) for part in re.split(r"[\s,]+", raw.strip()) if part]
        if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
            return parts[0], parts[1], parts[2], parts[3]

    def length(name: str) -> float:
        match = re.match(r"^\s*([0-9.]+)", root.get(name) or "")
        return float(match.group(1)) if match else 0.0

    width, height = length("width"), length("height")
    return (0.0, 0.0, width, height) if width > 0 and height > 0 else (0.0, 0.0, 1024.0, 1024.0)


# --- 기본 도형(무료) -----------------------------------------------------------------------


def _star(points: int, outer: float, inner: float) -> str:
    coords = []
    for index in range(points * 2):
        radius = outer if index % 2 == 0 else inner
        angle = math.pi * index / points - math.pi / 2
        coords.append(f"{50 + radius * math.cos(angle):.2f},{52 + radius * math.sin(angle):.2f}")
    return " ".join(coords)


TEMPLATES: dict[str, tuple[str, Callable[[str, str], str]]] = {
    "star": ("별", lambda a, b: f'<polygon points="{_star(5, 46, 20)}" fill="{a}" stroke="{b}" stroke-width="5" stroke-linejoin="round"/>'),
    "heart": ("하트", lambda a, b: f'<path d="M50 88C22 68 6 50 6 31 6 17 17 7 30 7c9 0 16 5 20 12 4-7 11-12 20-12 13 0 24 10 24 24 0 19-16 37-44 57z" '
                                   f'fill="{a}"/><circle cx="30" cy="30" r="7" fill="{b}" opacity="0.35"/>'),
    "sparkle": ("반짝임", lambda a, b: f'<path d="M46 6c4 28 14 38 42 42-28 4-38 14-42 42-4-28-14-38-42-42 28-4 38-14 42-42z" fill="{a}"/>'
                                     f'<path d="M82 66c1.5 9 5 12.5 14 14-9 1.5-12.5 5-14 14-1.5-9-5-12.5-14-14 9-1.5 12.5-5 14-14z" fill="{b}"/>'),
    "moon": ("달", lambda a, b: f'<path d="M60 6a44 44 0 1 0 34 66A36 36 0 1 1 60 6z" fill="{a}"/><circle cx="74" cy="24" r="5" fill="{b}"/>'
                               f'<circle cx="86" cy="42" r="3" fill="{b}"/>'),
    "crown": ("왕관", lambda a, b: f'<path d="M10 78 16 26 36 50 50 16 64 50 84 26 90 78z" fill="{a}" stroke="{b}" stroke-width="4" stroke-linejoin="round"/>'
                                  f'<rect x="10" y="78" width="80" height="12" rx="4" fill="{b}"/>'),
    "bubble": ("말풍선", lambda a, b: f'<path d="M18 10h64a12 12 0 0 1 12 12v40a12 12 0 0 1-12 12H44L24 92V74h-6A12 12 0 0 1 6 62V22a12 12 0 0 1 12-12z" '
                                    f'fill="{a}"/><circle cx="32" cy="42" r="6" fill="{b}"/><circle cx="50" cy="42" r="6" fill="{b}"/>'
                                    f'<circle cx="68" cy="42" r="6" fill="{b}"/>'),
    "paw": ("발바닥", lambda a, b: f'<path d="M50 50c16 0 30 14 30 28 0 10-8 14-16 12-6-1-9-4-14-4s-8 3-14 4c-8 2-16-2-16-12 0-14 14-28 30-28z" fill="{a}"/>'
                                 f'<ellipse cx="20" cy="40" rx="9" ry="12" fill="{a}"/><ellipse cx="38" cy="22" rx="9" ry="12" fill="{a}"/>'
                                 f'<ellipse cx="62" cy="22" rx="9" ry="12" fill="{a}"/><ellipse cx="80" cy="40" rx="9" ry="12" fill="{a}"/>'
                                 f'<circle cx="50" cy="70" r="6" fill="{b}" opacity="0.4"/>'),
    "badge": ("둥근 배지", lambda a, b: f'<circle cx="50" cy="50" r="44" fill="{a}"/><circle cx="50" cy="50" r="34" fill="none" stroke="{b}" stroke-width="5"/>'
                                      f'<circle cx="50" cy="50" r="12" fill="{b}"/>'),
}


def template_svg(template: str, primary: str = "#FF4F8B", accent: str = "#1E2327") -> str:
    check_choice(template, TEMPLATES, "기본 도형")
    inner = TEMPLATES[template][1](check_color(primary), check_color(accent))
    return f'<svg xmlns="{SVG_NS}" viewBox="0 0 100 100">{inner}</svg>'


# --- 채널 이름 글꼴 윤곽선 -----------------------------------------------------------------


@lru_cache(maxsize=4)
def _font(font_id: str) -> Any:
    try:
        from fontTools.ttLib import TTFont
    except ImportError as error:
        raise LogoError('채널 이름 글자 처리에 fontTools 필요: pip install "debutkit[logo]"') from error
    source = resources.files("debutkit.overlay").joinpath("static", "vendor", "fonts", FONTS[font_id].file)
    try:
        with resources.as_file(source) as path:
            return TTFont(str(path))
    except ImportError as error:  # woff2 압축 해제에 brotli 필요
        raise LogoError('글꼴 압축 해제에 brotli 필요: pip install "debutkit[logo]"') from error


@dataclass(frozen=True)
class TextShape:
    path: str
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top


def text_shape(text: str, font_id: str = "pretendard", size: float = 100.0) -> TextShape:
    """글자를 윤곽선 경로로(기준선 y=0, 아래로 갈수록 y 증가). 글꼴에 없는 글자는 안내와 함께 실패."""
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen

    check_choice(font_id, FONTS, "글꼴")
    font = _font(font_id)
    cmap = font.getBestCmap()
    missing = "".join(dict.fromkeys(ch for ch in text if not ch.isspace() and ord(ch) not in cmap))
    if missing:
        raise LogoError(f"{FONTS[font_id].name} 글꼴에 없는 글자: {missing}. 다른 글꼴을 고르거나 글자 바꾸기")
    glyphs = font.getGlyphSet()
    scale = size / font["head"].unitsPerEm
    metrics = font["hmtx"]
    path_pen = SVGPathPen(glyphs, ntos=lambda value: f"{value:.2f}".rstrip("0").rstrip("."))
    bounds = BoundsPen(glyphs)
    x = 0.0
    for ch in text:
        name = cmap.get(ord(ch))
        if name is None:  # 공백이 글꼴에 없을 때
            x += size * 0.3 / scale
            continue
        transform = (scale, 0, 0, -scale, x * scale, 0)
        glyphs[name].draw(TransformPen(path_pen, transform))
        glyphs[name].draw(TransformPen(bounds, transform))
        x += metrics[name][0]
    if bounds.bounds is None:
        raise LogoError("채널 이름에 그릴 글자가 없음")
    left, top, right, bottom = bounds.bounds
    return TextShape(path_pen.getCommands(), left, top, right, bottom)


# --- 조합 ----------------------------------------------------------------------------------


def _number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def compose(symbol: str | None, name: str, *, font: str = "pretendard", layout: str = "horizontal", text_color: str = "#1E2327",
            background: str | None = None, source: dict[str, str] | None = None) -> str:
    """심볼(정리한 SVG)과 채널 이름으로 로고 SVG. ``source`` 가 있으면 AI 생성 표시(메타데이터와 설명)를 넣는다."""
    layout = check_choice(layout, LAYOUTS, "배치")
    name = check_name(name)
    if layout != "symbol" and not name:
        raise LogoError("채널 이름 필요")
    if layout != "name" and not symbol:
        raise LogoError("심볼 필요: 기본 도형을 고르거나 AI로 만들기")
    color = check_color(text_color)
    pad = 24.0
    shape = text_shape(name, font) if layout != "symbol" else None
    side = {"horizontal": 170.0, "vertical": 240.0, "symbol": 512.0, "name": 0.0}[layout]
    symbol_at = (pad, pad)
    text_at = (0.0, 0.0)
    if layout == "horizontal" and shape:
        gap = 36.0
        height = max(side, shape.height)
        symbol_at = (pad, pad + (height - side) / 2)
        text_at = (pad + side + gap - shape.left, pad + height / 2 - (shape.top + shape.bottom) / 2)
        width_total, height_total = pad * 2 + side + gap + shape.width, pad * 2 + height
    elif layout == "vertical" and shape:
        gap = 28.0
        inner = max(side, shape.width)
        symbol_at = (pad + (inner - side) / 2, pad)
        text_at = (pad + (inner - shape.width) / 2 - shape.left, pad + side + gap - shape.top)
        width_total, height_total = pad * 2 + inner, pad * 2 + side + gap + shape.height
    elif layout == "name" and shape:
        text_at = (pad - shape.left, pad - shape.top)
        width_total, height_total = pad * 2 + shape.width, pad * 2 + shape.height
    else:
        width_total = height_total = pad * 2 + side

    root = ET.Element(f"{{{SVG_NS}}}svg", {"viewBox": f"0 0 {_number(width_total)} {_number(height_total)}",
                                             "width": _number(width_total), "height": _number(height_total)})
    ET.SubElement(root, f"{{{SVG_NS}}}title").text = name or "로고"
    description = "debutkit 로고 만들기."
    if source:
        description += f" 심볼은 생성형 AI({source.get('provider', '')} {source.get('model', '')})로 생성. 채널 이름은 {FONTS[font].name} 글꼴."
        metadata = ET.SubElement(root, f"{{{SVG_NS}}}metadata")
        rdf = ET.SubElement(metadata, f"{{{RDF_NS}}}RDF")
        ET.SubElement(rdf, f"{{{RDF_NS}}}Description", {f"{{{IPTC_NS}}}DigitalSourceType": AI_COMPOSITE})
    elif layout != "name":
        description += " 심볼은 debutkit 기본 도형."
    ET.SubElement(root, f"{{{SVG_NS}}}desc").text = description
    if background:
        ET.SubElement(root, f"{{{SVG_NS}}}rect", {"width": _number(width_total), "height": _number(height_total), "fill": check_color(background)})
    if layout != "name" and symbol:
        # 중첩 svg 대신 g와 transform(Qt, 일부 편집기와 방송 플랫폼 변환기가 중첩 svg를 그리지 않음)
        parsed = ET.fromstring(sanitize_svg(symbol))
        min_x, min_y, box_w, box_h = view_box(parsed)
        scale = side / max(box_w, box_h)
        offset_x = symbol_at[0] + (side - box_w * scale) / 2 - min_x * scale
        offset_y = symbol_at[1] + (side - box_h * scale) / 2 - min_y * scale
        group = ET.SubElement(root, f"{{{SVG_NS}}}g", {"transform": f"translate({_number(offset_x)} {_number(offset_y)}) scale({scale:.6f})"})
        for key, value in parsed.attrib.items():  # 맨 바깥 SVG의 채우기, 선 설정 유지
            if _local(key) not in ("viewBox", "width", "height", "x", "y", "version", "preserveAspectRatio", "style", "class"):
                group.set(key, value)
        group.extend(list(parsed))
    if shape:
        ET.SubElement(root, f"{{{SVG_NS}}}path", {"d": shape.path, "fill": color,
                                                   "transform": f"translate({_number(text_at[0])} {_number(text_at[1])})"})
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


# --- 생성형 AI 요청 ------------------------------------------------------------------------


def _mask(text: str, key: str) -> str:
    return text.replace(key, "****") if key else text


def describe_http(provider: Provider, status: int, body: str, key: str) -> str:
    """서비스의 오류 응답을 한국어 안내로(키는 가림)."""
    message = body
    try:
        data = json.loads(body)
        error = data.get("error") if isinstance(data, dict) else None
        message = str(error.get("message") if isinstance(error, dict) else error or data.get("message") or body) if isinstance(data, dict) else body
    except ValueError:
        pass
    message = _mask(message, key)[:200]
    lowered = message.lower()
    if status == 401:
        return f"{provider.name} API 키가 올바르지 않음: 키를 다시 저장({provider.key_hint})"
    if status == 403 and "verif" in lowered:
        return "OpenAI 조직 인증 필요: platform.openai.com 설정의 Organization verification을 마친 뒤 다시 시도"
    if status == 403:
        return f"{provider.name}에서 이 요청을 허용하지 않음: {message}"
    if status == 429:
        return f"{provider.name} 요청 한도 초과 또는 잔액 부족: 잠시 뒤 다시 시도하거나 결제 상태 확인"
    if status == 400 and any(word in lowered for word in ("safety", "moderation", "content policy", "content_policy", "rejected")):
        return "설명이 서비스의 안전 정책에 걸림: 설명을 바꿔 다시 시도"
    if status >= 500:
        return f"{provider.name} 서비스 오류({status}): 잠시 뒤 다시 시도"
    return f"{provider.name} 요청 오류({status}): {message}"


Opener = Callable[..., Any]
ClaudeClient = Callable[[str], Any]  # API 키를 받아 anthropic.Anthropic과 같은 모양의 객체(시험에서 바꿔 끼움)


def _claude_symbol(key: str, prompt: str, quality: str, *, client: ClaudeClient | None = None, timeout: float = 240.0) -> tuple[str, str]:
    """Claude가 SVG 코드를 작성. (정리 전 SVG, 실제로 응답한 모델).

    응답을 조금씩 받는다(스트리밍). 끝까지 기다렸다 받으면 몇 분 걸리는 고품질 생성이 대기 시간 제한에 걸리므로,
    ``timeout`` 은 전체 시간이 아니라 응답 조각 사이의 최대 공백(서버가 생각하는 동안에도 연결 유지 신호를 보냄).
    """
    provider = PROVIDERS["claude"]
    try:
        import anthropic
    except ImportError as error:
        raise LogoError('Claude 사용에는 anthropic 패키지 필요: pip install "debutkit[logo]"') from error
    made = (client or (lambda value: anthropic.Anthropic(api_key=value, timeout=timeout, max_retries=2)))(key)
    try:
        with made.beta.messages.stream(
                model=CLAUDE_MODEL, max_tokens=16000,
                # 안전 판단으로 거절되면 서버가 다른 모델로 같은 요청을 이어서 처리(fallback)
                betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                output_config={"effort": "low" if quality == "fast" else "high"},
                system=CLAUDE_SYSTEM, messages=[{"role": "user", "content": prompt}]) as stream:
            response = stream.get_final_message()
    except anthropic.AuthenticationError as error:
        raise LogoError(describe_http(provider, 401, str(error.message), key)) from None
    except anthropic.PermissionDeniedError as error:
        raise LogoError(describe_http(provider, 403, str(error.message), key)) from None
    except anthropic.RateLimitError as error:
        raise LogoError(describe_http(provider, 429, str(error.message), key)) from None
    except anthropic.BadRequestError as error:
        raise LogoError(describe_http(provider, 400, str(error.message), key)) from None
    except anthropic.APIStatusError as error:  # 529(혼잡)와 5xx 등
        raise LogoError(describe_http(provider, error.status_code, str(error.message), key)) from None
    except anthropic.APITimeoutError:  # 연결 실패의 한 종류라 먼저 구분
        raise LogoError(f"Claude 응답이 {timeout:.0f}초 넘게 멈춤: 잠시 뒤 다시 시도") from None
    except anthropic.APIConnectionError as error:  # 연결 실패, 받는 도중 끊김
        raise LogoError(f"Claude에 연결하지 못함: 인터넷 연결 확인({_mask(str(error), key)})") from None
    if response.stop_reason == "refusal":
        raise LogoError("설명이 Claude의 사용 정책에 걸림: 설명을 바꿔 다시 시도")
    text = "".join(block.text for block in response.content if block.type == "text")
    found = re.search(r"<svg\b.*?</svg>", text, re.IGNORECASE | re.DOTALL)
    if found is None:
        cut = " (응답이 길어 잘림: 더 단순한 설명으로 다시 시도)" if response.stop_reason == "max_tokens" else ""
        raise LogoError(f"Claude 응답에 SVG가 없음{cut}")
    return found.group(0), str(getattr(response, "model", CLAUDE_MODEL) or CLAUDE_MODEL)


def request_symbol(provider_id: str, key: str, prompt: str, quality: str, colors: list[str], *, opener: Opener = urllib.request.urlopen,
                   timeout: float = 240.0, claude: ClaudeClient | None = None) -> tuple[str, str]:
    """심볼 SVG 1개 생성. (정리 전 원본 SVG, 응답한 모델). 실패하면 LogoError."""
    if provider_id == "claude":
        return _claude_symbol(key, prompt, quality, client=claude, timeout=timeout)
    provider = PROVIDERS[provider_id]
    model = provider.models[quality]
    if provider_id == "openai":
        body: dict[str, Any] = {"model": model, "prompt": prompt, "output_format": "svg", "n": 1, "size": "1024x1024",
                                "quality": "medium" if quality == "fast" else "high"}
    else:
        body = {"model": model, "prompt": prompt, "size": "1:1", "response_format": "b64_json"}
        if colors:
            body["controls"] = {"colors": [{"rgb": [int(color[index:index + 2], 16) for index in (1, 3, 5)]} for color in colors]}
    request = urllib.request.Request(provider.endpoint, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                              "User-Agent": f"debutkit/{__version__}"})
    try:
        with opener(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise LogoError(describe_http(provider, error.code, error.read(4000).decode("utf-8", "replace"), key)) from None
    except (urllib.error.URLError, OSError) as error:
        raise LogoError(f"{provider.name}에 연결하지 못함: 인터넷 연결 확인({_mask(str(error), key)})") from None
    except ValueError:
        raise LogoError(f"{provider.name} 응답을 읽지 못함") from None
    try:
        encoded = data["data"][0]["b64_json"]
        return base64.b64decode(encoded).decode("utf-8"), model
    except (KeyError, IndexError, TypeError, ValueError, UnicodeDecodeError):
        raise LogoError(f"{provider.name} 응답에 SVG가 없음") from None


# --- 작업 공간(오버레이 서버, 명령줄 공용) ------------------------------------------------------


def logos_dir() -> Path:
    """생성한 심볼과 생성 기록(비용이 든 결과를 잃지 않도록 저장)."""
    return settings.settings_path().parent / "logos"


class LogoStudio:
    """API 키 보관, 심볼 생성 기록, 로고 조합."""

    def __init__(self, *, keys: KeyBox | None = None, folder: Path | None = None, opener: Opener = urllib.request.urlopen,
                 claude: ClaudeClient | None = None, clock: Callable[[], float] = time.time) -> None:
        base = settings.settings_path().parent
        self.keys = keys or KeyBox(base / "logo-keys.json", b"debutkit-logo-key", "debutkit-logo")
        self.folder = folder or logos_dir()
        self._opener = opener
        self._claude = claude
        self._clock = clock
        self._lock = threading.Lock()
        self._symbols: dict[str, dict[str, Any]] = {}
        self._busy = False
        self._load_saved()

    def _load_saved(self) -> None:
        log = self.folder / "log.jsonl"
        try:
            lines = log.read_text(encoding="utf-8").splitlines()[-KEEP:]
        except OSError:
            return
        for line in lines:
            try:
                record = json.loads(line)
                svg = (self.folder / f"{record['id']}.svg").read_text(encoding="utf-8")
                self._symbols[record["id"]] = {**record, "svg": sanitize_svg(svg)}
            except (ValueError, KeyError, OSError, TypeError):
                continue

    def set_key(self, provider: Any, key: Any) -> dict[str, Any]:
        provider_id = check_choice(provider, PROVIDERS, "AI 서비스")
        if key is None:
            self.keys.clear(provider_id)
        else:
            self.keys.save(provider_id, check_key(key))
        return self.status()

    def generate(self, provider: Any, quality: Any, description: Any, style: Any, colors: Any) -> dict[str, Any]:
        """사용자 키로 심볼 생성(요금 발생, 최대 몇 분). 결과는 정리해서 기록에 남긴다."""
        provider_id = check_choice(provider, PROVIDERS, "AI 서비스")
        quality_id = check_choice(quality or "fast", QUALITIES, "품질")
        style_id = check_choice(style or "cute", STYLES, "느낌")
        text = check_description(description)
        palette = check_colors(colors)
        key = self.keys.load(provider_id)
        if not key:
            raise LogoError(f"{PROVIDERS[provider_id].name} API 키를 먼저 저장({PROVIDERS[provider_id].key_hint})")
        with self._lock:
            if self._busy:
                raise LogoError("이미 만드는 중: 끝난 뒤 다시 시도")
            self._busy = True
        try:
            raw, model = request_symbol(provider_id, key, build_prompt(text, style_id, palette), quality_id, palette, opener=self._opener,
                                        claude=self._claude)
            svg = sanitize_svg(raw)
        finally:
            with self._lock:
                self._busy = False
        record = {"id": random_ids.token_hex(6), "provider": PROVIDERS[provider_id].name, "model": model,
                  "description": text, "style": style_id, "colors": palette, "time": int(self._clock())}
        with self._lock:
            self._symbols[record["id"]] = {**record, "svg": svg}
            while len(self._symbols) > KEEP:
                self._symbols.pop(next(iter(self._symbols)))
        try:  # 요금이 든 결과는 파일로도 보관(실패해도 이번 화면에서는 사용 가능)
            self.folder.mkdir(parents=True, exist_ok=True)
            (self.folder / f"{record['id']}.svg").write_text(svg, encoding="utf-8")
            with (self.folder / "log.jsonl").open("a", encoding="utf-8") as log:
                log.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass
        return dict(record)

    def symbol(self, symbol_id: str) -> dict[str, Any] | None:
        with self._lock:
            found = self._symbols.get(symbol_id)
            return dict(found) if found else None

    def make(self, data: dict[str, Any]) -> str:
        """요청 내용으로 로고 SVG. symbol: {"template", "primary", "accent"} 또는 {"id"}."""
        layout = check_choice(data.get("layout") or "horizontal", LAYOUTS, "배치")
        chosen = data.get("symbol") if isinstance(data.get("symbol"), dict) else {}
        svg: str | None = None
        source: dict[str, str] | None = None
        if layout != "name":
            if chosen.get("id"):
                found = self.symbol(str(chosen["id"]))
                if found is None:
                    raise LogoError("고른 AI 심볼을 찾지 못함: 다시 만들기")
                svg, source = found["svg"], {"provider": found["provider"], "model": found["model"]}
            else:
                svg = template_svg(chosen.get("template") or "star", chosen.get("primary") or "#FF4F8B", chosen.get("accent") or "#1E2327")
        background = data.get("background") or None
        return compose(svg, data.get("name") or "", font=check_choice(data.get("font") or "pretendard", FONTS, "글꼴"), layout=layout,
                       text_color=data.get("text_color") or "#1E2327", background=background, source=source)

    def status(self) -> dict[str, Any]:
        with self._lock:
            recent = [{key: value for key, value in record.items() if key != "svg"} for record in reversed(list(self._symbols.values()))]
            busy = self._busy
        return {
            "providers": {key: {"name": item.name, "models": item.models, "price": item.price, "terms": item.terms, "key_hint": item.key_hint,
                                "key_saved": self.keys.has(key)} for key, item in PROVIDERS.items()},
            "key_storage": self.keys.mode, "qualities": QUALITIES, "styles": {key: value[0] for key, value in STYLES.items()},
            "layouts": LAYOUTS, "fonts": {key: item.name for key, item in FONTS.items()},
            "templates": {key: value[0] for key, value in TEMPLATES.items()}, "recent": recent, "busy": busy,
        }
