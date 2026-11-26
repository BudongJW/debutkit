"""게임 패키지 배경 그림 만들기(src/debutkit/overlay/static/games/scene-*.svg).

    python packaging/build_game_scenes.py

- 게임마다 그 게임을 떠올리게 하는 장면(색, 지형, 구도)을 도형으로 그린 1920x1080 SVG. 패키지 미리보기와 대기, 자리 비움, 엔딩 화면 배경에 쓴다
- 공식 로고, 캐릭터, 게임 화면, 공식 그림은 쓰지 않고 모두 여기서 그린 도형. 같은 결과가 나오도록 난수 씨앗을 고정
"""

from __future__ import annotations

import math
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "src" / "debutkit" / "overlay" / "static" / "games"
W, H = 1920, 1080


def svg(body: str, defs: str = "") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" preserveAspectRatio="xMidYMid slice">'
            f"<defs>{defs}</defs>{body}</svg>\n")


def lin(name: str, stops: list[tuple[float, str]], x2: float = 0, y2: float = 1, extra: str = "") -> str:
    inner = "".join(f'<stop offset="{offset}" stop-color="{color}"/>' for offset, color in stops)
    return f'<linearGradient id="{name}" x1="0" y1="0" x2="{x2}" y2="{y2}" {extra}>{inner}</linearGradient>'


def rad(name: str, stops: list[tuple[float, str, float]], cx=0.5, cy=0.5, r=0.5) -> str:
    inner = "".join(f'<stop offset="{offset}" stop-color="{color}" stop-opacity="{opacity}"/>' for offset, color, opacity in stops)
    return f'<radialGradient id="{name}" cx="{cx}" cy="{cy}" r="{r}">{inner}</radialGradient>'


def poly(points, fill: str, extra: str = "") -> str:
    return f'<polygon points="{" ".join(f"{x:.0f},{y:.0f}" for x, y in points)}" fill="{fill}" {extra}/>'


def hexagon(cx: float, cy: float, rx: float, ry: float) -> list[tuple[float, float]]:
    return [(cx + rx * math.cos(math.radians(60 * i + 30)), cy + ry * math.sin(math.radians(60 * i + 30))) for i in range(6)]


# --------------------------------------------------------------------------- 발로란트: 노을 진 지중해 도시, 각진 벽, 붉은 기하 조각
def valorant() -> str:
    rng = random.Random(1)
    defs = lin("sky", [(0, "#0f1923"), (0.55, "#3b2f45"), (0.82, "#c9605f"), (1, "#f1a07a")]) + \
        lin("wall", [(0, "#4b5563"), (1, "#2a333d")]) + lin("floor", [(0, "#3a4149"), (1, "#151c23")]) + \
        rad("haze", [(0, "#ffb38a", 0.55), (1, "#ffb38a", 0)], 0.5, 0.75, 0.5)
    body = ['<rect width="1920" height="1080" fill="url(#sky)"/>', '<rect width="1920" height="1080" fill="url(#haze)"/>']
    # 먼 지붕 실루엣
    x = 0
    roofs = []
    while x < W:
        w = rng.randint(70, 160)
        h = rng.randint(60, 170)
        roofs.append(f'<rect x="{x}" y="{640 - h}" width="{w}" height="{h + 20}" fill="#2b2a3a"/>')
        if rng.random() < 0.4:
            roofs.append(poly([(x, 640 - h), (x + w / 2, 640 - h - 40), (x + w, 640 - h)], "#2b2a3a"))
        x += w - 6
    body += roofs
    body.append('<rect x="0" y="640" width="1920" height="440" fill="url(#floor)"/>')
    # 바닥 원근선
    for i in range(-8, 9):
        body.append(f'<line x1="{960 + i * 40}" y1="640" x2="{960 + i * 260}" y2="1080" stroke="#ece8e1" stroke-opacity="0.06" stroke-width="2"/>')
    # 앞쪽 각진 벽(모서리를 깎은 판)
    body.append(poly([(0, 300), (520, 300), (560, 340), (560, 1080), (0, 1080)], "url(#wall)"))
    body.append(poly([(1920, 260), (1380, 260), (1340, 300), (1340, 1080), (1920, 1080)], "url(#wall)"))
    for y in range(360, 1080, 90):
        body.append(f'<line x1="0" y1="{y}" x2="560" y2="{y}" stroke="#ece8e1" stroke-opacity="0.07" stroke-width="3"/>')
        body.append(f'<line x1="1340" y1="{y - 30}" x2="1920" y2="{y - 30}" stroke="#ece8e1" stroke-opacity="0.07" stroke-width="3"/>')
    # 벽의 큰 거점 글자
    body.append('<text x="1630" y="640" font-family="Bahnschrift, Arial Narrow, sans-serif" font-weight="700" font-size="300" fill="#ff4655" '
                'fill-opacity="0.85" text-anchor="middle">A</text>')
    # 가운데 상자 엄폐물
    body.append(poly([(820, 700), (1100, 700), (1120, 720), (1120, 860), (800, 860), (800, 720)], "#5a4a3c"))
    body.append('<rect x="830" y="730" width="260" height="10" fill="#ece8e1" fill-opacity="0.15"/>')
    # 붉은 기하 조각(화면 가장자리)
    body.append(poly([(0, 0), (380, 0), (0, 220)], "#ff4655", 'fill-opacity="0.92"'))
    body.append(poly([(1920, 1080), (1500, 1080), (1920, 820)], "#ff4655", 'fill-opacity="0.92"'))
    body.append(poly([(430, 0), (470, 0), (60, 240), (20, 240)], "#ece8e1", 'fill-opacity="0.5"'))
    body.append(poly([(1450, 1080), (1490, 1080), (1880, 850), (1840, 850)], "#ece8e1", 'fill-opacity="0.5"'))
    # 조준점
    body.append('<g stroke="#ece8e1" stroke-width="4" stroke-linecap="square"><line x1="960" y1="512" x2="960" y2="528"/><line x1="960" y1="552" x2="960" y2="568"/>'
                '<line x1="932" y1="540" x2="948" y2="540"/><line x1="972" y1="540" x2="988" y2="540"/></g>')
    return svg("".join(body), defs)


# --------------------------------------------------------------------------- 리그 오브 레전드: 위에서 본 정글과 강, 세 갈래 길, 금빛 마법진
def lol() -> str:
    rng = random.Random(2)
    defs = rad("glow", [(0, "#0ac8b9", 0.5), (1, "#0ac8b9", 0)], 0.5, 0.5, 0.5) + lin("vign", [(0, "#010a13"), (1, "#010a13")]) + \
        rad("dark", [(0, "#000000", 0), (0.7, "#000000", 0.25), (1, "#010a13", 0.85)], 0.5, 0.5, 0.72)
    body = ['<rect width="1920" height="1080" fill="#16301f"/>']
    for _ in range(260):  # 정글 숲 덩어리
        x, y, r = rng.randint(-40, 1960), rng.randint(-40, 1120), rng.randint(18, 60)
        body.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{rng.choice(["#1d3b26", "#122719", "#244a2d", "#0f2215"])}"/>')
    # 강(왼쪽 위에서 오른쪽 아래)
    body.append('<path d="M-60 120 C420 300 600 420 960 540 C1320 660 1500 780 1980 960 L1980 1120 C1500 900 1300 780 960 680 C620 580 380 440 -60 290 Z" '
                'fill="#1b5c6b" fill-opacity="0.9"/>')
    body.append('<path d="M-60 200 C420 360 620 470 960 600 C1300 720 1500 840 1980 1030" fill="none" stroke="#5fe3f0" stroke-opacity="0.35" stroke-width="5"/>')
    # 세 갈래 돌길
    lane = 'fill="none" stroke="#9a8a66" stroke-width="64" stroke-linecap="round" stroke-linejoin="round" stroke-opacity="0.92"'
    body.append(f'<path d="M140 1080 L140 140 L1920 140" {lane}/>')
    body.append(f'<path d="M0 940 L1780 940 L1780 0" {lane}/>')
    body.append(f'<path d="M120 1060 L1800 40" {lane}/>')
    body.append('<path d="M120 1060 L1800 40" fill="none" stroke="#c8b98a" stroke-width="3" stroke-dasharray="6 26" stroke-opacity="0.6"/>')
    # 포탑 자리(육각 돌)
    for x, y in ((140, 520), (700, 140), (1240, 940), (1780, 560), (560, 790), (1360, 300)):
        body.append(poly(hexagon(x, y, 34, 34), "#3a3f45", 'stroke="#c8aa6e" stroke-width="4"'))
        body.append(f'<circle cx="{x}" cy="{y}" r="10" fill="#0ac8b9"/>')
    # 가운데 금빛 마법진
    body.append('<circle cx="960" cy="560" r="230" fill="url(#glow)"/>')
    body.append('<g fill="none" stroke="#c8aa6e" stroke-opacity="0.85"><circle cx="960" cy="560" r="170" stroke-width="4"/>'
                '<circle cx="960" cy="560" r="150" stroke-width="1.5" stroke-dasharray="4 10"/><circle cx="960" cy="560" r="96" stroke-width="3"/></g>')
    body.append(poly([(960, 400), (1090, 560), (960, 720), (830, 560)], "none", 'stroke="#c8aa6e" stroke-width="3"'))
    body.append(poly([(960, 470), (1030, 560), (960, 650), (890, 560)], "#0ac8b9", 'fill-opacity="0.6"'))
    body.append('<rect width="1920" height="1080" fill="url(#dark)"/>')
    # 금빛 테두리 장식
    body.append('<g fill="none" stroke="#c8aa6e"><rect x="28" y="28" width="1864" height="1024" stroke-width="3"/>'
                '<rect x="40" y="40" width="1840" height="1000" stroke-width="1" stroke-opacity="0.6"/></g>')
    for x, y in ((28, 28), (1892, 28), (28, 1052), (1892, 1052)):
        body.append(poly([(x, y - 22), (x + 22, y), (x, y + 22), (x - 22, y)], "#010a13", 'stroke="#c8aa6e" stroke-width="3"'))
    return svg("".join(body), defs)


# --------------------------------------------------------------------------- 오버워치: 맑은 하늘의 미래 도시, 흰 탑과 주황 띠, 육각 방벽
def overwatch() -> str:
    rng = random.Random(3)
    defs = lin("sky", [(0, "#6ec3f5"), (0.6, "#bfe6fb"), (1, "#f4fbff")]) + rad("sun", [(0, "#ffffff", 1), (0.25, "#fff1c9", 0.8), (1, "#fff1c9", 0)], 0.78, 0.22, 0.35) + \
        lin("tower", [(0, "#ffffff"), (1, "#d6dee8")], 1, 0) + lin("ground", [(0, "#e7ecf2"), (1, "#b8c3cf")])
    body = ['<rect width="1920" height="1080" fill="url(#sky)"/>', '<rect width="1920" height="1080" fill="url(#sun)"/>']
    # 먼 탑들
    for i in range(14):
        x = 40 + i * 140 + rng.randint(-20, 20)
        h = rng.randint(220, 520)
        w = rng.randint(70, 120)
        body.append(f'<rect x="{x}" y="{700 - h}" width="{w}" height="{h}" rx="{w // 2}" fill="#dde7f2"/>')
    # 앞쪽 큰 탑(둥근 모서리, 주황 띠, 파란 유리)
    for x, w, h in ((180, 220, 640), (1500, 260, 700), (760, 170, 480)):
        body.append(f'<rect x="{x}" y="{820 - h}" width="{w}" height="{h + 40}" rx="40" fill="url(#tower)" stroke="#c9d3de" stroke-width="3"/>')
        body.append(f'<rect x="{x}" y="{820 - h + 70}" width="{w}" height="22" fill="#f99e1a"/>')
        for row in range(3):
            body.append(f'<rect x="{x + 24}" y="{820 - h + 130 + row * 90}" width="{w - 48}" height="54" rx="12" fill="#4aa8e8" fill-opacity="0.75"/>')
    # 떠 있는 다리와 둥근 고리
    body.append('<path d="M400 520 C760 440 1160 440 1520 500" fill="none" stroke="#ffffff" stroke-width="26" stroke-linecap="round"/>')
    body.append('<path d="M400 520 C760 440 1160 440 1520 500" fill="none" stroke="#f99e1a" stroke-width="6" stroke-linecap="round"/>')
    body.append('<ellipse cx="1180" cy="300" rx="150" ry="150" fill="none" stroke="#ffffff" stroke-width="18" stroke-opacity="0.85"/>')
    # 광장
    body.append('<path d="M0 820 L1920 820 L1920 1080 L0 1080 Z" fill="url(#ground)"/>')
    for i in range(-10, 11):
        body.append(f'<line x1="{960 + i * 60}" y1="820" x2="{960 + i * 220}" y2="1080" stroke="#9aa7b6" stroke-opacity="0.35" stroke-width="2"/>')
    body.append('<path d="M0 820 H1920" stroke="#f99e1a" stroke-width="8"/>')
    # 육각 방벽(반투명)
    for row in range(5):
        for col in range(7):
            cx, cy = 1180 + col * 52 + (26 if row % 2 else 0), 560 + row * 45
            body.append(poly(hexagon(cx, cy, 28, 28), "#7fd0ff", 'fill-opacity="0.12" stroke="#4aa8e8" stroke-opacity="0.45" stroke-width="2"'))
    # 주황 사선 띠(가장자리)
    for i in range(4):
        body.append(poly([(0, 980 - i * 40), (220 - i * 30, 980 - i * 40), (180 - i * 30, 1010 - i * 40), (0, 1010 - i * 40)], "#f99e1a", f'fill-opacity="{0.9 - i * 0.2:.1f}"'))
    return svg("".join(body), defs)


# --------------------------------------------------------------------------- 하스스톤: 위에서 본 선술집 탁자, 돌판과 금 고리, 보석과 촛불
def hearthstone() -> str:
    rng = random.Random(4)
    defs = lin("plank", [(0, "#7a4e2a"), (1, "#5b3a1e")], 1, 0) + rad("board", [(0, "#efdcae", 1), (0.75, "#cdae74", 1), (1, "#8a6a3c", 1)], 0.5, 0.5, 0.5) + \
        rad("candle", [(0, "#ffd98a", 0.85), (1, "#ffb347", 0)], 0.5, 0.5, 0.5) + rad("vign", [(0.55, "#000000", 0), (1, "#1a0e05", 0.75)], 0.5, 0.5, 0.75)
    body = ['<rect width="1920" height="1080" fill="#5b3a1e"/>']
    for i in range(14):  # 나무 판자
        y = i * 80
        body.append(f'<rect x="0" y="{y}" width="1920" height="78" fill="url(#plank)" fill-opacity="{0.75 + rng.random() * 0.25:.2f}"/>')
        body.append(f'<line x1="0" y1="{y + 78}" x2="1920" y2="{y + 78}" stroke="#2a190b" stroke-width="4"/>')
        for _ in range(5):
            x = rng.randint(0, 1800)
            body.append(f'<path d="M{x} {y + rng.randint(15, 60)} q60 -10 120 0 t120 0" fill="none" stroke="#3b2412" stroke-opacity="0.35" stroke-width="2"/>')
    # 가운데 돌판(타원)과 금 고리
    body.append('<ellipse cx="960" cy="540" rx="720" ry="360" fill="#2a190b"/>')
    body.append('<ellipse cx="960" cy="540" rx="700" ry="342" fill="url(#board)" stroke="#d4a84b" stroke-width="10"/>')
    body.append('<ellipse cx="960" cy="540" rx="660" ry="310" fill="none" stroke="#8a6a3c" stroke-width="3" stroke-dasharray="14 10"/>')
    body.append('<line x1="300" y1="540" x2="1620" y2="540" stroke="#8a6a3c" stroke-width="4" stroke-opacity="0.6"/>')
    # 보석 자리(네 방향)
    for x, y in ((960, 196), (960, 884), (262, 540), (1658, 540)):
        body.append(f'<circle cx="{x}" cy="{y}" r="46" fill="#d4a84b" stroke="#2a190b" stroke-width="6"/>')
        body.append(poly([(x, y - 30), (x + 26, y), (x, y + 30), (x - 26, y)], "#2f7bd8", 'stroke="#123e7a" stroke-width="3"'))
        body.append(poly([(x, y - 30), (x + 10, y), (x, y)], "#9ccbff"))
    # 마나 수정(오른쪽 아래)
    for i in range(7):
        x, y = 1300 + i * 58, 990
        body.append(poly([(x, y - 34), (x + 22, y), (x, y + 34), (x - 22, y)], "#2f7bd8" if i < 5 else "#3a2a1a", 'stroke="#9ccbff" stroke-width="3"'))
    # 펼친 카드 뒷면(왼쪽 아래)
    for i in range(5):
        angle = -24 + i * 12
        body.append(f'<g transform="translate({360 + i * 70} 1010) rotate({angle})"><rect x="-70" y="-200" width="140" height="200" rx="14" fill="#6b3a1e" '
                    f'stroke="#d4a84b" stroke-width="6"/><circle cx="0" cy="-100" r="34" fill="none" stroke="#d4a84b" stroke-width="4"/></g>')
    # 촛불
    for x, y in ((140, 120), (1780, 120), (1780, 960)):
        body.append(f'<circle cx="{x}" cy="{y}" r="150" fill="url(#candle)"/><circle cx="{x}" cy="{y}" r="26" fill="#f6e7c4"/><circle cx="{x}" cy="{y}" r="9" fill="#ffb347"/>')
    body.append('<rect width="1920" height="1080" fill="url(#vign)"/>')
    return svg("".join(body), defs)


# --------------------------------------------------------------------------- 배틀그라운드: 위에서 본 전장 지도, 등고선, 격자, 안전 구역, 비행 경로, 보급 상자
def pubg() -> str:
    rng = random.Random(5)
    defs = ""
    body = ['<rect width="1920" height="1080" fill="#7c8556"/>']
    for _ in range(70):  # 밭과 숲 조각
        x, y, w, h = rng.randint(-50, 1900), rng.randint(-50, 1060), rng.randint(80, 260), rng.randint(60, 200)
        body.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{rng.choice(["#8d9562", "#6b7448", "#9a9a68", "#5d6a3e"])}" '
                    f'transform="rotate({rng.randint(-20, 20)} {x} {y})"/>')
    # 등고선
    for k in range(9):
        cx, cy = rng.choice([(520, 380), (1380, 720), (1500, 260)])
        r = 60 + k * 38
        points = []
        for a in range(0, 361, 10):
            wobble = r + 18 * math.sin(math.radians(a * 3 + k * 40))
            points.append(f"{cx + wobble * math.cos(math.radians(a)):.0f},{cy + wobble * 0.75 * math.sin(math.radians(a)):.0f}")
        body.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="#3d4428" stroke-opacity="0.45" stroke-width="2"/>')
    # 강과 길
    body.append('<path d="M-40 760 C300 700 520 820 820 760 C1120 700 1300 560 1960 600" fill="none" stroke="#5b86a0" stroke-width="40"/>')
    body.append('<path d="M200 -20 C260 300 420 520 380 1100 M-20 300 C600 330 1300 260 1960 380" fill="none" stroke="#d9cfa8" stroke-width="12"/>')
    for _ in range(40):  # 마을 건물
        x, y = rng.randint(250, 520), rng.randint(250, 500)
        body.append(f'<rect x="{x}" y="{y}" width="18" height="14" fill="#c9b48a" stroke="#4a4630" stroke-width="2"/>')
    # 격자와 좌표
    for i in range(1, 8):
        body.append(f'<line x1="{i * 240}" y1="0" x2="{i * 240}" y2="1080" stroke="#1c1f18" stroke-opacity="0.35" stroke-width="2"/>')
        body.append(f'<text x="{i * 240 - 120}" y="34" font-family="Bahnschrift, Arial Narrow, sans-serif" font-size="26" fill="#1c1f18" fill-opacity="0.7" text-anchor="middle">{"ABCDEFGH"[i - 1]}</text>')
    for j in range(1, 5):
        body.append(f'<line x1="0" y1="{j * 216}" x2="1920" y2="{j * 216}" stroke="#1c1f18" stroke-opacity="0.35" stroke-width="2"/>')
    # 안전 구역(흰 원)과 자기장(파란 원)
    body.append('<circle cx="1180" cy="520" r="300" fill="none" stroke="#ffffff" stroke-width="6"/>')
    body.append('<circle cx="1080" cy="560" r="520" fill="none" stroke="#3d7bff" stroke-width="8" stroke-opacity="0.8"/>')
    # 비행 경로
    body.append('<line x1="80" y1="120" x2="1860" y2="980" stroke="#ffffff" stroke-width="5" stroke-dasharray="26 18"/>')
    body.append(poly([(1860, 980), (1820, 940), (1810, 985)], "#ffffff"))
    # 보급 상자와 낙하산
    body.append('<path d="M640 300 Q700 200 760 300" fill="#e8e1ce" stroke="#4a4630" stroke-width="3"/>')
    body.append('<line x1="640" y1="300" x2="684" y2="380" stroke="#4a4630" stroke-width="2"/><line x1="760" y1="300" x2="716" y2="380" stroke="#4a4630" stroke-width="2"/>')
    body.append('<rect x="672" y="376" width="56" height="44" fill="#f2a900" stroke="#1c1f18" stroke-width="4"/>')
    body.append('<line x1="672" y1="398" x2="728" y2="398" stroke="#1c1f18" stroke-width="3"/>')
    return svg("".join(body), defs)


# --------------------------------------------------------------------------- 메이플스토리: 맑은 하늘의 떠 있는 풀밭 발판, 밧줄, 버섯, 구름
def maplestory() -> str:
    rng = random.Random(6)
    defs = lin("sky", [(0, "#7fcff8"), (1, "#e6f7ff")]) + lin("dirt", [(0, "#d39a5a"), (1, "#a8693a")]) + lin("hill", [(0, "#9fd77a"), (1, "#7cbf5b")])
    body = ['<rect width="1920" height="1080" fill="url(#sky)"/>']
    for _ in range(9):  # 몽실 구름
        x, y, s = rng.randint(0, 1800), rng.randint(40, 380), rng.uniform(0.7, 1.4)
        body.append(f'<g fill="#ffffff" fill-opacity="0.95" transform="translate({x} {y}) scale({s:.2f})"><circle cx="0" cy="20" r="40"/>'
                    '<circle cx="50" cy="0" r="55"/><circle cx="105" cy="22" r="40"/><rect x="0" y="20" width="105" height="40"/></g>')
    body.append('<path d="M0 760 C300 640 520 700 760 660 C1040 610 1300 700 1600 640 C1760 610 1860 640 1920 660 L1920 1080 L0 1080 Z" fill="url(#hill)"/>')

    def platform(x, y, w):
        return (f'<rect x="{x}" y="{y}" width="{w}" height="70" rx="18" fill="url(#dirt)"/>'
                f'<rect x="{x - 6}" y="{y - 12}" width="{w + 12}" height="30" rx="15" fill="#8bd05a" stroke="#5d9c3a" stroke-width="4"/>'
                + "".join(f'<circle cx="{x + 20 + i * 36}" cy="{y + 40}" r="5" fill="#8a5528" fill-opacity="0.5"/>' for i in range(w // 36)))

    for x, y, w in ((120, 560, 420), (700, 430, 380), (1280, 560, 460), (420, 820, 520), (1180, 860, 560)):
        body.append(platform(x, y, w))
    # 밧줄과 사다리
    body.append('<line x1="560" y1="575" x2="560" y2="820" stroke="#a8693a" stroke-width="8"/><line x1="1400" y1="575" x2="1400" y2="860" stroke="#a8693a" stroke-width="8"/>')
    for y in range(445, 560, 26):
        body.append(f'<line x1="940" y1="{y}" x2="980" y2="{y}" stroke="#a8693a" stroke-width="6"/>')
    body.append('<line x1="940" y1="445" x2="940" y2="560" stroke="#a8693a" stroke-width="6"/><line x1="980" y1="445" x2="980" y2="560" stroke="#a8693a" stroke-width="6"/>')
    # 버섯(얼굴 없는 주황 갓)
    for x, y, s in ((250, 548, 1.0), (1420, 548, 0.8), (620, 808, 1.1), (1300, 848, 0.9)):
        body.append(f'<g transform="translate({x} {y}) scale({s})"><rect x="-14" y="-40" width="28" height="40" rx="8" fill="#fff4dc"/>'
                    '<path d="M-46 -36 C-46 -86 46 -86 46 -36 Z" fill="#ff9a2e" stroke="#c96a1e" stroke-width="4"/>'
                    '<circle cx="-18" cy="-58" r="7" fill="#fff4dc"/><circle cx="14" cy="-64" r="9" fill="#fff4dc"/></g>')
    # 큰 나무
    body.append('<rect x="1700" y="440" width="60" height="260" fill="#8a5528"/><circle cx="1730" cy="420" r="130" fill="#6fbf4a"/>'
                '<circle cx="1660" cy="470" r="80" fill="#84cc5a"/><circle cx="1810" cy="470" r="80" fill="#84cc5a"/>')
    for _ in range(26):  # 반짝이
        x, y = rng.randint(0, 1920), rng.randint(0, 700)
        body.append(f'<path d="M{x} {y - 8} L{x + 2} {y - 2} L{x + 8} {y} L{x + 2} {y + 2} L{x} {y + 8} L{x - 2} {y + 2} L{x - 8} {y} L{x - 2} {y - 2} Z" fill="#fff6b0"/>')
    return svg("".join(body), defs)


# --------------------------------------------------------------------------- 로스트아크: 푸른 검정 밤하늘, 금빛 빛기둥, 떠 있는 유적과 고딕 성, 금 테두리
def lostark() -> str:
    rng = random.Random(7)
    defs = lin("sky", [(0, "#07080c"), (0.5, "#141b29"), (0.82, "#2b2a2e"), (1, "#7a5a2e")]) + \
        lin("beam", [(0, "#e9d5a5"), (1, "#c9a063")], 1, 0) + rad("halo", [(0, "#f6e6bd", 0.85), (0.3, "#c9a063", 0.45), (1, "#c9a063", 0)], 0.5, 0.45, 0.35)
    body = ['<rect width="1920" height="1080" fill="url(#sky)"/>']
    for _ in range(120):  # 별
        body.append(f'<circle cx="{rng.randint(0, 1920)}" cy="{rng.randint(0, 560)}" r="{rng.uniform(0.6, 2):.1f}" fill="#e9d5a5" fill-opacity="{rng.uniform(0.2, 0.8):.2f}"/>')
    body.append('<rect width="1920" height="1080" fill="url(#halo)"/>')
    body.append('<rect x="930" y="0" width="60" height="760" fill="url(#beam)" fill-opacity="0.55"/>')
    body.append('<rect x="952" y="0" width="16" height="760" fill="#fff4d6" fill-opacity="0.8"/>')
    # 별자리 선(항해 지도 느낌)
    stars = [(220, 160), (330, 230), (460, 190), (560, 280), (1420, 140), (1530, 220), (1650, 170), (1740, 260)]
    body.append(f'<polyline points="{" ".join(f"{x},{y}" for x, y in stars[:4])}" fill="none" stroke="#c9a063" stroke-opacity="0.5" stroke-width="2"/>')
    body.append(f'<polyline points="{" ".join(f"{x},{y}" for x, y in stars[4:])}" fill="none" stroke="#c9a063" stroke-opacity="0.5" stroke-width="2"/>')
    for x, y in stars:
        body.append(f'<circle cx="{x}" cy="{y}" r="5" fill="#e9d5a5"/>')
    # 떠 있는 유적 섬
    for x, y, w in ((300, 520, 260), (1500, 470, 300)):
        body.append(f'<path d="M{x} {y} L{x + w} {y} L{x + w * 0.7} {y + 110} L{x + w * 0.45} {y + 170} L{x + w * 0.25} {y + 90} Z" fill="#10141c"/>')
        for i in range(3):
            body.append(f'<rect x="{x + 30 + i * (w // 3)}" y="{y - 80 - i * 18}" width="22" height="{80 + i * 18}" fill="#141a24"/>')
    # 절벽과 성
    body.append('<path d="M0 1080 L0 780 L260 720 L420 780 L600 680 L760 720 L880 640 L1040 640 L1160 700 L1340 650 L1600 720 L1920 690 L1920 1080 Z" fill="#090b10"/>')
    for x, w, h in ((900, 50, 250), (960, 80, 330), (1050, 46, 210)):
        body.append(f'<rect x="{x}" y="{650 - h}" width="{w}" height="{h + 20}" fill="#07090d"/>')
        body.append(poly([(x - 6, 650 - h), (x + w / 2, 650 - h - 80), (x + w + 6, 650 - h)], "#07090d"))
        body.append(f'<rect x="{x + w / 2 - 4}" y="{650 - h + 50}" width="8" height="18" fill="#f99200" fill-opacity="0.85"/>')
    for _ in range(70):  # 금빛 빛 조각
        x, y, r = rng.randint(0, 1920), rng.randint(300, 1080), rng.uniform(1.5, 4)
        body.append(f'<circle cx="{x}" cy="{y}" r="{r:.1f}" fill="#e9d5a5" fill-opacity="{rng.uniform(0.25, 0.8):.2f}"/>')
    # 금 테두리와 L자 모서리
    body.append('<g fill="none" stroke="#c9a063"><rect x="30" y="30" width="1860" height="1020" stroke-width="2"/><rect x="44" y="44" width="1832" height="992" stroke-width="1" stroke-opacity="0.5"/></g>')
    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        x, y = (30 if sx > 0 else 1890), (30 if sy > 0 else 1050)
        body.append(f'<path d="M{x} {y + sy * 120} L{x} {y} L{x + sx * 120} {y}" fill="none" stroke="#c9a063" stroke-width="6"/>')
        body.append(poly([(x + sx * 24, y + sy * 12), (x + sx * 36, y + sy * 24), (x + sx * 24, y + sy * 36), (x + sx * 12, y + sy * 24)], "#f99200"))
    return svg("".join(body), defs)


# --------------------------------------------------------------------------- FC 온라인: 밤 경기장, 줄무늬 잔디, 하얀 선, 관중석과 조명
def fconline() -> str:
    rng = random.Random(8)
    defs = lin("night", [(0, "#050505"), (1, "#14171a")]) + rad("light", [(0, "#ffffff", 0.9), (0.3, "#dff3ff", 0.35), (1, "#dff3ff", 0)], 0.5, 0.5, 0.5)
    body = ['<rect width="1920" height="1080" fill="url(#night)"/>']
    # 관중석(점)
    body.append('<path d="M0 260 L1920 260 L1920 520 L0 520 Z" fill="#101214"/>')
    colors = ["#3ba55c", "#f4f2ec", "#14532d", "#3d7bff", "#ff4f8b", "#f2b400"]
    for row in range(14):
        for col in range(0, 1920, 18):
            if rng.random() < 0.8:
                body.append(f'<circle cx="{col + rng.randint(0, 8)}" cy="{272 + row * 17}" r="4" fill="{rng.choice(colors)}" fill-opacity="{rng.uniform(0.35, 0.8):.2f}"/>')
    # 전광판 띠
    body.append('<rect x="0" y="520" width="1920" height="44" fill="#0b0b0b"/>')
    for i in range(8):
        body.append(f'<rect x="{i * 240 + 10}" y="528" width="220" height="28" fill="{["#3ba55c", "#f4f2ec"][i % 2]}" fill-opacity="0.85"/>')
    # 경기장(원근)
    stripes = []
    for i in range(12):
        x0, x1 = -400 + i * 227, -400 + (i + 1) * 227
        stripes.append(poly([(200 + i * 127, 564), (200 + (i + 1) * 127, 564), (x1, 1080), (x0, 1080)], "#2db45a" if i % 2 else "#249e4e"))
    body += stripes
    line = 'fill="none" stroke="#ffffff" stroke-opacity="0.85" stroke-width="5"'
    body.append(f'<polygon points="200,564 1720,564 2320,1080 -400,1080" {line}/>')
    body.append(f'<line x1="960" y1="564" x2="960" y2="1080" {line}/>')
    body.append(f'<ellipse cx="960" cy="760" rx="230" ry="80" {line}/>')
    body.append(f'<polygon points="200,640 420,640 330,860 40,860" {line}/>')
    # 조명탑
    for x in (160, 1760):
        body.append(f'<rect x="{x - 6}" y="60" width="12" height="220" fill="#3a4a5e"/><rect x="{x - 70}" y="40" width="140" height="40" rx="4" fill="#dff3ff"/>')
        body.append(f'<circle cx="{x}" cy="60" r="260" fill="url(#light)"/>')
    return svg("".join(body), defs)


# --------------------------------------------------------------------------- 전략적 팀 전투: 별이 뜬 보랏빛 하늘, 떠 있는 육각 전장, 금화
def tft() -> str:
    rng = random.Random(9)
    defs = lin("sky", [(0, "#0c0a1e"), (0.6, "#2b1f5c"), (1, "#4a2f8a")]) + rad("glow", [(0, "#8b6cff", 0.6), (1, "#8b6cff", 0)], 0.5, 0.6, 0.5) + \
        lin("rim", [(0, "#f0c96b"), (1, "#9a7a3a")])
    body = ['<rect width="1920" height="1080" fill="url(#sky)"/>', '<rect width="1920" height="1080" fill="url(#glow)"/>']
    for _ in range(160):  # 별
        body.append(f'<circle cx="{rng.randint(0, 1920)}" cy="{rng.randint(0, 600)}" r="{rng.uniform(0.8, 2.4):.1f}" fill="#ffffff" fill-opacity="{rng.uniform(0.3, 1):.2f}"/>')
    # 떠 있는 섬(타원 바닥과 금 테두리)
    body.append('<ellipse cx="960" cy="660" rx="760" ry="250" fill="#1c143a" stroke="url(#rim)" stroke-width="10"/>')
    body.append('<path d="M240 690 C400 1000 1520 1000 1680 690 C1500 880 420 880 240 690 Z" fill="#120c2a"/>')
    # 육각 전장(원근)
    for row in range(4):
        y = 520 + row * 66
        scale = 0.78 + row * 0.08
        for col in range(7):
            x = 960 + (col - 3) * 112 * scale + (56 * scale if row % 2 else 0)
            fill = "#2b1f5c" if (row + col) % 2 else "#352870"
            body.append(poly(hexagon(x, y, 52 * scale, 30 * scale), fill, 'stroke="#d9b25f" stroke-width="2.5" stroke-opacity="0.85"'))
    # 대기석
    for col in range(9):
        body.append(f'<rect x="{560 + col * 92}" y="820" width="76" height="34" rx="6" fill="#241a4e" stroke="#d9b25f" stroke-width="2"/>')
    # 금화
    for x, y in ((380, 700), (420, 730), (1520, 690), (1560, 720), (1490, 740)):
        body.append(f'<ellipse cx="{x}" cy="{y}" rx="26" ry="14" fill="#f0c96b" stroke="#9a7a3a" stroke-width="3"/>')
    for _ in range(40):  # 빛 조각
        x, y = rng.randint(200, 1720), rng.randint(300, 900)
        body.append(f'<circle cx="{x}" cy="{y}" r="{rng.uniform(1.5, 3.5):.1f}" fill="#b9a2ff" fill-opacity="{rng.uniform(0.4, 0.9):.2f}"/>')
    return svg("".join(body), defs)


# --------------------------------------------------------------------------- 마인크래프트: 네모 블록 땅, 네모 해와 구름, 네모 나무와 물
def minecraft() -> str:
    rng = random.Random(10)
    size = 60
    defs = lin("sky", [(0, "#6f9cff"), (1, "#b8d4ff")])
    body = ['<rect width="1920" height="1080" fill="url(#sky)"/>', '<rect x="1500" y="110" width="140" height="140" fill="#fff6b0"/>',
            '<rect x="1520" y="130" width="100" height="100" fill="#ffe066"/>']
    for _ in range(6):  # 네모 구름
        x, y = rng.randint(0, 1700), rng.randint(60, 300)
        body.append(f'<rect x="{x}" y="{y}" width="{rng.randint(4, 8) * 30}" height="{rng.randint(2, 3) * 30}" fill="#ffffff" fill-opacity="0.92"/>')
    heights = []
    level = 11
    for _ in range(W // size + 1):
        level = max(8, min(13, level + rng.choice([-1, 0, 0, 1])))
        heights.append(level)

    def block(x, y, top, side, dots):
        cells = [f'<rect x="{x}" y="{y}" width="{size}" height="{size}" fill="{side}"/>']
        if top:
            cells.append(f'<rect x="{x}" y="{y}" width="{size}" height="{size // 3}" fill="{top}"/>')
            cells.append(f'<rect x="{x + 10}" y="{y + size // 3}" width="10" height="10" fill="{top}"/><rect x="{x + 40}" y="{y + size // 3}" width="10" height="10" fill="{top}"/>')
        for _ in range(3):
            cells.append(f'<rect x="{x + rng.randrange(0, size - 10, 10)}" y="{y + rng.randrange(size // 3, size - 10, 10)}" width="10" height="10" fill="{dots}"/>')
        return "".join(cells)

    for col, level in enumerate(heights):
        x = col * size
        top_y = level * size - 60
        body.append(block(x, top_y, "#7cbd47", "#866043", "#6b4a30"))
        for depth in range(1, 4):
            body.append(block(x, top_y + depth * size, None, "#866043" if depth < 2 else "#7f7f7f", "#6b4a30" if depth < 2 else "#6a6a6a"))
        body.append(f'<rect x="{x}" y="{top_y + 4 * size}" width="{size}" height="{H}" fill="#6a6a6a"/>')
    # 물 웅덩이
    body.append(f'<rect x="{9 * size}" y="{heights[9] * size - 60}" width="{3 * size}" height="{size}" fill="#3f76e4" fill-opacity="0.9"/>')
    # 네모 나무
    tx = 4 * size
    ty = heights[4] * size - 60
    body.append(f'<rect x="{tx}" y="{ty - 4 * size}" width="{size}" height="{4 * size}" fill="#6b4a2b"/>')
    for dx, dy in ((-2, -6), (-1, -6), (0, -6), (1, -6), (2, -6), (-2, -5), (-1, -5), (0, -5), (1, -5), (2, -5), (-1, -7), (0, -7), (1, -7)):
        body.append(f'<rect x="{tx + dx * size}" y="{ty + dy * size}" width="{size}" height="{size}" fill="{rng.choice(["#3f8f2a", "#4aa232", "#357a23"])}"/>')
    body.append(f'<rect x="{25 * size}" y="{heights[25] * size - 60 - size}" width="{size}" height="{size}" fill="#c9a26b" stroke="#6b4a2b" stroke-width="6"/>')
    return svg("".join(body), defs)


SCENES = {"valorant": valorant, "lol": lol, "overwatch": overwatch, "hearthstone": hearthstone, "pubg": pubg, "maplestory": maplestory,
          "lostark": lostark, "fconline": fconline, "tft": tft, "minecraft": minecraft}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for key, draw in SCENES.items():
        path = OUT / f"scene-{key}.svg"
        path.write_text(draw(), encoding="utf-8")
        print(f"{path.name}  ({path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
