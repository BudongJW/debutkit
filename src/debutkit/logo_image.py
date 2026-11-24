"""공개 이미지 모델로 로고 심볼 만들기: 단색 배경 위에 그린 그림을 받아 배경을 지우고 벡터(SVG)로 바꾼다.

- 모델: Qwen-Image(Apache-2.0). 빠름은 Lightning LoRA 8단계, 고품질은 기본 단계
- 실행 위치 두 가지
  - ComfyUI: 사용자가 설치한 ComfyUI(이 PC나 같은 네트워크의 GPU PC)에 HTTP로 작업 제출. 설명이 그 PC 밖으로 나가지 않음
  - Hugging Face: 공개 데모(Space)를 사용자 토큰으로 실행(Hugging Face의 무료 GPU 한도 사용)
- 처리 순서: 캐릭터에 없는 단색(초록, 초록 계열 색을 쓰면 자홍) 배경 위에 그리게 한 뒤
  1. 배경색 제거(배경색과 섞인 가장자리 픽셀은 배경 몫을 빼서 원래 색으로)
  2. 반투명 가장자리를 안쪽 색으로 다시 칠해 어두운 화면에서 밝은 테두리가 보이지 않게
  3. 내용 영역만 정사각형으로 자르고 색 수를 줄인 뒤 색 영역별 경계를 따라 벡터화(넓은 색부터 쌓아 색 사이 틈 방지)
- 받은 원본 그림, 시드, 지시문은 생성 기록에 남겨 같은 심볼을 다시 만들 수 있게 한다
"""

from __future__ import annotations

import io
import json
import math
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from . import __version__

Opener = Callable[..., Any]

GREEN, MAGENTA = (0, 255, 0), (255, 0, 255)
IMAGE_LIMIT = 40_000_000  # 받는 그림 최대 크기(바이트)
TRACE_SIZE = 1024  # 벡터화할 때 그림 크기(픽셀)
TRACE_COLORS = 10  # 벡터화 전 색 수
#: 이 알파부터 픽셀 자신의 색을 믿고, 이 아래는 버린다
SOLID, FAINT = 0.92, 0.10
NEGATIVE = "text, letters, words, numbers, watermark, signature, photo, realistic, 3d render, gradient, shadow, texture, noise, frame, border"


class ImageModelError(ValueError):
    """공개 모델 생성 실패. 메시지는 한국어 안내."""


@dataclass(frozen=True)
class Made:
    master: bytes  # 모델이 그린 원본 그림(PNG 또는 WebP)
    model: str
    seed: int
    prompt: str


def _mask(text: str, secret: str | None) -> str:
    return text.replace(secret, "****") if secret else text


# --- 지시문 -------------------------------------------------------------------------------


def _hue(colour: tuple[int, int, int]) -> tuple[float, float]:
    """색상(도)과 채도 폭(0에서 1)."""
    red, green, blue = (value / 255 for value in colour)
    high, low = max(red, green, blue), min(red, green, blue)
    if high - low < 1e-9:
        return 0.0, 0.0
    if high == red:
        hue = 60 * (((green - blue) / (high - low)) % 6)
    elif high == green:
        hue = 60 * ((blue - red) / (high - low) + 2)
    else:
        hue = 60 * ((red - green) / (high - low) + 4)
    return hue, high - low


def _is_greenish(color: str) -> bool:
    hue, chroma = _hue(tuple(int(color[index:index + 2], 16) for index in (1, 3, 5)))  # type: ignore[arg-type]
    return chroma >= 0.25 and 75 <= hue <= 165


def _is_backdrop(border: tuple[int, int, int], key: tuple[int, int, int]) -> bool:
    """테두리 색이 요청한 배경 색 계열인지. 모델은 순수 초록(#00FF00) 대신 탁한 초록(예: 91,198,105)을 칠하기도 하므로
    색 값이 아니라 색상으로 판정한다."""
    hue, chroma = _hue(border)
    if chroma < 0.2:
        return False
    return 75 <= hue <= 165 if key == GREEN else 270 <= hue <= 330


def key_colour(colors: list[str]) -> tuple[int, int, int]:
    """배경으로 칠하게 할 색: 초록. 고른 색에 초록 계열이 있으면 자홍."""
    return MAGENTA if any(_is_greenish(color) for color in colors) else GREEN


def raster_prompt(description: str, style: str, colors: list[str], key: tuple[int, int, int]) -> str:
    """글자 없는 평면 심볼을 단색 배경 위에(배경은 나중에 지운다)."""
    palette = ", ".join(colors) if colors else "a small harmonious palette of 3 to 4 colors"
    back = "pure green #00FF00" if key == GREEN else "pure magenta #FF00FF"
    return (f"Flat vector logo symbol for a VTuber live-streaming channel: {description}. {style}. "
            f"Mascot icon design with bold clean dark outlines, flat solid colors and a strong simple silhouette that reads at small sizes. "
            f"Colors: {palette}. One single symbol, centered, filling about 80 percent of the square frame. "
            f"No text, no letters, no numbers, no watermark, no shadow, no gradient, no texture, no frame. "
            f"Plain solid {back} background with nothing else on it.")


# --- 배경 제거와 벡터화 --------------------------------------------------------------------


def _numpy() -> Any:
    try:
        import numpy as np
        from PIL import Image  # noqa: F401
    except ImportError as error:
        raise ImageModelError('공개 모델 심볼 처리에 numpy와 Pillow 필요: pip install "debutkit[logo]"') from error
    return np


def _neighbours(values: Any, known: Any) -> tuple[Any, Any]:
    """알려진 이웃(8방향) 값의 합과 수."""
    np = _numpy()
    height, width = known.shape
    padded_values = np.pad(values * known[..., None], ((1, 1), (1, 1), (0, 0)))
    padded_known = np.pad(known.astype(np.float64), 1)
    total = np.zeros_like(values)
    count = np.zeros((height, width))
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            if dy == 1 and dx == 1:
                continue
            total += padded_values[dy:dy + height, dx:dx + width]
            count += padded_known[dy:dy + height, dx:dx + width]
    return total, count


def bleed(rgb: Any, known: Any, *, reach: int = 8) -> Any:
    """알려지지 않은 픽셀에 가장 가까운 알려진 픽셀의 색(최대 ``reach`` 픽셀)."""
    colours = rgb.astype("float64").copy()
    known = known.copy()
    for _ in range(reach):
        if known.all():
            break
        total, count = _neighbours(colours, known)
        fresh = ~known & (count > 0)
        if not fresh.any():
            break
        colours[fresh] = total[fresh] / count[fresh][:, None]
        known |= fresh
    return colours


def clean_edge(image: Any, *, solid: float = SOLID, faint: float = FAINT) -> Any:
    """반투명 가장자리를 안쪽 색으로 다시 칠하고 가장 흐린 부분은 버린다(어두운 화면의 밝은 테두리 방지)."""
    np = _numpy()
    from PIL import Image

    pixels = np.asarray(image.convert("RGBA")).astype(np.float64)
    alpha = pixels[..., 3] / 255.0
    trusted = alpha >= solid
    if not trusted.any():
        return image.convert("RGBA")
    colours = bleed(pixels[..., :3], trusted)
    kept = np.clip((alpha - faint) / (solid - faint), 0.0, 1.0)
    out = np.dstack([np.where(trusted[..., None], pixels[..., :3], colours), kept * 255.0])
    out[kept <= 0, :3] = 0
    return Image.fromarray(np.clip(np.rint(out), 0, 255).astype(np.uint8), "RGBA")


def border_colour(image: Any, *, ring: int = 4) -> tuple[int, int, int]:
    """그림 테두리 몇 픽셀의 중앙값 색."""
    np = _numpy()
    pixels = np.asarray(image.convert("RGB"))
    ring = max(1, min(ring, min(pixels.shape[:2]) // 2))
    frame = np.concatenate([pixels[:ring].reshape(-1, 3), pixels[-ring:].reshape(-1, 3), pixels[:, :ring].reshape(-1, 3),
                            pixels[:, -ring:].reshape(-1, 3)])
    return tuple(int(value) for value in np.median(frame, axis=0))


def _distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b, strict=True)) ** 0.5 / (255.0 * 3 ** 0.5)


def key_background(image: Any, colour: tuple[int, int, int], *, near: float = 0.06, far: float = 0.18, everywhere: bool = True) -> Any:
    """단색 배경 제거. ``near`` 안쪽은 투명, ``far`` 바깥은 그대로, 사이는 배경 몫을 뺀 반투명.

    ``everywhere`` 이면 그 색을 그림 전체에서 지운다(도형이 감싼 틈의 배경까지. 캐릭터에 없는 색일 때 맞음).
    아니면 테두리와 이어진 부분만 지운다.
    """
    np = _numpy()
    from PIL import Image, ImageDraw

    rgb = np.asarray(image.convert("RGB")).astype(np.float64)
    back = np.array(colour, dtype=np.float64)
    distance = np.sqrt(((rgb - back) ** 2).sum(axis=2)) / (255.0 * np.sqrt(3.0))
    like = distance < far
    if everywhere:
        outside = like
    else:
        mask = Image.fromarray(np.pad(like, 1, constant_values=True).astype(np.uint8) * 255, "L").copy()
        ImageDraw.floodfill(mask, (0, 0), 128)
        outside = np.asarray(mask)[1:-1, 1:-1] == 128
    alpha = np.where(outside, np.clip((distance - near) / (far - near), 0.0, 1.0), 1.0)
    share = np.maximum(alpha, 1e-3)[..., None]
    front = np.clip((rgb - (1.0 - share) * back) / share, 0.0, 255.0)
    out = np.dstack([np.where((alpha > 0.5)[..., None], front, rgb), alpha * 255.0])
    return Image.fromarray(np.clip(np.rint(out), 0, 255).astype(np.uint8), "RGBA")


def _dominance(rgb: Any, key: tuple[int, int, int]) -> Any:
    """배경 색 쪽으로 치우친 정도: 초록은 G가 R, B보다 큰 만큼, 자홍은 R, B가 G보다 큰 만큼."""
    np = _numpy()
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return green - np.maximum(red, blue) if key == GREEN else np.minimum(red, blue) - green


def chroma_key(image: Any, key: tuple[int, int, int], back: tuple[int, int, int], *, tolerance: float = 0.06) -> Any:
    """초록이나 자홍 배경 제거(크로마 키). 배경 색 쪽으로 치우친 정도로 투명도를 정하고, 섞인 픽셀은 배경 몫을 빼고
    남은 색 번짐(초록 기운)도 지운다. 그림에 그 색 계열이 없을 때만 맞는 방식(지시문과 배경색 선택으로 보장)."""
    np = _numpy()
    from PIL import Image

    rgb = np.asarray(image.convert("RGB")).astype(np.float64)
    backdrop = np.array(back, dtype=np.float64)
    full = float(_dominance(backdrop[None, None, :], key)[0, 0])
    full -= max(6.0, 0.12 * full)  # 배경의 미세한 잡음(필름 입자)도 완전히 투명하게
    floor = tolerance * 255.0
    alpha = np.clip(1.0 - (_dominance(rgb, key) - floor) / max(full - floor, 1.0), 0.0, 1.0)
    share = np.maximum(alpha, 1e-3)[..., None]
    front = np.clip((rgb - (1.0 - share) * backdrop) / share, 0.0, 255.0)
    if key == GREEN:
        front[..., 1] = np.minimum(front[..., 1], np.maximum(front[..., 0], front[..., 2]))
    else:
        spill = np.maximum(np.minimum(front[..., 0], front[..., 2]) - front[..., 1], 0.0)
        front[..., 0] -= spill
        front[..., 2] -= spill
    out = np.dstack([np.where((alpha > 0.02)[..., None], front, 0.0), alpha * 255.0])
    return Image.fromarray(np.clip(np.rint(out), 0, 255).astype(np.uint8), "RGBA")


def cut_out(data: bytes, key: tuple[int, int, int]) -> Any:
    """받은 그림에서 배경을 지운 투명 그림. 배경이 요청한 초록이나 자홍이면 크로마 키, 다른 단색이면 테두리와 이어진 배경만 지운다."""
    np = _numpy()
    from PIL import Image, UnidentifiedImageError

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ImageModelError("받은 그림을 읽지 못함: 다시 만들기") from error
    if image.mode in ("RGBA", "LA") and min(image.getchannel("A").getextrema()) < 250:
        return clean_edge(image)
    border = border_colour(image)
    strength = float(_dominance(np.array(border, dtype=np.float64)[None, None, :], key)[0, 0])
    if _is_backdrop(border, key) and strength > 0.1 * 255:
        cut = chroma_key(image, key, border)
    else:  # 모델이 다른 단색 배경을 그린 경우
        cut = key_background(image, border, everywhere=False)
    return clean_edge(cut)


def coverage(image: Any) -> float:
    """불투명한 부분의 비율."""
    np = _numpy()
    return float((np.asarray(image.getchannel("A")) >= 128).mean())


def square_crop(image: Any, *, size: int = TRACE_SIZE, margin: float = 0.04) -> Any:
    """불투명한 내용만 정사각형으로(여백 ``margin``) 자르고 ``size`` 픽셀로."""
    np = _numpy()
    from PIL import Image

    alpha = np.asarray(image.getchannel("A"))
    rows, cols = np.nonzero(alpha >= 128)
    if rows.size == 0:
        raise ImageModelError("배경을 지우니 남은 그림이 없음: 다시 만들기")
    top, bottom, left, right = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
    side = max(bottom - top, right - left)
    pad = int(round(side * margin))
    canvas = Image.new("RGBA", (side + pad * 2, side + pad * 2), (0, 0, 0, 0))
    canvas.paste(image.crop((left, top, right, bottom)), (pad + (side - (right - left)) // 2, pad + (side - (bottom - top)) // 2))
    return canvas.resize((size, size), Image.Resampling.LANCZOS)


@dataclass(frozen=True)
class Poster:
    labels: Any  # 픽셀별 색 번호(투명은 -1)
    palette: list[tuple[int, int, int]]

    def image(self) -> Any:
        """확인용 그림."""
        np = _numpy()
        from PIL import Image

        colours = np.array(self.palette + [(0, 0, 0)], dtype=np.uint8)
        rgb = colours[self.labels]
        return Image.fromarray(np.dstack([rgb, np.where(self.labels >= 0, 255, 0).astype(np.uint8)]), "RGBA")


def posterize(image: Any, colors: int = TRACE_COLORS, *, speck: int = 5, minor: float = 0.012, merge: float = 7.0) -> Poster:
    """불투명한 픽셀만으로 고른 ``colors`` 색으로 줄이고 투명은 켜짐과 꺼짐 둘로. 작은 점은 둘레 색으로,
    넓이가 ``minor`` 보다 작은 색은 가장 가까운 색으로, 색 차이(CIE Lab 거리)가 ``merge`` 보다 작은 색끼리는 넓은 쪽으로 합친다
    (벡터화 준비)."""
    np = _numpy()
    from PIL import Image, ImageFilter

    rgba = np.asarray(image.convert("RGBA"))
    solid = rgba[..., 3] >= 128
    if not solid.any():
        raise ImageModelError("배경을 지우니 남은 그림이 없음: 다시 만들기")
    smooth = np.asarray(Image.fromarray(np.ascontiguousarray(rgba[..., :3])).filter(ImageFilter.MedianFilter(3)))
    sample = smooth[solid].reshape(1, -1, 3)
    quantized = Image.fromarray(np.ascontiguousarray(sample), "RGB").quantize(colors=colors, method=Image.Quantize.MEDIANCUT,
                                                                             dither=Image.Dither.NONE)
    mapped = Image.fromarray(smooth).quantize(palette=quantized, dither=Image.Dither.NONE)
    if speck > 1:
        mapped = mapped.filter(ImageFilter.ModeFilter(speck))  # 몇 픽셀짜리 얼룩을 둘레에서 가장 많은 색으로
    alpha = Image.fromarray((solid * 255).astype(np.uint8)).filter(ImageFilter.ModeFilter(speck)) if speck > 1 else None
    labels = np.asarray(mapped).astype(np.int32)
    solid = np.asarray(alpha) >= 128 if alpha is not None else solid
    raw = quantized.getpalette() or []
    counts = {int(value): int(count) for value, count in zip(*np.unique(labels[solid], return_counts=True), strict=True)}
    total = max(sum(counts.values()), 1)

    def colour(index: int) -> Any:
        return np.array(raw[index * 3:index * 3 + 3], dtype=np.float64)

    def blend(index: int, majors: list[int]) -> bool:
        """두 주요 색 사이의 섞인 색(경계의 부드럽게 처리된 픽셀)인지."""
        point = colour(index)
        for first in majors:
            for second in majors:
                if first >= second:
                    continue
                a, b = colour(first), colour(second)
                span = b - a
                t = float(np.clip(((point - a) * span).sum() / max(float((span * span).sum()), 1e-9), 0.0, 1.0))
                if float(np.sqrt(((a + t * span - point) ** 2).sum())) < 0.08 * 255 * np.sqrt(3):
                    return True
        return False

    # 넓이가 작은 색 중 섞인 색과 아주 작은 색은 가장 가까운 주요 색으로: 색 사이 경계가 물결치지 않게(작은 강조색은 유지)
    major = [index for index, count in counts.items() if count / total >= minor] or [max(counts, key=lambda index: counts[index])]
    major += [index for index, count in counts.items() if index not in major and count / total >= 0.0015 and not blend(index, major)]

    # 눈으로 구분되지 않는 주요 색(넓은 한 색 면이 여러 색으로 갈린 것)은 넓은 쪽으로: 면 안에 가는 경계선이 생기지 않게
    lab = {index: _lab(colour(index)) for index in counts}

    def apart(one: int, other: int) -> float:
        return float(np.sqrt(((lab[one] - lab[other]) ** 2).sum()))

    kept: list[int] = []
    for index in sorted(major, key=lambda index: -counts[index]):
        if all(apart(index, other) >= merge for other in kept):
            kept.append(index)

    out = np.full(labels.shape, -1, dtype=np.int32)
    for index in counts:
        target = index if index in kept else min(kept, key=lambda other: apart(index, other))
        out[(labels == index) & solid] = kept.index(target)
    return Poster(out, [tuple(raw[index * 3:index * 3 + 3]) for index in kept])  # type: ignore[misc]


def _lab(rgb: Any) -> Any:
    """sRGB(0에서 255)를 CIE Lab으로(색 차이를 사람 눈 기준으로 재기 위해)."""
    np = _numpy()
    value = np.asarray(rgb, dtype=np.float64) / 255.0
    linear = np.where(value <= 0.04045, value / 12.92, ((value + 0.055) / 1.055) ** 2.4)
    xyz = linear @ np.array([[0.4124, 0.2126, 0.0193], [0.3576, 0.7152, 0.1192], [0.1805, 0.0722, 0.9505]])
    ratio = xyz / np.array([0.95047, 1.0, 1.08883])
    f = np.where(ratio > 0.008856, np.cbrt(ratio), 7.787 * ratio + 16 / 116)
    return np.array([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])])


def _boundary_loops(mask: Any) -> list[list[tuple[int, int]]]:
    """참인 영역의 경계(픽셀 모서리 격자)를 닫힌 꼭짓점 목록으로. 바깥과 구멍 모두(채우기 규칙 evenodd로 그림)."""
    np = _numpy()
    padded = np.pad(mask, 1)
    inside = padded[1:-1, 1:-1]
    edges: dict[tuple[int, int], list[tuple[int, int]]] = {}

    def add(ys: Any, xs: Any, start: tuple[int, int], end: tuple[int, int]) -> None:
        for y, x in zip(ys.tolist(), xs.tolist(), strict=True):
            edges.setdefault((x + start[0], y + start[1]), []).append((x + end[0], y + end[1]))

    # 시계 방향(화면 좌표): 위 변은 왼쪽에서 오른쪽, 오른쪽 변은 아래로, 아래 변은 왼쪽으로, 왼쪽 변은 위로
    add(*np.nonzero(inside & ~padded[:-2, 1:-1]), (0, 0), (1, 0))
    add(*np.nonzero(inside & ~padded[1:-1, 2:]), (1, 0), (1, 1))
    add(*np.nonzero(inside & ~padded[2:, 1:-1]), (1, 1), (0, 1))
    add(*np.nonzero(inside & ~padded[1:-1, :-2]), (0, 1), (0, 0))
    loops = []
    while edges:
        start = next(iter(edges))
        point, previous = start, None
        loop = [start]
        while True:
            outgoing = edges[point]
            if len(outgoing) > 1 and previous is not None:
                # 대각선으로만 닿은 두 픽셀이 만나는 점: 오른쪽으로 꺾는 변을 골라 영역을 나눈다
                dx, dy = point[0] - previous[0], point[1] - previous[1]
                right = (point[0] - dy, point[1] + dx)
                nxt = right if right in outgoing else outgoing[0]
            else:
                nxt = outgoing[0]
            outgoing.remove(nxt)
            if not outgoing:
                del edges[point]
            previous, point = point, nxt
            if point == start:
                break
            loop.append(point)
        loops.append(loop)
    return loops


def _area(points: list[tuple[float, float]]) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True))) / 2


def _simplify(points: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    """닫힌 꺾은선 단순화(Ramer-Douglas-Peucker, 가장 먼 두 점에서 나눠 처리)."""
    if len(points) < 5:
        return points

    def rdp(chain: list[tuple[float, float]]) -> list[tuple[float, float]]:
        keep = [False] * len(chain)
        keep[0] = keep[-1] = True
        stack = [(0, len(chain) - 1)]
        while stack:
            first, last = stack.pop()
            (x1, y1), (x2, y2) = chain[first], chain[last]
            length = max(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5, 1e-9)
            best, index = -1.0, -1
            for i in range(first + 1, last):
                x0, y0 = chain[i]
                distance = abs((y2 - y1) * x0 - (x2 - x1) * y0 + x2 * y1 - y2 * x1) / length
                if distance > best:
                    best, index = distance, i
            if best > tolerance:
                keep[index] = True
                stack += [(first, index), (index, last)]
        return [point for point, kept in zip(chain, keep, strict=True) if kept]

    far = max(range(len(points)), key=lambda i: (points[i][0] - points[0][0]) ** 2 + (points[i][1] - points[0][1]) ** 2)
    first = rdp(points[:far + 1])
    second = rdp(points[far:] + [points[0]])
    return first[:-1] + second[:-1]


def _smooth_path(points: list[tuple[float, float]], corner: float) -> str:
    """꼭짓점 사이를 이차 곡선으로 부드럽게. 각이 ``corner`` 도보다 날카로운 꼭짓점은 그대로 뾰족하게."""
    def fmt(point: tuple[float, float]) -> str:
        return f"{point[0]:.1f} {point[1]:.1f}"

    count = len(points)
    mids = [((points[i][0] + points[(i + 1) % count][0]) / 2, (points[i][1] + points[(i + 1) % count][1]) / 2) for i in range(count)]
    parts = [f"M{fmt(mids[-1])}"]
    for i in range(count):
        before, here, after = points[i - 1], points[i], points[(i + 1) % count]
        ax, ay, bx, by = before[0] - here[0], before[1] - here[1], after[0] - here[0], after[1] - here[1]
        norm = max(math.hypot(ax, ay) * math.hypot(bx, by), 1e-9)
        angle = math.degrees(math.acos(max(-1.0, min(1.0, (ax * bx + ay * by) / norm))))
        if angle < corner:
            parts.append(f"L{fmt(here)}L{fmt(mids[i])}")
        else:
            parts.append(f"Q{fmt(here)} {fmt(mids[i])}")
    return "".join(parts) + "Z"


def _relax(points: list[tuple[float, float]], rounds: int) -> list[tuple[float, float]]:
    """픽셀 계단을 이웃 꼭짓점과 평균해 매끈하게(진짜 모서리는 몇 픽셀 안에서만 둥글어짐)."""
    count = len(points)
    for _ in range(rounds):
        points = [((points[i - 1][0] + 2 * points[i][0] + points[(i + 1) % count][0]) / 4,
                   (points[i - 1][1] + 2 * points[i][1] + points[(i + 1) % count][1]) / 4) for i in range(count)]
    return points


def trace(poster: Poster, *, tolerance: float = 0.6, corner: float = 70.0, rounds: int = 3, min_area: float = 12.0) -> str:
    """색 번호 그림을 SVG로. 넓은 색부터 아래에 깔고, 각 층은 자기 색과 위에 올 색의 영역을 합친 모양(색 사이 틈 방지)."""
    np = _numpy()
    height, width = poster.labels.shape
    areas = [(int((poster.labels == index).sum()), index) for index in range(len(poster.palette))]
    order = [index for _, index in sorted(areas, reverse=True)]
    layers = []
    for position, index in enumerate(order):
        mask = np.isin(poster.labels, order[position:])
        loops = []
        for loop in _boundary_loops(mask):
            points = [(float(x), float(y)) for x, y in loop]
            if _area(points) < min_area:
                continue
            simple = _simplify(_relax(points, rounds), tolerance)
            if len(simple) >= 3:
                loops.append(_smooth_path(simple, corner))
        if loops:
            red, green, blue = poster.palette[index]
            layers.append(f'<path fill="#{red:02X}{green:02X}{blue:02X}" fill-rule="evenodd" d="{"".join(loops)}"/>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">{"".join(layers)}</svg>'


def symbol_svg(data: bytes, key: tuple[int, int, int]) -> str:
    """모델이 그린 그림에서 심볼 SVG까지."""
    cut = cut_out(data, key)
    share = coverage(cut)
    if share < 0.01:
        raise ImageModelError("배경을 지우니 남은 그림이 거의 없음: 설명을 바꿔 다시 만들기")
    if share > 0.97:
        raise ImageModelError("그림에서 배경을 찾지 못함(배경이 단색이 아님): 다시 만들기")
    return trace(posterize(square_crop(cut)))


# --- 통신 공용 ----------------------------------------------------------------------------


def _request(url: str, *, data: Any = None, headers: dict[str, str] | None = None, method: str | None = None) -> urllib.request.Request:
    body = json.dumps(data).encode("utf-8") if data is not None else None
    merged = {"User-Agent": f"debutkit/{__version__}", **({"Content-Type": "application/json"} if body is not None else {}), **(headers or {})}
    return urllib.request.Request(url, data=body, headers=merged, method=method or ("POST" if body is not None else "GET"))


def _read(response: Any, limit: int = IMAGE_LIMIT) -> bytes:
    data = response.read(limit + 1)
    if len(data) > limit:
        raise ImageModelError("받은 응답이 너무 큼")
    return data


def _json(opener: Opener, request: urllib.request.Request, timeout: float) -> Any:
    with opener(request, timeout=timeout) as response:
        return json.loads(_read(response, 20_000_000).decode("utf-8"))


# --- ComfyUI ------------------------------------------------------------------------------

COMFY_DEFAULT = "http://127.0.0.1:8188"
_ADDRESS = re.compile(r"^https?://[A-Za-z0-9.\-\[\]:]+(:\d{1,5})?/?$")
COMFY_FILES = "huggingface.co/Comfy-Org/Qwen-Image_ComfyUI의 split_files 폴더"


def check_address(value: Any) -> str:
    text = (value or COMFY_DEFAULT).strip() if isinstance(value, str) or value is None else ""
    if not _ADDRESS.match(text):
        raise ImageModelError(f"ComfyUI 주소 형식: {COMFY_DEFAULT} 처럼 http://주소:포트")
    return text.rstrip("/")


def _options(info: dict[str, Any], node: str, field: str) -> list[str]:
    """/object_info의 선택 항목 목록(예전 형식 [[...]]과 새 형식 ["COMBO", {"options": [...]}] 모두)."""
    try:
        spec = info[node]["input"]["required"][field]
    except (KeyError, TypeError):
        return []
    if isinstance(spec, list) and spec:
        if isinstance(spec[0], list):
            return [str(item) for item in spec[0]]
        if spec[0] == "COMBO" and len(spec) > 1 and isinstance(spec[1], dict):
            return [str(item) for item in spec[1].get("options", [])]
    return []


def _pick(names: list[str], must: tuple[str, ...], *, avoid: tuple[str, ...] = (), prefer: tuple[str, ...] = ()) -> str | None:
    found = [name for name in names if all(word in name.lower() for word in must) and not any(word in name.lower() for word in avoid)]
    found.sort(key=lambda name: (-sum(word in name.lower() for word in prefer), name))
    return found[0] if found else None


#: 연구용 라이선스(Qwen-Image-2.1)와 편집, 레이어 모델은 쓰지 않는다
_AVOID = ("edit", "layered", "2.1", "2_1", "control", "inpaint", "lightning")


def comfy_plan(info: dict[str, Any], quality: str) -> dict[str, Any]:
    """ComfyUI에 있는 파일로 Qwen-Image 작업 설정. 없으면 안내와 함께 실패."""
    unet = _pick(_options(info, "UNETLoader", "unet_name"), ("qwen", "image"), avoid=_AVOID, prefer=("2512",))
    loader = "UNETLoader"
    if unet is None:
        unet = _pick(_options(info, "UnetLoaderGGUF", "unet_name"), ("qwen", "image"), avoid=_AVOID, prefer=("2512",))
        loader = "UnetLoaderGGUF"
    clip = _pick(_options(info, "CLIPLoader", "clip_name"), ("qwen",), avoid=("edit",), prefer=("2.5_vl", "2.5-vl", "vl"))
    vae = _pick(_options(info, "VAELoader", "vae_name"), ("qwen", "vae"))
    missing = [label for label, value in (("diffusion_models의 qwen_image 모델", unet), ("text_encoders의 qwen_2.5_vl 모델", clip),
                                          ("vae의 qwen_image_vae", vae)) if value is None]
    if missing:
        raise ImageModelError(f"ComfyUI에 Qwen-Image 파일이 없음: {', '.join(missing)}. {COMFY_FILES}에서 받아 ComfyUI의 models 폴더에 넣고 "
                              "ComfyUI를 다시 시작")
    if "qwen_image" not in _options(info, "CLIPLoader", "type"):
        raise ImageModelError("이 ComfyUI는 Qwen-Image를 지원하지 않음: ComfyUI를 최신 버전으로 업데이트")
    lora = _pick(_options(info, "LoraLoaderModelOnly", "lora_name"), ("qwen", "lightning"), avoid=("edit", "2.1", "2_1"), prefer=("8step",)) \
        if quality == "fast" else None
    if lora:
        steps, cfg, label = (4 if "4step" in lora.lower() and "8step" not in lora.lower() else 8), 1.0, f"Qwen-Image + {lora}"
    else:
        steps, cfg, label = (20 if quality == "fast" else 30), 2.5, f"Qwen-Image {unet}"
    return {"unet": unet, "loader": loader, "clip": clip, "vae": vae, "lora": lora, "steps": steps, "cfg": cfg,
            "size": 1024 if quality == "fast" else 1328, "label": label}


def comfy_workflow(plan: dict[str, Any], prompt: str, seed: int) -> dict[str, Any]:
    """ComfyUI API 형식 작업(Qwen-Image 기본 예제 구성)."""
    model_node = ["1", 0]
    flow: dict[str, Any] = {
        "1": {"class_type": plan["loader"], "inputs": {"unet_name": plan["unet"], **({"weight_dtype": "default"} if plan["loader"] == "UNETLoader" else {})}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": plan["clip"], "type": "qwen_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": plan["vae"]}},
    }
    if plan["lora"]:
        flow["4"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": model_node, "lora_name": plan["lora"], "strength_model": 1.0}}
        model_node = ["4", 0]
    flow.update({
        "5": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": model_node, "shift": 3.1}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE if plan["cfg"] > 1 else "", "clip": ["2", 0]}},
        "8": {"class_type": "EmptySD3LatentImage", "inputs": {"width": plan["size"], "height": plan["size"], "batch_size": 1}},
        "9": {"class_type": "KSampler", "inputs": {"model": ["5", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["8", 0],
                                                    "seed": seed, "steps": plan["steps"], "cfg": plan["cfg"], "sampler_name": "euler",
                                                    "scheduler": "simple", "denoise": 1.0}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}},
        "11": {"class_type": "SaveImage", "inputs": {"images": ["10", 0], "filename_prefix": "debutkit_logo"}},
    })
    return flow


def _comfy_error(status: dict[str, Any]) -> str:
    for message in status.get("messages") or []:
        if isinstance(message, list) and len(message) == 2 and message[0] == "execution_error" and isinstance(message[1], dict):
            text = str(message[1].get("exception_message") or "").strip()
            if "out of memory" in text.lower() or "allocation on device" in text.lower():
                return "ComfyUI 그래픽 메모리 부족: 다른 프로그램을 닫거나 더 작은 모델(fp8, GGUF) 사용"
            return f"ComfyUI 실행 오류({message[1].get('node_type', '')}): {text[:200]}"
    return "ComfyUI 실행 오류: ComfyUI 창의 기록 확인"


def comfy_image(address: Any, prompt: str, quality: str, *, opener: Opener = urllib.request.urlopen, seed: int | None = None,
                timeout: float = 1800.0, poll: float = 1.0, sleep: Callable[[float], None] = time.sleep,
                clock: Callable[[], float] = time.monotonic) -> Made:
    """ComfyUI에서 그림 1장. ``timeout`` 은 전체 대기 시간(그래픽카드에 따라 몇 분)."""
    base = check_address(address)
    seed = secrets.randbelow(2**31) if seed is None else seed
    try:
        info = {}
        for node in ("UNETLoader", "UnetLoaderGGUF", "CLIPLoader", "VAELoader", "LoraLoaderModelOnly"):
            try:
                info.update(_json(opener, _request(f"{base}/object_info/{node}"), 15))
            except urllib.error.HTTPError:
                continue  # 설치되지 않은 노드(예: GGUF)
        if "UNETLoader" not in info:
            raise ImageModelError(f"{base}에서 ComfyUI 응답이 없음: ComfyUI 실행 여부와 주소 확인")
        plan = comfy_plan(info, quality)
        client = secrets.token_hex(8)
        try:
            queued = _json(opener, _request(f"{base}/prompt", data={"prompt": comfy_workflow(plan, prompt, seed), "client_id": client}), 30)
        except urllib.error.HTTPError as error:
            detail = error.read(4000).decode("utf-8", "replace")
            try:
                message = json.loads(detail).get("error", {}).get("message", detail)
            except (ValueError, AttributeError):
                message = detail
            raise ImageModelError(f"ComfyUI가 작업을 받지 않음: {str(message)[:200]}") from None
        prompt_id = str(queued.get("prompt_id") or "")
        if not prompt_id:
            raise ImageModelError("ComfyUI 응답에 작업 번호가 없음")
        deadline = clock() + timeout
        while True:
            history = _json(opener, _request(f"{base}/history/{urllib.parse.quote(prompt_id)}"), 30)
            entry = history.get(prompt_id) if isinstance(history, dict) else None
            if entry:
                status = entry.get("status") or {}
                if status.get("status_str") == "error":
                    raise ImageModelError(_comfy_error(status))
                images = [image for output in (entry.get("outputs") or {}).values() for image in (output.get("images") or [])]
                if images:
                    picked = images[0]
                    query = urllib.parse.urlencode({"filename": picked.get("filename", ""), "subfolder": picked.get("subfolder", ""),
                                                    "type": picked.get("type", "output")})
                    with opener(_request(f"{base}/view?{query}"), timeout=60) as response:
                        return Made(_read(response), f"{plan['label']} (ComfyUI)", seed, prompt)
                if status.get("completed"):
                    raise ImageModelError("ComfyUI 작업이 그림 없이 끝남")
            if clock() > deadline:
                raise ImageModelError(f"ComfyUI 작업이 {timeout / 60:.0f}분 안에 끝나지 않음: ComfyUI 창에서 진행 확인")
            sleep(poll)
    except urllib.error.HTTPError as error:
        raise ImageModelError(f"ComfyUI 요청 오류({error.code})") from None
    except (urllib.error.URLError, OSError):
        raise ImageModelError(f"ComfyUI에 연결하지 못함({base}): ComfyUI 실행 여부와 주소 확인") from None
    except ValueError as error:
        if isinstance(error, ImageModelError):
            raise
        raise ImageModelError("ComfyUI 응답을 읽지 못함") from None


# --- Hugging Face Space(공개 데모) ---------------------------------------------------------


@dataclass(frozen=True)
class SpaceModel:
    space: str
    label: str
    steps: int
    guidance: float


#: 같은 /infer 입력(지시문, 시드, 무작위 시드, 비율, 가이던스, 단계, 지시문 다듬기)을 쓰는 Space. 앞의 것이 멈춰 있으면 다음 것
SPACES: dict[str, tuple[SpaceModel, ...]] = {
    "fast": (SpaceModel("multimodalart/Qwen-Image-Fast", "Qwen-Image + Lightning 8단계", 8, 1.0),),
    "best": (SpaceModel("Qwen/Qwen-Image-2512", "Qwen-Image-2512", 40, 4.0), SpaceModel("Qwen/Qwen-Image", "Qwen-Image", 40, 4.0)),
}
SPACE_PARAMETERS = ["prompt", "seed", "randomize_seed", "aspect_ratio", "guidance_scale", "num_inference_steps", "prompt_enhance"]
_DOWN = {"RUNTIME_ERROR", "BUILD_ERROR", "CONFIG_ERROR", "NO_APP_FILE", "PAUSED", "STOPPED", "DELETING"}


def _space_error(title: str, message: str, token: str) -> str:
    text = _mask(f"{title} {message}", token).strip()
    lowered = text.lower()
    if "zerogpu" in lowered and ("quota" in lowered or "limit" in lowered):
        return ("Hugging Face 무료 GPU 사용 한도 초과: 한도는 첫 사용 24시간 뒤 다시 채워짐(무료 계정 하루 5분, PRO 40분). "
                "빠름 품질이 한도를 덜 씀. " + text[:160])
    return "Hugging Face Space 오류: " + (text[:240] or "원인 미상(잠시 뒤 다시 시도)")


def _host(space: str, token: str, opener: Opener) -> str:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        meta = _json(opener, _request(f"https://huggingface.co/api/spaces/{space}", headers=headers), 30)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise ImageModelError("Hugging Face 토큰이 올바르지 않음: huggingface.co 설정의 Access Tokens에서 다시 복사해 저장") from None
        raise ImageModelError(f"Hugging Face Space 정보를 받지 못함({error.code})") from None
    stage = str((meta.get("runtime") or {}).get("stage") or "")
    if stage in _DOWN:
        raise LookupError(stage)
    host = str(meta.get("host") or "")
    if not host.startswith("https://") or not host.endswith(".hf.space"):
        raise ImageModelError("Hugging Face Space 주소가 예상과 다름")
    return host.rstrip("/")


def _space_call(model: SpaceModel, host: str, token: str, prompt: str, seed: int, opener: Opener, timeout: float) -> bytes:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    config = _json(opener, _request(f"{host}/config", headers=headers), 30)
    prefix = "/" + str(config.get("api_prefix") or "/gradio_api").strip("/")
    dependencies = config.get("dependencies") or []
    found = next((index for index, item in enumerate(dependencies) if isinstance(item, dict) and item.get("api_name") == "infer"), None)
    if found is None:
        raise ImageModelError(f"Space({model.space})의 입력 형식이 바뀜: debutkit 새 버전 확인")
    fn_index = dependencies[found].get("id", found)
    info = _json(opener, _request(f"{host}{prefix}/info", headers=headers), 30)
    names = [item.get("parameter_name") for item in ((info.get("named_endpoints") or {}).get("/infer") or {}).get("parameters", [])]
    if names != SPACE_PARAMETERS:
        raise ImageModelError(f"Space({model.space})의 입력 형식이 바뀜: debutkit 새 버전 확인")
    session = secrets.token_hex(6)
    body = {"data": [prompt, seed, False, "1:1", model.guidance, model.steps, False], "fn_index": fn_index, "session_hash": session,
            "event_data": None, "trigger_id": None}
    try:
        _json(opener, _request(f"{host}{prefix}/queue/join", data=body, headers=headers), 60)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise ImageModelError("Hugging Face 토큰이 올바르지 않음: huggingface.co 설정의 Access Tokens에서 다시 복사해 저장") from None
        if error.code == 429:
            raise ImageModelError("Hugging Face 요청이 많음: 잠시 뒤 다시 시도") from None
        raise ImageModelError(f"Hugging Face Space가 요청을 받지 않음({error.code})") from None
    output: dict[str, Any] | None = None
    with opener(_request(f"{host}{prefix}/queue/data?session_hash={session}", headers=headers), timeout=timeout) as stream:
        for raw in stream:
            line = raw.decode("utf-8", "replace").strip() if isinstance(raw, bytes) else str(raw).strip()
            if not line.startswith("data:"):
                continue
            try:
                message = json.loads(line[5:])
            except ValueError:
                continue
            kind = message.get("msg")
            if kind == "unexpected_error":
                raise ImageModelError(_space_error("", str(message.get("message") or ""), token))
            if kind == "process_completed":
                result = message.get("output") or {}
                if not message.get("success"):
                    raise ImageModelError(_space_error(str(message.get("title") or ""), str(result.get("error") or ""), token))
                output = result
                break
    if output is None:
        raise ImageModelError("Hugging Face Space 응답이 중간에 끊김: 다시 시도")
    picture = (output.get("data") or [None])[0]
    if not isinstance(picture, dict):
        raise ImageModelError("Hugging Face Space 응답에 그림이 없음")
    url = str(picture.get("url") or "")
    if not url and picture.get("path"):
        url = f"{host}{prefix}/file={picture['path']}"
    if urllib.parse.urlsplit(url).netloc != urllib.parse.urlsplit(host).netloc:
        raise ImageModelError("Hugging Face Space가 다른 주소의 그림을 보냄")
    with opener(_request(url, headers=headers), timeout=120) as response:
        return _read(response)


def space_image(token: str, prompt: str, quality: str, *, opener: Opener = urllib.request.urlopen, seed: int | None = None,
                timeout: float = 900.0) -> Made:
    """Hugging Face Space에서 그림 1장(사용자 토큰의 무료 GPU 한도 사용)."""
    seed = secrets.randbelow(2**31) if seed is None else seed
    stopped = []
    for model in SPACES[quality]:
        try:
            try:
                host = _host(model.space, token, opener)
            except LookupError as stage:
                stopped.append(f"{model.space}({stage})")
                continue
            data = _space_call(model, host, token, prompt, seed, opener, timeout)
        except urllib.error.HTTPError as error:
            raise ImageModelError(f"Hugging Face Space 요청 오류({error.code})") from None
        except (urllib.error.URLError, OSError) as error:
            raise ImageModelError(f"Hugging Face에 연결하지 못함: 인터넷 연결 확인({_mask(str(error), token)})") from None
        except ValueError as error:
            if isinstance(error, ImageModelError):
                raise
            raise ImageModelError("Hugging Face Space 응답을 읽지 못함") from None
        return Made(data, f"{model.label} (Hugging Face Space {model.space})", seed, prompt)
    raise ImageModelError("Hugging Face Space가 지금 동작하지 않음: " + ", ".join(stopped) + ". 잠시 뒤 다시 시도하거나 다른 품질 선택")
