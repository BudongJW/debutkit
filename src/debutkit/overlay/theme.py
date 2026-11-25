"""방송 색(채널 테마): 모든 방송 화면(채팅, 알림, 추첨, 뽑기판, 후원 벽, 레이스)과 조작 화면이 함께 쓰는 색과 글꼴.

- ``/theme.css``: 함께 배포하는 글꼴(Black Han Sans, Pretendard)과 CSS 변수. 화면마다 ``<link rel="stylesheet" href="/theme.css">``
  ``--dk-primary`` (주 색), ``--dk-primary-light``, ``--dk-primary-deep``, ``--dk-on-primary`` (주 색 위 글자), ``--dk-highlight`` (강조, 희귀),
  ``--dk-ink`` (슬레이트 잉크), ``--dk-paper`` (크림 종이), ``--dk-display`` (제목 글꼴), ``--dk-text`` (본문 글꼴)
- ``/theme`` 조회, ``POST /theme`` (``{"primary": "#ff4f8b", "highlight": "#ffd84d"}`` 또는 ``{"preset": "lavender"}``, ``{"from_logo": true}``)
- ``/live?feeds=theme`` 로 바뀐 색을 받아 화면이 새로고침 없이 바꿀 수 있다(``window.debutkitTheme`` 도움 함수, ui.js)
- 설정은 설정 폴더의 ``theme.json``. 로고 만들기에서 마지막으로 저장한 로고의 주 색을 가져올 수 있다
"""

from __future__ import annotations

import colorsys
import json
import re
from typing import Any

from .. import settings
from . import feature

DATA = "theme.json"
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


def load() -> dict[str, str]:
    saved = settings.load_data(DATA)
    _, primary, highlight = PRESETS["pink"]
    try:
        primary = check_color(saved.get("primary", primary), "주 색")
        highlight = check_color(saved.get("highlight", highlight), "강조 색")
    except ThemeError:
        _, primary, highlight = PRESETS["pink"]
    preset = saved.get("preset") if saved.get("preset") in PRESETS else ""
    return {"primary": primary, "highlight": highlight, "preset": preset}


def css(theme: dict[str, str] | None = None, *, fonts: bool = True) -> str:
    """``fonts`` 가 False면 변수만(조작 화면은 본문을 이 PC 글꼴로 써서 보통 굵기를 유지)."""
    theme = theme or load()
    colors = palette(theme["primary"], theme["highlight"])
    variables = "".join(f"  --dk-{key}: {value};\n" for key, value in colors.items())
    return ((FONTS if fonts else "") + ":root {\n" + variables
            + '  --dk-display: "Black Han Sans", "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;\n'
            + '  --dk-text: "Pretendard", "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans CJK KR", sans-serif;\n'
            + "  --dk-hard-shadow: 0 6px 0 rgba(30, 35, 39, 0.88);\n}\n")


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


def make_feature(context: feature.Context) -> feature.Feature:
    channel = feature.Channel({"seq": 0, **load()})

    def info(_: Any = None) -> dict[str, Any]:
        current = load()
        return {**current, "palette": palette(current["primary"], current["highlight"]),
                "presets": {key: {"name": name, "primary": primary, "highlight": highlight} for key, (name, primary, highlight) in PRESETS.items()},
                "logo": logo_colors()}

    def save(data: dict[str, Any]) -> dict[str, Any]:
        current = load()
        if data.get("preset"):
            if data["preset"] not in PRESETS:
                raise ThemeError("없는 색 조합: " + ", ".join(PRESETS))
            _, primary, highlight = PRESETS[data["preset"]]
            preset = data["preset"]
        elif data.get("from_logo"):
            found = logo_colors()
            if not found:
                raise ThemeError("저장한 로고 기록 없음: 로고 만들기에서 로고를 저장한 뒤 사용")
            primary, highlight, preset = found["primary"], current["highlight"], ""
        else:
            primary = check_color(data.get("primary", current["primary"]), "주 색")
            highlight = check_color(data.get("highlight", current["highlight"]), "강조 색")
            preset = ""
        settings.save_data(DATA, {"primary": primary, "highlight": highlight, "preset": preset})
        channel.publish({"seq": channel.current.get("seq", 0) + 1, "primary": primary, "highlight": highlight, "preset": preset,
                         "palette": palette(primary, highlight)})
        return info()

    return feature.Feature(name="theme", get={"/theme": info, "/theme.css": lambda query: feature.Raw(css(fonts=query.get("fonts", ["1"])[0] != "0").encode("utf-8"),
                                                                                                  "text/css; charset=utf-8")},
                           post={"/theme": save}, feeds={"theme": channel})
