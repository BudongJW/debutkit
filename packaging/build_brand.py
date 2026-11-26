"""debutkit 브랜드 파일 만들기(assets/brand)와 프로그램 아이콘.

    pip install pillow fonttools brotli
    python packaging/build_brand.py

- 심볼: 메인 캐릭터 데비(데뷔 준비생)의 상반신이 원형 배지 위로 나온 그림. 원본은 assets/brand/mascot/source/debi_1024.png
  (FLUX.1 schnell, Apache-2.0로 만든 시안, 배경 제거. 생성 기록은 assets/brand/mascot/draft/manifest.json)
- 작은 심볼(32px 이하, 파비콘): 마스코트 마이(리본 마이크). 이 파일에서 도형으로 직접 그린 벡터. 마이 전체 그림은 symbol/mai_*
- 워드마크: 함께 배포한 Pretendard Bold(SIL OFL)의 윤곽선. "kit"는 라벤더, i의 점 자리는 노란 별
- 만드는 것: symbol(데비 배지, 마이), wordmark, lockup(가로, 세로), app-icon, favicon(SVG, PNG, ICO), board.png(컨셉 보드),
  Windows 실행 파일 아이콘(app-icon/debutkit.ico), 설정 마법사 창 아이콘(src/debutkit/gui/icon.png), 오버레이 탭 아이콘(favicon.svg)
- PNG는 헤드리스 Chrome 또는 Edge로 그린다(packaging/build_screens.py의 촬영 함수, 투명 배경)

만든 파일은 저장소에 함께 넣는다(빌드 때 Pillow 불필요).
"""

from __future__ import annotations

import base64
import io
import math
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "assets" / "brand"
ICO = BRAND / "app-icon" / "debutkit.ico"
GUI_ICON = ROOT / "src" / "debutkit" / "gui" / "icon.png"
OVERLAY_FAVICON = ROOT / "src" / "debutkit" / "overlay" / "static" / "favicon.svg"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "packaging"))

#: 브랜드 색
INK = "#231B3D"
LAVENDER = "#A98BF7"
LAVENDER_DEEP = "#7E62DE"
LAVENDER_TEXT = "#5B3FC4"  # 밝은 배경 위 글자(흰 배경 대비 7:1 안팎)
LAVENDER_LIGHT = "#C2ADFF"  # 어두운 배경 위 글자
SILVER = "#F1EEFA"
SILVER_SHADE = "#D6D0EC"
GRILLE = "#4A3C86"
YELLOW = "#FFC93C"
MINT = "#45D6B8"
CORAL = "#FF6F6F"
CHEEK = "#FF97A6"
CREAM = "#FAF7F5"
SVG_NS = "http://www.w3.org/2000/svg"
DEBI = BRAND / "mascot" / "source" / "debi_1024.png"


# --------------------------------------------------------------------------- 메인 캐릭터 데비(그림)


def debi_bust():
    """데비의 머리부터 허리까지(투명 배경 RGBA)."""
    from PIL import Image

    image = Image.open(DEBI).convert("RGBA")
    left, top, right, bottom = image.getbbox()
    return image.crop((left, top, right, top + int((bottom - top) * 0.6)))


def badge(size: int = 1024, *, ring: bool = False):
    """원형 배지 위로 데비 상반신이 나온 심볼(투명 배경 PNG용 RGBA). ``ring`` 은 바깥 흰 테두리(어두운 배경용)."""
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    diameter = int(size * 0.8)
    cx, cy = size // 2, size - diameter // 2 - int(size * 0.04)
    circle = (cx - diameter // 2, cy - diameter // 2, cx + diameter // 2, cy + diameter // 2)
    draw = ImageDraw.Draw(canvas)
    if ring:
        pad = int(size * 0.025)
        draw.ellipse((circle[0] - pad, circle[1] - pad, circle[2] + pad, circle[3] + pad), fill="#FFFFFF")
    draw.ellipse(circle, fill=LAVENDER, outline=INK, width=max(2, size // 64))
    bust = debi_bust()
    scale = diameter * 1.02 / bust.width
    bust = bust.resize((round(bust.width * scale), round(bust.height * scale)), Image.Resampling.LANCZOS)
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    layer.alpha_composite(bust, (cx - bust.width // 2, circle[3] - bust.height))
    # 원 아래쪽 밖은 지우고 위쪽(머리)은 원 밖으로 나오게
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse(circle, fill=255)
    mask_draw.rectangle((0, 0, size, cy), fill=255)
    layer.putalpha(Image.composite(layer.getchannel("A"), Image.new("L", (size, size), 0), mask))
    canvas.alpha_composite(layer)
    if ring:  # 원 밖으로 나온 머리에도 흰 테두리
        alpha = canvas.getchannel("A")
        from PIL import ImageFilter

        halo = alpha.filter(ImageFilter.MaxFilter(int(size * 0.03) | 1))
        white = Image.new("RGBA", (size, size), (255, 255, 255, 255))
        white.putalpha(halo)
        white.alpha_composite(canvas)
        canvas = white
    return canvas


def app_icon_png(size: int = 1024, *, dark: bool = True, rounded: bool = False):
    from PIL import Image, ImageDraw

    back = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=int(size * 0.22) if rounded else 0, fill=255)
    fill = Image.new("RGBA", (size, size), INK if dark else CREAM)
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    for step in range(40, 0, -1):  # 가운데 라벤더 빛
        radius = int(size * 0.5 * step / 40)
        alpha = int((140 if dark else 90) * (1 - step / 40) ** 1.4)
        glow_draw.ellipse((size // 2 - radius, int(size * 0.45) - radius, size // 2 + radius, int(size * 0.45) + radius),
                          fill=(126, 98, 222, alpha) if dark else (169, 139, 247, alpha))
    fill.alpha_composite(glow)
    back.paste(fill, (0, 0), mask)
    art = badge(int(size * 0.86), ring=dark)
    back.alpha_composite(art, ((size - art.width) // 2, int(size * 0.07)))
    return back


def png_bytes(image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def embed(image, width: float, height: float, x: float = 0, y: float = 0) -> str:
    """그림(PNG)을 SVG 안에 넣는다(사이트, 문서가 SVG 하나로 쓰게)."""
    data = base64.b64encode(png_bytes(image)).decode()
    return f'<image x="{x}" y="{y}" width="{width}" height="{height}" href="data:image/png;base64,{data}"/>'


# --------------------------------------------------------------------------- 심볼(마이)


def _arc(cx: float, cy: float, r: float, side: int, spread: float = 50) -> str:
    """음파 호: 가운데(cx, cy)에서 바깥쪽(side: -1 왼쪽, 1 오른쪽)으로 ±spread도."""
    a = math.radians(spread)
    x, top, bottom = cx + side * r * math.cos(a), cy - r * math.sin(a), cy + r * math.sin(a)
    return f"M{x:.1f} {top:.1f} A{r} {r} 0 0 {1 if side > 0 else 0} {x:.1f} {bottom:.1f}"


def symbol_parts(*, small: bool = False, sticker: bool = False, uid: str = "mai") -> str:
    """심볼의 SVG 내용(viewBox 0 0 512 512). ``sticker`` 는 바깥 흰 테두리(어두운 배경용), ``small`` 은 32px 이하용 단순화."""
    s = 30 if small else 16
    left, right, top, bottom = (126, 386, 36, 476) if small else (166, 346, 70, 392)
    width = right - left
    radius = width / 2
    body = f"M{left} {top + radius} A{radius} {radius} 0 0 1 {right} {top + radius} L{right} {bottom - radius} A{radius} {radius} 0 0 1 {left} {bottom - radius} Z"
    parts = [f'<defs><clipPath id="{uid}-body"><path d="{body}"/></clipPath></defs>']
    waves = [] if small else [_arc(256 + side * 72, 196, r, side) for side in (-1, 1) for r in (58, 98)]
    if sticker:
        parts += [f'<path d="{arc}" fill="none" stroke="#FFFFFF" stroke-width="{s * 1.2 + 22:.1f}" stroke-linecap="round"/>' for arc in waves]
        if not small:
            parts += ['<rect x="234" y="384" width="44" height="52" rx="10" fill="#FFFFFF" stroke="#FFFFFF" stroke-width="38"/>',
                      '<rect x="172" y="430" width="168" height="40" rx="20" fill="#FFFFFF" stroke="#FFFFFF" stroke-width="38"/>',
                      '<circle cx="256" cy="66" r="24" fill="#FFFFFF" stroke="#FFFFFF" stroke-width="36"/>']
        parts.append(f'<path d="{body}" fill="#FFFFFF" stroke="#FFFFFF" stroke-width="{s + 22}" stroke-linejoin="round"/>')
    parts += [f'<path d="{arc}" fill="none" stroke="{MINT}" stroke-width="{s * 1.2:.1f}" stroke-linecap="round"/>' for arc in waves]
    if not small:
        parts += [f'<rect x="234" y="384" width="44" height="52" rx="10" fill="{LAVENDER_DEEP}" stroke="{INK}" stroke-width="{s}"/>',
                  f'<rect x="172" y="430" width="168" height="40" rx="20" fill="{LAVENDER}" stroke="{INK}" stroke-width="{s}"/>']
    parts.append(f'<path d="{body}" fill="{LAVENDER}"/>')
    inner = [f'<rect x="{left - 4}" y="{bottom - radius * 0.9:.1f}" width="{width + 8}" height="{radius:.1f}" fill="{LAVENDER_DEEP}" opacity="0.35"/>']
    # 위쪽 그릴(은색 막대 2개)과 그 아래 얼굴판(줄 없는 은색). 얼굴은 얼굴판 안에만 그려 줄, 외곽선과 겹치지 않게
    g_top = top + (40 if small else 30)
    face_top = top + (bottom - top) * 0.27
    face_bottom = top + (bottom - top) * 0.62
    step = (face_top - g_top) / 2
    inner.append(f'<rect x="{left - 4}" y="{g_top - step * 0.1:.1f}" width="{width + 8}" height="{face_top - g_top + step * 0.1:.1f}" fill="{GRILLE}"/>')
    for i in range(2):  # 은색 막대 2개
        y = g_top + i * step
        inner.append(f'<rect x="{left - 4}" y="{y + step * 0.14:.1f}" width="{width + 8}" height="{step * 0.66:.1f}" fill="{SILVER}"/>')
        inner.append(f'<rect x="{left - 4}" y="{y + step * 0.6:.1f}" width="{width + 8}" height="{step * 0.2:.1f}" fill="{SILVER_SHADE}"/>')
    inner.append(f'<rect x="{left - 4}" y="{face_top:.1f}" width="{width + 8}" height="{face_bottom - face_top:.1f}" fill="{SILVER}"/>')
    band_y, band_h = face_bottom + (bottom - face_bottom) * 0.18, (bottom - face_bottom) * 0.26
    inner.append(f'<rect x="{left - 4}" y="{band_y:.1f}" width="{width + 8}" height="{band_h:.1f}" fill="{YELLOW}"/>')
    for y in (face_top, face_bottom, band_y, band_y + band_h):
        inner.append(f'<line x1="{left - 4}" y1="{y:.1f}" x2="{right + 4}" y2="{y:.1f}" stroke="{INK}" stroke-width="{s * 0.6:.1f}"/>')
    parts.append(f'<g clip-path="url(#{uid}-body)">{"".join(inner)}</g>')
    # 얼굴: 얼굴판 가운데. 눈, 볼, 입 모두 얼굴판 안쪽 여백 안
    panel = face_bottom - face_top
    face_y = face_top + panel * 0.4
    eye_dx, eye_r = width * 0.19, min(width * 0.06, panel * 0.11)
    for side in (-1, 1):
        x = 256 + side * eye_dx
        parts.append(f'<circle cx="{x:.1f}" cy="{face_y:.1f}" r="{eye_r:.1f}" fill="{INK}"/>'
                     f'<circle cx="{x + eye_r * 0.38:.1f}" cy="{face_y - eye_r * 0.38:.1f}" r="{eye_r * 0.34:.1f}" fill="#FFFFFF"/>'
                     f'<ellipse cx="{256 + side * eye_dx * 1.55:.1f}" cy="{face_y + eye_r * 1.55:.1f}" rx="{eye_r * 0.95:.1f}" ry="{eye_r * 0.55:.1f}" fill="{CHEEK}"/>')
    mouth = eye_r * 1.1
    mouth_top = face_y + eye_r * 1.2
    mouth_low = min(face_y + eye_r * 2.6, face_bottom - panel * 0.16)
    parts.append(f'<path d="M{256 - mouth:.1f} {mouth_top:.1f} Q256 {mouth_low + (mouth_low - mouth_top) * 0.6:.1f} {256 + mouth:.1f} {mouth_top:.1f}" '
                 f'fill="none" stroke="{INK}" stroke-width="{s * 0.6:.1f}" stroke-linecap="round"/>')
    parts.append(f'<path d="{body}" fill="none" stroke="{INK}" stroke-width="{s}" stroke-linejoin="round"/>')
    if not small:
        parts.append(f'<circle cx="256" cy="{top - 4}" r="22" fill="{CORAL}" stroke="{INK}" stroke-width="{s * 0.8:.1f}"/>'
                     f'<circle cx="249" cy="{top - 11}" r="6" fill="#FFFFFF" opacity="0.9"/>')
    return "".join(parts)


def svg(content: str, view: str, title: str = "debutkit") -> str:
    return f'<svg xmlns="{SVG_NS}" viewBox="{view}" role="img" aria-label="{title}"><title>{title}</title>{content}</svg>\n'


def symbol(*, small: bool = False, sticker: bool = False) -> str:
    return svg(symbol_parts(small=small, sticker=sticker), "0 0 512 512")


# --------------------------------------------------------------------------- 워드마크


def _star(cx: float, cy: float, r: float, inner: float = 0.48) -> str:
    points = []
    for i in range(10):
        radius = r if i % 2 == 0 else r * inner
        angle = -math.pi / 2 + i * math.pi / 5
        points.append(f"{cx + radius * math.cos(angle):.2f},{cy + radius * math.sin(angle):.2f}")
    return "M" + " L".join(points) + " Z"


def wordmark_parts(*, dark: bool = False, size: float = 100.0, tracking: float = -2.0) -> tuple[str, tuple[float, float, float, float]]:
    """워드마크 내용과 (왼쪽, 위, 너비, 높이). 기준선 y=0."""
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.recordingPen import DecomposingRecordingPen
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen

    from debutkit import logo

    font = logo._font("pretendard")
    cmap, glyphs, metrics = font.getBestCmap(), font.getGlyphSet(), font["hmtx"]
    scale = size / font["head"].unitsPerEm
    paths = {"debut": SVGPathPen(glyphs), "kit": SVGPathPen(glyphs)}
    bounds = BoundsPen(glyphs)
    x, dot = 0.0, (0.0, 0.0)
    for index, ch in enumerate("debutkit"):
        name = cmap[ord(ch)]
        transform = (scale, 0, 0, -scale, x * scale, 0)
        pen = TransformPen(paths["debut" if index < 5 else "kit"], transform)
        glyphs[name].draw(TransformPen(bounds, transform))
        if ch == "i":  # 점은 빼고 별로
            recording = DecomposingRecordingPen(glyphs)
            glyphs[name].draw(recording)
            contours, current = [], []
            for op, args in recording.value:
                current.append((op, args))
                if op in ("closePath", "endPath"):
                    contours.append(current)
                    current = []
            contours.sort(key=lambda contour: max((point[1] for _, args in contour for point in args), default=0))
            for contour in contours[:-1]:
                for op, args in contour:
                    getattr(pen, op)(*args)
            xs = [point[0] for _, args in contours[-1] for point in args]
            ys = [point[1] for _, args in contours[-1] for point in args]
            dot = (sum(xs) / len(xs) * scale + x * scale, -sum(ys) / len(ys) * scale)
        else:
            glyphs[name].draw(pen)
        x += metrics[name][0] + tracking / scale
    left, top, right, bottom = bounds.bounds
    star = _star(dot[0], dot[1] - size * 0.03, size * 0.15)
    content = (f'<path d="{paths["debut"].getCommands()}" fill="{"#FFFFFF" if dark else INK}"/>'
               f'<path d="{paths["kit"].getCommands()}" fill="{LAVENDER_LIGHT if dark else LAVENDER_TEXT}"/>'
               f'<path d="{star}" fill="{YELLOW}" stroke="{INK}" stroke-width="{size * 0.025:.2f}" stroke-linejoin="round"/>')
    top = min(top, dot[1] - size * 0.2)
    return content, (left, top, right - left, bottom - top)


def wordmark(*, dark: bool = False) -> str:
    content, (left, top, width, height) = wordmark_parts(dark=dark)
    pad = 8
    return svg(content, f"{left - pad:.1f} {top - pad:.1f} {width + 2 * pad:.1f} {height + 2 * pad:.1f}")


# --------------------------------------------------------------------------- 조합


def lockup(*, vertical: bool = False, dark: bool = False) -> str:
    """심볼과 워드마크. 가로형: 심볼 높이에 맞춘 글자, 세로형: 심볼 아래 글자."""
    content, (left, top, width, height) = wordmark_parts(dark=dark)
    picture = badge(512, ring=dark)
    if vertical:
        scale = 360 / width
        total_w, sym = 400, 260
        text_y = sym + 30
        inner = (embed(picture, sym, sym, (total_w - sym) / 2, 0) +
                 f'<g transform="translate({(total_w - width * scale) / 2 - left * scale:.1f} {text_y - top * scale:.1f}) scale({scale:.4f})">{content}</g>')
        return svg(inner, f"0 0 {total_w} {text_y + height * scale + 10:.1f}")
    sym = 200
    scale = sym * 0.5 / height
    text_x = sym + 20
    inner = (embed(picture, sym, sym) +
             f'<g transform="translate({text_x - left * scale:.1f} {(sym - height * scale) / 2 - top * scale:.1f}) scale({scale:.4f})">{content}</g>')
    return svg(inner, f"0 0 {text_x + width * scale + 12:.1f} {sym}")


def app_icon(*, dark: bool = True, rounded: bool = False) -> str:
    return svg(embed(app_icon_png(512, dark=dark, rounded=rounded), 1024, 1024), "0 0 1024 1024")


def mai_icon(*, dark: bool = True, rounded: bool = False) -> str:
    """마이 앱 아이콘(벡터, 보조)."""
    back = INK if dark else CREAM
    glow = LAVENDER_DEEP if dark else LAVENDER
    radius = 224 if rounded else 0
    content = (f'<defs><radialGradient id="glow" cx="0.5" cy="0.42" r="0.6"><stop offset="0" stop-color="{glow}" stop-opacity="{0.55 if dark else 0.35}"/>'
               f'<stop offset="1" stop-color="{glow}" stop-opacity="0"/></radialGradient></defs>'
               f'<rect width="1024" height="1024" rx="{radius}" fill="{back}"/><rect width="1024" height="1024" rx="{radius}" fill="url(#glow)"/>'
               f'<svg x="112" y="112" width="800" height="800" viewBox="0 0 512 512">{symbol_parts(sticker=dark, uid="icon")}</svg>')
    return svg(content, "0 0 1024 1024")


# --------------------------------------------------------------------------- PNG, 아이콘


def render(files: dict[Path, tuple[str, tuple[int, int], str]]) -> None:
    """SVG를 PNG로(투명 배경): {PNG 경로: (SVG, (너비, 높이), 배경색 또는 "")}."""
    import build_screens

    browsers = build_screens.find_browsers()
    with tempfile.TemporaryDirectory() as folder:
        for index, (out, (markup, (width, height), background)) in enumerate(files.items()):
            source = Path(folder) / f"{index}.svg"
            source.write_text(markup, encoding="utf-8")
            page = Path(folder) / f"{index}.html"
            page.write_text(f'<!doctype html><html><body style="margin:0;background:{background or "transparent"}">'
                            f'<img src="{source.name}" style="display:block;width:{width}px;height:{height}px"></body></html>', encoding="utf-8")
            build_screens.capture(browsers, page.as_uri(), out, (width, height), wait=1.5, transparent=not background)


def _size(markup: str, width: int) -> tuple[int, int]:
    view = markup.split('viewBox="', 1)[1].split('"', 1)[0].split()
    return width, round(width * float(view[3]) / float(view[2]))


def board() -> str:
    """컨셉 보드(2000x1230): 심볼과 워드마크, 가로형 로고, 앱 아이콘, 탭 아이콘, 색, 캐스트."""
    swatches = "".join(f'<div class="sw"><i style="background:{color}"></i><b>{name}</b><span>{color}</span></div>'
                       for name, color in (("Lavender", LAVENDER), ("Lavender Text", LAVENDER_TEXT), ("Ink", INK), ("Mint", MINT), ("Yellow", YELLOW),
                                           ("Coral", CORAL), ("Cream", CREAM)))
    cast = "".join(f'<figure><img src="{"../symbol/mai_dark-bg.svg" if key == "mai" else f"../mascot/draft/{key}.png"}"><figcaption>{name}</figcaption></figure>'
                   for key, name in (("mai", "마이"), ("cue", "큐"), ("bubbles", "뽀글이들"), ("capsule", "캡슐"), ("cuckoo", "뻐꾹"), ("dessaengi", "데생이")))
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
body {{ margin: 0; width: 2000px; height: 1230px; display: grid; grid-template-columns: 1150px 1fr; font-family: Pretendard, "Malgun Gothic", sans-serif; }}
.left {{ background: {INK}; color: #fff; display: grid; place-items: center; position: relative; }}
.left .tag {{ position: absolute; left: 60px; top: 50px; font-size: 30px; color: #cfc6ea; }}
.hero {{ display: grid; justify-items: center; gap: 36px; }}
.hero img.sym {{ width: 560px; margin-bottom: -40px; }} .hero img.word {{ width: 560px; }}
.hero p {{ margin: 0; font-size: 40px; color: #d9d1f2; }}
.right {{ background: #17122b; padding: 56px 60px; display: grid; gap: 34px; align-content: start; color: #cfc6ea; font-size: 24px; }}
.card {{ background: {CREAM}; border-radius: 40px; height: 250px; display: grid; place-items: center; }} .card img {{ width: 600px; }}
.icons {{ display: flex; gap: 28px; align-items: end; }} .icons img {{ border-radius: 44px; }}
.tabs {{ display: flex; gap: 14px; }} .tab {{ flex: 1; display: flex; gap: 14px; align-items: center; padding: 18px 24px; border-radius: 14px 14px 0 0; font-size: 26px; }}
.tab img {{ width: 30px; }}
.sws {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 10px; }} .sw {{ display: grid; gap: 4px; font-size: 17px; }} .sw i {{ height: 64px; border-radius: 12px; }}
.sw span {{ color: #a99fc8; }} .cast {{ display: flex; gap: 6px; }} figure {{ margin: 0; text-align: center; font-size: 18px; }} figure img {{ width: 118px; }}
</style></head><body>
<div class="left"><div class="tag">debutkit 메인 캐릭터 데비(데뷔 준비생)</div>
<div class="hero"><img class="sym" src="../mascot/source/debi_1024.png"><img class="word" src="../wordmark/wordmark_dark-bg.svg"><p>첫 방송 준비를 함께</p></div></div>
<div class="right"><div class="card"><img src="../lockup/horizontal_light-bg.svg"></div>
<div>앱 아이콘(데비), 파비콘과 32px 이하(마이)</div>
<div class="icons"><img src="../app-icon/app-icon_dark_rounded.svg" width="190"><img src="../app-icon/app-icon_light.svg" width="140" style="border-radius:32px">
<img src="../symbol/mai_dark-bg.svg" width="110"><img src="../favicon/favicon.svg" width="40"><img src="../favicon/favicon.svg" width="20"></div>
<div class="tabs"><div class="tab" style="background:#2b2445;color:#fff"><img src="../favicon/favicon.svg">debutkit 시작하기</div>
<div class="tab" style="background:#efeaf7;color:{INK}"><img src="../favicon/favicon.svg">debutkit 시작하기</div></div>
<div class="sws">{swatches}</div><div class="cast">{cast}</div></div></body></html>"""


def build() -> list[Path]:
    from PIL import Image

    out = []
    # 그림으로 만드는 것(데비): PNG는 바로, SVG는 PNG를 넣어서
    pictures = {"symbol/symbol_light-bg": badge(1024), "symbol/symbol_dark-bg": badge(1024, ring=True),
                "app-icon/app-icon_dark": app_icon_png(1024), "app-icon/app-icon_dark_rounded": app_icon_png(1024, rounded=True),
                "app-icon/app-icon_light": app_icon_png(1024, dark=False, rounded=True)}
    for name, image in pictures.items():
        (BRAND / f"{name}.png").parent.mkdir(parents=True, exist_ok=True)
        image.save(BRAND / f"{name}.png", optimize=True)
        small = image.resize((512, 512), Image.Resampling.LANCZOS)
        (BRAND / f"{name}.svg").write_text(svg(embed(small, 1024, 1024), "0 0 1024 1024"), encoding="utf-8")
        out += [BRAND / f"{name}.png", BRAND / f"{name}.svg"]
    # 벡터로 그리는 것(마이, 워드마크, 로고)
    texts = {
        "symbol/symbol-small_light-bg.svg": symbol(small=True), "symbol/symbol-small_dark-bg.svg": symbol(small=True, sticker=True),
        "symbol/mai_light-bg.svg": symbol(), "symbol/mai_dark-bg.svg": symbol(sticker=True),
        "wordmark/wordmark_light-bg.svg": wordmark(), "wordmark/wordmark_dark-bg.svg": wordmark(dark=True),
        "lockup/horizontal_light-bg.svg": lockup(), "lockup/horizontal_dark-bg.svg": lockup(dark=True),
        "lockup/vertical_light-bg.svg": lockup(vertical=True), "lockup/vertical_dark-bg.svg": lockup(vertical=True, dark=True),
        "favicon/favicon.svg": symbol(small=True),
    }
    for name, markup in texts.items():
        path = BRAND / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markup, encoding="utf-8")
        out.append(path)
    pngs = {BRAND / name.replace(".svg", ".png"): (markup, _size(markup, 1024 if name.startswith("symbol") else 1600), "")
            for name, markup in texts.items() if not name.startswith("favicon")}
    pngs[BRAND / "favicon" / "favicon-512.png"] = (texts["favicon/favicon.svg"], (512, 512), "")
    render(pngs)
    favicon = Image.open(BRAND / "favicon" / "favicon-512.png").convert("RGBA")
    for size in (16, 32, 48, 180, 192):
        favicon.resize((size, size), Image.Resampling.LANCZOS).save(BRAND / "favicon" / f"favicon-{size}.png", optimize=True)
    favicon.save(BRAND / "favicon" / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    page = BRAND / "board" / "board.html"
    page.parent.mkdir(exist_ok=True)
    page.write_text(board(), encoding="utf-8")
    import build_screens

    build_screens.capture(build_screens.find_browsers(), page.as_uri(), BRAND / "board.png", (2000, 1230), wait=2.5)
    page.unlink()
    page.parent.rmdir()
    # 프로그램 아이콘: 48px 이상은 데비 앱 아이콘, 32px 이하는 마이(작게 봐도 형태 유지)
    app = Image.open(BRAND / "app-icon" / "app-icon_dark_rounded.png").convert("RGBA")
    frames = [app.resize((size, size), Image.Resampling.LANCZOS) for size in (256, 128, 64, 48)]
    frames += [Image.open(BRAND / "favicon" / f"favicon-{size}.png").convert("RGBA") for size in (32, 16)]
    frames[0].save(ICO, format="ICO", sizes=[frame.size for frame in frames], append_images=frames[1:])
    app.resize((256, 256), Image.Resampling.LANCZOS).save(GUI_ICON, optimize=True)
    shutil.copyfile(BRAND / "favicon" / "favicon.svg", OVERLAY_FAVICON)
    return out + [ICO, GUI_ICON, OVERLAY_FAVICON, BRAND / "board.png"]


def main() -> int:
    for path in build():
        print(f"{path.relative_to(ROOT)}  ({path.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
