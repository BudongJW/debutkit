"""방송 색과 방송 스타일(채널 테마): 모든 방송 화면(채팅, 알림, 추첨, 뽑기판, 후원 벽, 레이스)과 조작 화면이 함께 쓰는 색, 모양, 글꼴.

- ``/theme.css``: 글꼴(함께 배포한 글꼴과 내 글꼴)과 CSS 변수. 화면마다 ``<link rel="stylesheet" href="/theme.css">``
  - 색: ``--dk-primary`` (주 색), ``--dk-primary-light``, ``--dk-primary-deep``, ``--dk-on-primary`` (주 색 위 글자), ``--dk-highlight`` (강조, 희귀),
    ``--dk-ink`` (슬레이트 잉크), ``--dk-paper`` (크림 종이)
  - 방송 스타일(STYLES): ``--dk-surface`` (카드 바탕, background 값), ``--dk-on-surface``, ``--dk-muted``, ``--dk-line``, ``--dk-line-width``,
    ``--dk-line-style``, ``--dk-radius``, ``--dk-shadow``, ``--dk-glow`` (제목 글자 빛), ``--dk-backdrop`` (뒤 흐림), ``--dk-tag-bg``, ``--dk-tag-text``,
    ``--dk-enter-ease``, ``--dk-enter-time`` 와 ``@keyframes dk-enter``. ``--dk-style`` 은 스타일 이름, ``--dk-tone`` 은 바탕의 밝기(dark, light)
  - 글꼴: ``--dk-display`` (제목), ``--dk-text`` (본문). 스타일 기본 글꼴 또는 고른 글꼴
- ``/theme`` 조회, ``POST /theme`` (``{"primary", "highlight"}``, ``{"preset": "lavender"}``, ``{"from_logo": true}``, ``{"style": "neon"}``,
  ``{"display_font": "blackhan", "text_font": "local:나눔고딕"}``). ``POST /theme/font`` 내 글꼴 올리기(``{"name", "data"}``, base64),
  ``POST /theme/font/remove`` (``{"id"}``), ``/theme/font?id=`` 내 글꼴 파일
- ``/live?feeds=theme`` 로 바뀐 값을 받아 화면이 새로고침 없이 바꾼다(theme.js가 /theme.css 를 다시 읽음)
- 설정은 설정 폴더의 ``theme.json``, 내 글꼴 파일은 ``fonts`` 폴더(이름은 debutkit이 정함). 로고 만들기의 로고 색을 가져올 수 있다
"""

from __future__ import annotations

import base64
import binascii
import colorsys
import json
import re
import secrets
from pathlib import Path
from typing import Any, Callable

from .. import settings
from . import feature

DATA = "theme.json"
FONT_FOLDER = "fonts"
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
#: (이름, 주 색, 강조 색). 첫 항목이 기본(debutkit 핑크와 금박)
PRESETS: dict[str, tuple[str, str, str]] = {
    "pink": ("핑크", "#ff4f8b", "#ffd84d"),
    "coral": ("코랄", "#ff6b5a", "#ffd84d"),
    "orange": ("귤", "#ff9b2f", "#fff07a"),
    "lemon": ("레몬", "#f2c200", "#ff4f8b"),
    "mint": ("민트", "#18c29c", "#ffd84d"),
    "green": ("새싹", "#4cb050", "#ffe066"),
    "sky": ("하늘", "#36a3ff", "#ffd84d"),
    "navy": ("남색", "#3557d6", "#ffd84d"),
    "lavender": ("라벤더", "#8b6cff", "#ffd84d"),
    "purple": ("보라", "#a43be0", "#7ef0d0"),
    "rose": ("장미", "#d6336c", "#ffd84d"),
    "slate": ("먹색", "#3a4249", "#ff4f8b"),
}
INK = "#1e2327"
PAPER = "#faf7f5"
#: 방송 화면용 글꼴(함께 배포). 기존 화면(draw.css)과 같은 선언
FONTS = ('@font-face { font-family: "Black Han Sans"; src: url("/vendor/fonts/BlackHanSans-Regular.woff2") format("woff2"); font-display: block; }\n'
         '@font-face { font-family: "Pretendard"; src: url("/vendor/fonts/Pretendard-SemiBold.subset.woff2") format("woff2"); font-weight: 600; font-display: block; }\n'
         '@font-face { font-family: "Pretendard"; src: url("/vendor/fonts/Pretendard-Bold.subset.woff2") format("woff2"); font-weight: 700; font-display: block; }\n')
FALLBACK = '"Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans CJK KR", sans-serif'
#: 고를 수 있는 글꼴: 이름 -> (표시 이름, CSS 글꼴 목록, 설명). 함께 배포한 글꼴과 운영체제 기본 한글 글꼴.
#: 그 밖에 "local:글꼴 이름" (이 PC에 설치한 글꼴), "user:번호" (올린 내 글꼴)
FONT_CHOICES: dict[str, tuple[str, str, str]] = {
    "blackhan": ("Black Han Sans", f'"Black Han Sans", {FALLBACK}', "굵은 제목(함께 배포)"),
    "pretendard": ("Pretendard", f'"Pretendard", {FALLBACK}', "깔끔한 고딕(함께 배포)"),
    "malgun": ("맑은 고딕", f'"Malgun Gothic", {FALLBACK}', "Windows 기본"),
    "gulim": ("굴림", f'"Gulim", "굴림", {FALLBACK}', "Windows 기본"),
    "batang": ("바탕(명조)", '"Batang", "바탕", "AppleMyungjo", "Noto Serif CJK KR", serif', "Windows 기본"),
    "gungsuh": ("궁서", '"Gungsuh", "궁서", "Batang", serif', "Windows 기본"),
    "applesd": ("Apple SD 산돌고딕 Neo", f'"Apple SD Gothic Neo", {FALLBACK}', "macOS 기본"),
}
_LOCAL_NAME = re.compile(r"^[0-9A-Za-z가-힣 _\-.]{1,40}$")
#: 내 글꼴 파일: 첫 바이트 -> (확장자, CSS 형식)
FONT_MAGIC = {b"\x00\x01\x00\x00": ("ttf", "truetype"), b"true": ("ttf", "truetype"), b"OTTO": ("otf", "opentype"), b"wOFF": ("woff", "woff"),
              b"wOF2": ("woff2", "woff2")}
FONT_TYPES = {"ttf": "font/ttf", "otf": "font/otf", "woff": "font/woff", "woff2": "font/woff2"}
MAX_FONT = 20 * 1024 * 1024
MAX_FONTS = 10


class ThemeError(feature.FeatureError):
    pass


def check_color(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not _HEX.match(text):
        raise ThemeError(f"{label}은 #RRGGBB 형식(예: #ff4f8b)")
    return text.lower()


def _rgb(color: str) -> tuple[float, float, float]:
    return tuple(int(color[index:index + 2], 16) / 255 for index in (1, 3, 5))  # type: ignore[return-value]


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, channel)) * 255):02x}" for channel in rgb)


def mix(color: str, other: str, amount: float) -> str:
    """``color`` 에 ``other`` 를 ``amount`` 만큼 섞는다(0이면 그대로)."""
    a, b = _rgb(color), _rgb(other)
    return _hex(tuple(x + (y - x) * amount for x, y in zip(a, b, strict=True)))  # type: ignore[arg-type]


def rgba(color: str, alpha: float) -> str:
    r, g, b = (round(channel * 255) for channel in _rgb(color))
    return f"rgba({r}, {g}, {b}, {alpha:g})"


def luminance(color: str) -> float:
    def linear(channel: float) -> float:
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(channel) for channel in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(first: str, second: str) -> float:
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def on_color(color: str) -> str:
    """색 위에 쓸 글자 색: 잉크와 흰색 중 대비가 큰 쪽."""
    return INK if contrast(color, INK) >= contrast(color, "#ffffff") else "#ffffff"


def deep(color: str) -> str:
    """같은 색상의 진한 색(테두리, 그림자): 밝기를 낮추고 채도를 조금 올린다."""
    h, lightness, s = colorsys.rgb_to_hls(*_rgb(color))
    return _hex(colorsys.hls_to_rgb(h, max(0.18, lightness * 0.62), min(1.0, s * 1.08)))


def palette(primary: str, highlight: str) -> dict[str, str]:
    return {"primary": primary, "primary-light": mix(primary, "#ffffff", 0.55), "primary-deep": deep(primary), "on-primary": on_color(primary),
            "highlight": highlight, "highlight-deep": deep(highlight), "on-highlight": on_color(highlight), "ink": INK, "paper": PAPER}


# --------------------------------------------------------------------------- 방송 스타일

_GRAIN = ("url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'><filter id='n'><feTurbulence "
          "type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0.12 0 0 0 0 0.14 0 0 0 0 0.15 "
          "0 0 0 0.09 0'/></filter><rect width='120' height='120' filter='url(%23n)'/></svg>\")")
_PIXEL_FONT = f'"Galmuri11", "Galmuri9", "DungGeunMo", "Neo둥근모", "Black Han Sans", {FALLBACK}'
_HAND_FONT = f'"Nanum Pen Script", "나눔손글씨 펜", "Gaegu", "Cafe24 Ssurround", "Pretendard", {FALLBACK}'
#: 등장 움직임: 이름 -> (키프레임 내용, 시간, 속도 곡선)
ENTERS: dict[str, tuple[str, str, str]] = {
    "stamp": ("0% { opacity: 0; transform: translateY(-28px) scale(1.04); } 60% { opacity: 1; } 100% { opacity: 1; transform: none; }",
              "0.45s", "cubic-bezier(0.2, 1.5, 0.4, 1)"),
    "float": ("0% { opacity: 0; transform: translateY(18px) scale(0.92); } 70% { opacity: 1; transform: translateY(-4px) scale(1.02); } "
              "100% { opacity: 1; transform: none; }", "0.6s", "ease-out"),
    "flicker": ("0% { opacity: 0; } 12% { opacity: 0.85; } 22% { opacity: 0.15; } 36% { opacity: 1; } 46% { opacity: 0.45; } 62%, 100% { opacity: 1; }",
                "0.7s", "linear"),
    "steps": ("0% { opacity: 0; transform: translateY(24px); } 100% { opacity: 1; transform: none; }", "0.36s", "steps(4, end)"),
    "fade": ("0% { opacity: 0; transform: translateY(14px); } 100% { opacity: 1; transform: none; }", "0.5s", "ease-out"),
    "tape": ("0% { opacity: 0; transform: translateY(-36px) rotate(-6deg); } 70% { opacity: 1; transform: translateY(3px) rotate(-0.5deg); } "
             "100% { opacity: 1; transform: rotate(-1deg); }", "0.55s", "ease-out"),
    "twinkle": ("0% { opacity: 0; transform: scale(0.86); filter: brightness(2.2); } 100% { opacity: 1; transform: none; filter: none; }",
                "0.6s", "ease-out"),
    "slide": ("0% { opacity: 0; transform: translateX(-36px); } 100% { opacity: 1; transform: none; }", "0.35s", "cubic-bezier(0.2, 0.8, 0.2, 1)"),
    # 왼쪽에서 오른쪽으로 드러남. 끝 상태도 잘라 내므로 꼬리표, 그림자가 들어가도록 바깥으로 넉넉히
    "wipe": ("0% { opacity: 0; clip-path: inset(-80px 100% -80px -80px); } 25% { opacity: 1; } "
             "100% { opacity: 1; clip-path: inset(-80px -80px -80px -80px); }", "0.42s", "cubic-bezier(0.7, 0, 0.2, 1)"),
    "punch": ("0% { opacity: 0; transform: scale(1.32) skewX(-9deg); } 60% { opacity: 1; transform: scale(0.97) skewX(2deg); } "
              "100% { opacity: 1; transform: none; }", "0.42s", "cubic-bezier(0.2, 0.9, 0.3, 1.2)"),
    "flip": ("0% { opacity: 0; transform: perspective(700px) rotateY(80deg); } 60% { opacity: 1; transform: perspective(700px) rotateY(-10deg); } "
             "100% { opacity: 1; transform: none; }", "0.6s", "ease-out"),
    "unveil": ("0% { opacity: 0; transform: translateY(10px); filter: brightness(1.9) blur(2px); } 100% { opacity: 1; transform: none; filter: none; }",
               "0.7s", "ease-out"),
}


def _brackets(color: str, size: int = 16, width: int = 3) -> str:
    """모서리 꺾쇠(바탕 위 그라데이션 층): 왼쪽 위와 오른쪽 아래."""
    bar = f"linear-gradient({color}, {color})"
    return (f"{bar} left top / {size}px {width}px no-repeat, {bar} left top / {width}px {size}px no-repeat, "
            f"{bar} right bottom / {size}px {width}px no-repeat, {bar} right bottom / {width}px {size}px no-repeat")


def _style_tokens(key: str, colors: dict[str, str]) -> dict[str, str]:
    """방송 스타일 하나의 변수. 색은 방송 색에서 만든다."""
    p, h = colors["primary"], colors["highlight"]
    base = {"surface": PAPER, "on-surface": INK, "muted": "#4a535b", "line": INK, "line-width": "3px", "line-style": "solid", "radius": "10px",
            "shadow": f"0 6px 0 {INK}", "glow": "none", "backdrop": "none", "tag-bg": p, "tag-text": colors["on-primary"],
            "display": f'"Black Han Sans", {FALLBACK}', "text": f'"Pretendard", {FALLBACK}', "enter": "stamp", "tone": "light"}
    gold = mix(h, "#8a6a2f", 0.35)  # 금장: 강조 색을 조금 어둡고 누렇게
    old_gold = mix(h, "#6b5426", 0.45)
    wood = "#5b3a1e"
    styles: dict[str, dict[str, str]] = {
        "prop": {"surface": f"{_GRAIN}, {PAPER}"},
        "pastel": {"surface": f"linear-gradient(180deg, #ffffff, {mix(p, '#ffffff', 0.84)})", "on-surface": "#4a3f55", "muted": "#7a6f86",
                   "line": mix(p, "#ffffff", 0.4), "radius": "24px", "shadow": f"0 10px 24px {rgba(p, 0.28)}", "tag-bg": mix(p, "#ffffff", 0.25),
                   "tag-text": on_color(mix(p, "#ffffff", 0.25)), "display": f'"Pretendard", {FALLBACK}', "enter": "float"},
        "neon": {"surface": "rgba(12, 10, 28, 0.86)", "on-surface": "#f6f2ff", "muted": "#c3bbdf", "line": p, "line-width": "2px", "radius": "14px",
                 "shadow": f"0 0 0 1px {p}, 0 0 18px {rgba(p, 0.65)}, inset 0 0 14px {rgba(p, 0.35)}", "glow": f"0 0 6px {p}, 0 0 16px {rgba(p, 0.8)}",
                 "enter": "flicker", "tone": "dark"},
        "pixel": {"surface": "#20243f", "on-surface": "#ffffff", "muted": "#c9cde8", "line": "#ffffff", "line-width": "4px", "radius": "0px",
                  "shadow": "4px 4px 0 #000000, 8px 8px 0 rgba(0, 0, 0, 0.35)", "glow": "2px 2px 0 #000000", "display": _PIXEL_FONT,
                  "text": _PIXEL_FONT, "enter": "steps", "tone": "dark"},
        # 흰 글자가 밝은 게임 화면 위에서도 읽히도록 어두운 연기 유리에 위쪽 반사광
        "glass": {"surface": "linear-gradient(160deg, rgba(255, 255, 255, 0.24), rgba(255, 255, 255, 0.04) 55%), rgba(18, 22, 30, 0.42)",
                  "on-surface": "#ffffff", "muted": "rgba(255, 255, 255, 0.88)", "line": "rgba(255, 255, 255, 0.55)",
                  "line-width": "1.5px", "radius": "20px", "shadow": "0 12px 30px rgba(0, 0, 0, 0.28)", "glow": "0 1px 3px rgba(0, 0, 0, 0.45)",
                  "backdrop": "blur(14px) saturate(1.3)", "tag-bg": rgba(p, 0.85), "display": f'"Pretendard", {FALLBACK}', "enter": "fade",
                  "tone": "dark"},
        "diary": {"surface": f"repeating-linear-gradient(180deg, transparent 0 27px, {rgba('#7fa7d9', 0.35)} 27px 28px), #fffdf6",
                  "on-surface": "#3b3330", "muted": "#6b5f58", "line": "#3b3330", "line-width": "2px", "line-style": "dashed", "radius": "4px",
                  "shadow": "3px 4px 0 rgba(59, 51, 48, 0.22)", "tag-bg": rgba(h, 0.8), "tag-text": on_color(h), "display": _HAND_FONT, "text": _HAND_FONT,
                  "enter": "tape"},
        "night": {"surface": ("radial-gradient(1.5px 1.5px at 18% 28%, #ffffff, transparent), radial-gradient(1px 1px at 72% 62%, #ffffff, transparent), "
                              "radial-gradient(1.5px 1.5px at 42% 84%, rgba(255, 255, 255, 0.7), transparent), "
                              "radial-gradient(1px 1px at 88% 18%, #ffffff, transparent), linear-gradient(160deg, #1b2457, #3a2363)"),
                  "on-surface": "#fff8e7", "muted": "#d9cfe8", "line": h, "line-width": "2px", "radius": "16px",
                  "shadow": f"0 0 0 4px {rgba(h, 0.18)}, 0 12px 26px rgba(0, 0, 0, 0.45)", "glow": f"0 0 10px {rgba(h, 0.6)}", "tag-bg": h,
                  "tag-text": colors["on-highlight"], "enter": "twinkle", "tone": "dark"},
        "minimal": {"surface": "rgba(18, 20, 24, 0.82)", "on-surface": "#ffffff", "muted": "rgba(255, 255, 255, 0.72)", "line": "transparent",
                    "line-width": "0px", "radius": "8px", "shadow": f"inset 6px 0 0 {p}", "display": f'"Pretendard", {FALLBACK}', "enter": "slide",
                    "tone": "dark"},
        # ---- 게임 장르 스타일(게임 패키지가 고름). 공식 로고, 글꼴, 그림 없이 모양과 색만
        "tactical": {"surface": f"{_brackets(p)}, linear-gradient(180deg, rgba(20, 27, 35, 0.94), rgba(12, 17, 23, 0.94))",
                     "on-surface": "#f3f0ea", "muted": "#aab4be", "line": "rgba(243, 240, 234, 0.22)", "line-width": "1px", "radius": "0px",
                     "shadow": "0 0 0 1px rgba(0, 0, 0, 0.55), 8px 8px 0 rgba(0, 0, 0, 0.28)", "enter": "wipe", "tone": "dark"},
        "arcane": {"surface": f"radial-gradient(ellipse at 50% -20%, {rgba(p, 0.28)}, transparent 60%), linear-gradient(180deg, rgba(12, 22, 40, 0.95), "
                              "rgba(5, 11, 24, 0.95))",
                   "on-surface": "#f0e6d2", "muted": "#b3ab98", "line": gold, "line-width": "1.5px", "radius": "2px",
                   "shadow": f"0 0 0 3px rgba(5, 11, 24, 0.95), 0 0 0 4px {rgba(gold, 0.6)}, 0 12px 28px rgba(0, 0, 0, 0.55)",
                   "glow": f"0 0 8px {rgba(gold, 0.5)}", "tag-bg": gold, "tag-text": on_color(gold), "enter": "unveil", "tone": "dark"},
        "hero": {"surface": f"linear-gradient(105deg, {p} 0 12px, transparent 12px), linear-gradient(180deg, #ffffff, #e8edf4)",
                 "on-surface": "#1d2733", "muted": "#566577", "line": "rgba(29, 39, 51, 0.14)", "line-width": "2px", "radius": "6px",
                 "shadow": "0 10px 24px rgba(20, 30, 50, 0.28)", "enter": "punch"},
        "tavern": {"surface": "radial-gradient(ellipse at 50% 0%, rgba(255, 255, 255, 0.55), transparent 65%), linear-gradient(180deg, #f7e9c8, #e8cf9c)",
                   "on-surface": "#3a2513", "muted": "#6e5235", "line": "#6b4423", "line-width": "3px", "radius": "14px",
                   "shadow": f"inset 0 0 0 2px {rgba(h, 0.9)}, 0 0 0 4px {wood}, 0 10px 22px rgba(0, 0, 0, 0.4)", "enter": "flip"},
        "survival": {"surface": f"repeating-linear-gradient(135deg, {h} 0 9px, #1c1f18 9px 18px) left top / 100% 6px no-repeat, "
                                "linear-gradient(180deg, rgba(46, 51, 39, 0.95), rgba(29, 32, 25, 0.95))",
                     "on-surface": "#f0ead6", "muted": "#bdb69e", "line": "rgba(240, 234, 214, 0.28)", "line-width": "2px", "radius": "2px",
                     "shadow": "5px 5px 0 rgba(0, 0, 0, 0.45)", "tag-bg": h, "tag-text": colors["on-highlight"], "enter": "stamp", "tone": "dark"},
        "adventure": {"surface": "linear-gradient(180deg, #fffaf0, #ffe8c4)", "on-surface": "#4a2e18", "muted": "#7a5a3c", "line": "#a5682b",
                      "line-width": "3px", "radius": "18px", "shadow": "0 0 0 3px #fff4dc, 0 0 0 6px #a5682b, 0 9px 0 6px rgba(90, 52, 20, 0.3)",
                      "enter": "float"},
        "gothic": {"surface": "radial-gradient(ellipse at 50% 130%, rgba(150, 24, 24, 0.4), transparent 65%), linear-gradient(180deg, rgba(22, 17, 16, 0.96), "
                              "rgba(10, 8, 8, 0.96))",
                   "on-surface": "#efe3c8", "muted": "#a99780", "line": old_gold, "line-width": "1px", "radius": "0px",
                   "shadow": f"0 0 0 1px #000000, 0 0 0 4px rgba(10, 8, 8, 0.96), 0 0 0 5px {rgba(old_gold, 0.55)}, 0 14px 30px rgba(0, 0, 0, 0.6)",
                   "glow": "0 0 10px rgba(190, 40, 30, 0.55)", "tag-bg": "#7d1d1a", "tag-text": "#ffffff", "enter": "unveil", "tone": "dark"},
        "sports": {"surface": f"linear-gradient(90deg, {p} 0 10px, {h} 10px 14px, transparent 14px), linear-gradient(180deg, #13315a, #0b1f3b)",
                   "on-surface": "#ffffff", "muted": "#b9c9de", "line": "transparent", "line-width": "0px", "radius": "4px",
                   "shadow": "0 8px 18px rgba(0, 0, 0, 0.35)", "tag-bg": h, "tag-text": colors["on-highlight"], "enter": "wipe", "tone": "dark"},
    }
    return {**base, **styles.get(key, styles["prop"])}


#: 방송 스타일: 이름 -> (표시 이름, 설명). 미리보기 색은 info()가 방송 색으로 만든다
STYLES: dict[str, tuple[str, str]] = {
    "prop": ("방송 소품", "크림 종이, 잉크 외곽선, 딱딱한 그림자(기본)"),
    "pastel": ("파스텔 몽글", "흰 바탕에 방송 색 물감, 둥근 모서리, 부드러운 그림자"),
    "neon": ("네온", "어두운 유리에 빛나는 테두리와 글자"),
    "pixel": ("레트로 픽셀", "각진 대화 상자, 계단 그림자, 도트 글꼴(설치한 경우)"),
    "glass": ("유리", "뒤가 흐리게 비치는 반투명 판"),
    "diary": ("다이어리", "줄 노트, 점선 테두리, 마스킹 테이프, 손글씨 글꼴(설치한 경우)"),
    "night": ("밤하늘", "별이 뜬 남보라 하늘, 금빛 테두리"),
    "minimal": ("미니멀", "어두운 반투명 띠와 방송 색 막대"),
    "tactical": ("택티컬", "전술 FPS: 어두운 판, 꺾쇠 모서리, 쓱 지나가며 등장"),
    "arcane": ("마법 금장", "판타지 AOS: 짙은 남색 판, 금빛 이중 테두리"),
    "hero": ("히어로", "히어로 슈터: 밝은 흰 판, 비스듬한 색 띠, 확 튀어나옴"),
    "tavern": ("선술집 카드", "카드 게임: 양피지 카드, 금테와 나무 테두리, 카드 뒤집기"),
    "survival": ("서바이벌", "배틀로얄: 군용 올리브 판, 경고 줄무늬"),
    "adventure": ("모험 동화", "캐주얼 RPG: 크림 판, 둥근 나무 테두리, 말랑한 등장"),
    "gothic": ("다크 판타지", "다크 판타지 RPG: 검붉은 판, 낡은 금 테두리"),
    "sports": ("스포츠 중계", "축구, 야구 게임: 중계 자막 띠, 남색 판"),
}
#: 게임 장르 스타일(미리보기에서 따로 묶어 보여 줌). 나머지는 일반 스타일
GENRE_STYLES = ("tactical", "arcane", "hero", "tavern", "survival", "adventure", "gothic", "sports")


# --------------------------------------------------------------------------- 글꼴


def check_font(value: Any, fonts: list[dict[str, str]]) -> str:
    """글꼴 선택: 빈 값(스타일 기본), FONT_CHOICES 이름, ``local:설치한 글꼴 이름``, ``user:번호`` (올린 글꼴)."""
    text = str(value or "").strip()
    if not text or text in FONT_CHOICES:
        return text
    if text.startswith("local:"):
        name = text[6:].strip()
        if not _LOCAL_NAME.match(name):
            raise ThemeError("설치한 글꼴 이름은 한글, 영문, 숫자, 공백, -, _, . 로 40자 이내(Windows 글꼴 설정에 보이는 이름)")
        return f"local:{name}"
    if text.startswith("user:") and any(font["id"] == text[5:] for font in fonts):
        return text
    raise ThemeError("없는 글꼴: 목록에서 고르거나 설치한 글꼴 이름을 입력")


def font_stack(choice: str, fonts: list[dict[str, str]]) -> str | None:
    if choice in FONT_CHOICES:
        return FONT_CHOICES[choice][1]
    if choice.startswith("local:"):
        return f'"{choice[6:]}", {FALLBACK}'
    if choice.startswith("user:") and any(font["id"] == choice[5:] for font in fonts):
        return f'"dk-user-{choice[5:]}", {FALLBACK}'
    return None


def font_folder() -> Path:
    return settings.data_path(FONT_FOLDER)


def user_font_faces(fonts: list[dict[str, str]]) -> str:
    faces = []
    for font in fonts:
        kind = FONT_MAGIC_BY_EXT.get(font.get("ext", ""), "")
        if kind:
            faces.append(f'@font-face {{ font-family: "dk-user-{font["id"]}"; src: url("/theme/font?id={font["id"]}") format("{kind}"); '
                         "font-display: swap; }\n")
    return "".join(faces)


FONT_MAGIC_BY_EXT = {ext: kind for ext, kind in FONT_MAGIC.values()}


def decode_font(data: Any) -> tuple[bytes, str]:
    """올린 글꼴(base64 또는 data URL) 확인: (내용, 확장자). 틀리면 ThemeError."""
    text = str(data or "")
    if text.startswith("data:"):
        text = text.split(",", 1)[-1]
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise ThemeError("글꼴 파일을 읽지 못함") from None
    if not raw:
        raise ThemeError("글꼴 파일이 비어 있음")
    if len(raw) > MAX_FONT:
        raise ThemeError(f"글꼴 파일은 {MAX_FONT // 1024 // 1024} MB 이하")
    for magic, (ext, _) in FONT_MAGIC.items():
        if raw.startswith(magic):
            return raw, ext
    raise ThemeError("글꼴 파일이 아님: TTF, OTF, WOFF, WOFF2만")


# --------------------------------------------------------------------------- 저장과 CSS


def load() -> dict[str, Any]:
    saved = settings.load_data(DATA)
    _, primary, highlight = PRESETS["pink"]
    try:
        primary = check_color(saved.get("primary", primary), "주 색")
        highlight = check_color(saved.get("highlight", highlight), "강조 색")
    except ThemeError:
        _, primary, highlight = PRESETS["pink"]
    preset = saved.get("preset") if saved.get("preset") in PRESETS else ""
    fonts = [font for font in saved.get("fonts") or [] if isinstance(font, dict) and re.fullmatch(r"[0-9a-f]{24}", str(font.get("id", "")))
             and font.get("ext") in FONT_TYPES][:MAX_FONTS]
    fonts = [{"id": font["id"], "ext": font["ext"], "name": str(font.get("name") or "내 글꼴")[:40]} for font in fonts]
    choices = {}
    for name in ("display_font", "text_font"):
        try:
            choices[name] = check_font(saved.get(name, ""), fonts)
        except ThemeError:
            choices[name] = ""
    style = saved.get("style") if saved.get("style") in STYLES else "prop"
    return {"primary": primary, "highlight": highlight, "preset": preset, "style": style, **choices, "fonts": fonts}


def tokens(theme: dict[str, Any] | None = None) -> dict[str, str]:
    """CSS 변수 값(이름은 --dk- 뒤). 색, 방송 스타일, 글꼴."""
    theme = theme or load()
    colors = palette(theme["primary"], theme["highlight"])
    found = {**colors, **_style_tokens(theme["style"], colors), "style": theme["style"]}
    for slot, name in (("display", "display_font"), ("text", "text_font")):
        stack = font_stack(theme.get(name, ""), theme.get("fonts", []))
        if stack:
            found[slot] = stack
    enter = ENTERS[found.pop("enter")]
    found["enter-time"], found["enter-ease"] = enter[1], enter[2]
    found["hard-shadow"] = f"0 6px 0 {rgba(INK, 0.88)}"
    found["grain"] = _GRAIN
    return found


def css(theme: dict[str, Any] | None = None, *, fonts: bool = True) -> str:
    """``fonts`` 가 False면 함께 배포한 글꼴 선언은 빼고 변수만(조작 화면은 본문을 이 PC 글꼴로 써서 보통 굵기를 유지). 내 글꼴 선언은 넣는다."""
    theme = theme or load()
    values = tokens(theme)
    enter = ENTERS[_style_tokens(theme["style"], palette(theme["primary"], theme["highlight"]))["enter"]][0]
    variables = "".join(f"  --dk-{key}: {value};\n" for key, value in values.items())
    return ((FONTS if fonts else "") + user_font_faces(theme.get("fonts", [])) + ":root {\n" + variables + "}\n"
            + f"@keyframes dk-enter {{ {enter} }}\n")


def logo_colors() -> dict[str, str] | None:
    """마지막으로 저장한 로고의 심볼 주 색(로고 만들기 기록). 없으면 None."""
    from .. import logo

    try:
        lines = (logo.logos_dir() / "made.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            symbol = json.loads(line).get("symbol") or {}
            return {"primary": check_color(symbol.get("primary"), "주 색")}
        except (ValueError, ThemeError, AttributeError):
            continue
    return None


def _feed_value(seq: int) -> dict[str, Any]:
    """/live 의 theme 항목: 저장 값과 색. 처음 값에도 색이 있어야 theme.js가 기준으로 삼아 다음 스타일 변경을 알아챈다."""
    current = load()
    return {"seq": seq, **current, "palette": palette(current["primary"], current["highlight"])}


def make_feature(context: feature.Context) -> feature.Feature:
    channel = feature.Channel(_feed_value(0))

    def info(_: Any = None) -> dict[str, Any]:
        current = load()
        colors = palette(current["primary"], current["highlight"])
        styles = {}
        for key, (name, about) in STYLES.items():
            values = _style_tokens(key, colors)
            styles[key] = {"name": name, "about": about, "surface": values["surface"], "on": values["on-surface"], "line": values["line"],
                           "radius": values["radius"], "shadow": values["shadow"], "tag": values["tag-bg"], "font": values["display"],
                           "tone": values["tone"], "group": "game" if key in GENRE_STYLES else "basic"}
        return {**current, "palette": colors, "tokens": tokens(current),
                "presets": {key: {"name": name, "primary": primary, "highlight": highlight} for key, (name, primary, highlight) in PRESETS.items()},
                "styles": styles, "font_choices": {key: {"name": name, "about": about} for key, (name, _, about) in FONT_CHOICES.items()},
                "logo": logo_colors()}

    def store(values: dict[str, Any]) -> dict[str, Any]:
        settings.save_data(DATA, values)
        channel.publish(_feed_value(channel.current.get("seq", 0) + 1))
        return info()

    def saved_values() -> dict[str, Any]:
        current = load()
        return {key: current[key] for key in ("primary", "highlight", "preset", "style", "display_font", "text_font", "fonts")}

    def save(data: dict[str, Any]) -> dict[str, Any]:
        values = saved_values()
        if data.get("preset"):
            if data["preset"] not in PRESETS:
                raise ThemeError("없는 색 조합: " + ", ".join(PRESETS))
            _, values["primary"], values["highlight"] = PRESETS[data["preset"]]
            values["preset"] = data["preset"]
        elif data.get("from_logo"):
            found = logo_colors()
            if not found:
                raise ThemeError("저장한 로고 기록 없음: 로고 만들기에서 로고를 저장한 뒤 사용")
            values["primary"], values["preset"] = found["primary"], ""
        elif "primary" in data or "highlight" in data:
            values["primary"] = check_color(data.get("primary", values["primary"]), "주 색")
            values["highlight"] = check_color(data.get("highlight", values["highlight"]), "강조 색")
            values["preset"] = ""
        if "style" in data:
            if data["style"] not in STYLES:
                raise ThemeError("방송 스타일은 " + ", ".join(STYLES) + " 중 하나")
            values["style"] = data["style"]
        for name in ("display_font", "text_font"):
            if name in data:
                values[name] = check_font(data[name], values["fonts"])
        return store(values)

    def upload_font(data: dict[str, Any]) -> dict[str, Any]:
        values = saved_values()
        if len(values["fonts"]) >= MAX_FONTS:
            raise ThemeError(f"내 글꼴은 {MAX_FONTS}개까지: 쓰지 않는 글꼴을 지운 뒤 올리기")
        raw, ext = decode_font(data.get("data"))
        name = re.sub(r"\.(ttf|otf|woff2?)$", "", str(data.get("name") or "내 글꼴").strip(), flags=re.IGNORECASE)[:40] or "내 글꼴"
        font_id = secrets.token_hex(12)
        folder = font_folder()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{font_id}.{ext}").write_bytes(raw)
        values["fonts"] = [*values["fonts"], {"id": font_id, "ext": ext, "name": name}]
        for slot in data.get("use") or []:  # 올리면서 바로 쓰기("display", "text")
            if slot in ("display", "text"):
                values[f"{slot}_font"] = f"user:{font_id}"
        answer = store(values)
        return {**answer, "uploaded": font_id}

    def remove_font(data: dict[str, Any]) -> dict[str, Any]:
        values = saved_values()
        font_id = str(data.get("id") or "")
        found = next((font for font in values["fonts"] if font["id"] == font_id), None)
        if found is None:
            raise ThemeError("없는 글꼴", 404)
        values["fonts"] = [font for font in values["fonts"] if font["id"] != font_id]
        for name in ("display_font", "text_font"):
            if values[name] == f"user:{font_id}":
                values[name] = ""
        try:
            (font_folder() / f"{font_id}.{found['ext']}").unlink()
        except OSError:
            pass
        return store(values)

    def font_file(query: feature.Query) -> feature.Raw:
        font_id = query.get("id", [""])[0]
        found = next((font for font in load()["fonts"] if font["id"] == font_id), None)
        if found is None:
            raise ThemeError("없는 글꼴", 404)
        try:
            body = (font_folder() / f"{font_id}.{found['ext']}").read_bytes()
        except OSError:
            raise ThemeError("글꼴 파일이 없어짐", 404) from None
        return feature.Raw(body, FONT_TYPES[found["ext"]], "default-src 'none'; sandbox")

    def stylesheet(query: feature.Query) -> feature.Raw:
        """``?style=neon`` 은 이 화면만 다른 방송 스타일(알림, 채팅을 따로 꾸밀 때), ``?fonts=0`` 은 함께 배포한 글꼴 선언 빼기."""
        current = load()
        style = query.get("style", [""])[0]
        if style in STYLES:
            current = {**current, "style": style}
        return feature.Raw(css(current, fonts=query.get("fonts", ["1"])[0] != "0").encode("utf-8"), "text/css; charset=utf-8")

    handlers: dict[str, Callable[[Any], Any]] = {"/theme": info, "/theme.css": stylesheet, "/theme/font": font_file}
    return feature.Feature(name="theme", get=handlers, post={"/theme": save, "/theme/font": upload_font, "/theme/font/remove": remove_font},
                           feeds={"theme": channel}, body_limit={"/theme/font": MAX_FONT * 4 // 3 + 4096})
