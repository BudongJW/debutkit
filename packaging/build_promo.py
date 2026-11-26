"""서비스 소개 그림(docs/images/promo-*.jpg): 기본 3D 캐릭터 데비와 실제 debutkit 화면으로 만든 1600x900 소개 장면.

    python packaging/build_promo.py

- 데비: 캐릭터 그림 만들기 화면(헤드리스 브라우저, 소프트웨어 WebGL)에서 추천 자세로 그린 투명 PNG
- 화면: docs/images의 실제 화면 그림, 방송 중 장면은 오버레이 서버의 실제 채팅창(/chat?sample)과 후원 알림(/alerts?still)
- 저장 설정과 캐릭터 보관함은 임시 폴더(이 PC의 설정이 그림에 나오지 않음)
"""

from __future__ import annotations

import base64
import io
import json
import os
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "images"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "packaging"))

#: 데비 자세: 이름 -> (추천 자세, 각도, 표정)
POSES = {"wave": ("wave", 0, "happy"), "hip": ("hip", 0.3, "neutral"), "cheer": ("cheer", 0, "happy"), "relaxed": ("relaxed", 0.62, "relaxed"),
         "front": ("relaxed", 0, "happy")}
#: 소개 장면: 키 -> (꼬리표, 제목(<br> 줄바꿈), 설명, 꼬리표 목록)
SLIDES = {
    "hero": ("debutkit", "첫 방송 준비를<br>debutkit 하나로", "PC 점검, OBS 장면, 통합 채팅과 후원 알림, 캐릭터 방송, 방송 연출까지. 무료 오픈소스",
             ["치지직", "SOOP", "YouTube", "Twitch"]),
    "live": ("방송 중", "채팅, 후원, 캐릭터를<br>방송 화면 하나에", "네 플랫폼의 채팅과 후원 알림을 OBS 브라우저 소스로. 캐릭터는 마이크 소리에 맞춰 입이 움직임",
             ["통합 채팅창", "후원 알림", "캐릭터 화면", "게임 패키지"]),
    "prep": ("방송 준비", "방송 전에 할 일을<br>순서대로", "PC 점검과 OBS 장면 만들기, OBS에 넣기, 시험 후원, 방송 직전 점검",
             ["설정 마법사", "시작하기 목록", "방송 직전 점검"]),
    "character": ("캐릭터", "PNGTuber부터<br>3D 캐릭터까지", "VRM, GLB, FBX, Live2D 등록과 사용 조건 확인. 얼굴 추적, 표정 시트, 포즈 그림",
                  ["기본 캐릭터 데비", "얼굴 추적", "포즈 그림"]),
    "fun": ("방송 연출", "후원과 채팅으로<br>함께 노는 방송", "후원 추첨, 뽑기판, 후원 벽, 참여 레이스. 시청자가 채팅 명령과 후원으로 참여",
            ["후원 추첨 7종", "뽑기판", "후원 벽", "참여 레이스"]),
}


def render_poses(browsers: list[str], base: str, folder: Path) -> None:
    """캐릭터 그림 만들기 화면의 문서용 고리(window.debutkitSheet)로 데비 자세를 투명 PNG로(투명 여백은 잘라 냄)."""
    import build_screens
    from PIL import Image

    pictures: dict[str, bytes] = {}

    def work(call) -> None:
        call("Page.navigate", url=f"{base}/character/sheet?id=debutkit-3d")
        evaluate = lambda expression: call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True).get("result", {}).get("value")  # noqa: E731
        end = time.monotonic() + 180
        while not evaluate("Boolean(window.debutkitSheet && window.debutkitSheet.ready())"):
            if time.monotonic() > end:
                raise SystemExit("캐릭터 그림 만들기 화면이 그림을 끝내지 못함")
            time.sleep(1)
        for name, (preset, angle, face) in POSES.items():
            url = evaluate(f"window.debutkitSheet.pose({json.dumps(preset)}, {angle}, {json.dumps(face)}, 800, 1200, false)")
            pictures[name] = base64.b64decode(url.split(",", 1)[1])

    if not any(build_screens._devtools(browser, (1280, 900), work) and pictures for browser in browsers):
        raise SystemExit("데비 자세 그리기 실패")
    for name, data in pictures.items():
        image = Image.open(io.BytesIO(data)).convert("RGBA")
        image.crop(image.getbbox()).save(folder / f"debi-{name}.png")


def overlays(browsers: list[str], base: str, folder: Path) -> None:
    """방송 중 장면에 놓을 실제 채팅창(예시 채팅)과 후원 알림(멈춘 그림)을 투명 PNG로(오버레이 서버는 이 PC 화면만 받아 iframe 대신 그림)."""
    import build_screens

    build_screens.capture(browsers, f"{base}/chat?sample&theme=card", folder / "chat.png", (560, 820), wait=5.0, transparent=True)
    build_screens.capture(browsers, f"{base}/alerts?still", folder / "alert.png", (900, 320), wait=4.0, transparent=True)


def fonts() -> str:
    """함께 배포한 글꼴을 data 주소로(로컬 파일 페이지라 서버 글꼴을 불러오지 못함)."""
    vendor = ROOT / "src" / "debutkit" / "overlay" / "static" / "vendor" / "fonts"
    rules = []
    for family, name, weight in (("Black Han Sans", "BlackHanSans-Regular.woff2", 400), ("Pretendard", "Pretendard-Bold.subset.woff2", 700),
                                 ("Pretendard", "Pretendard-SemiBold.subset.woff2", 600)):
        data = base64.b64encode((vendor / name).read_bytes()).decode()
        rules.append(f'@font-face {{ font-family: "{family}"; src: url("data:font/woff2;base64,{data}") format("woff2"); font-weight: {weight}; }}')
    return "\n".join(rules)


def stars(count: int = 46) -> str:
    chance = random.Random(5)
    return "".join(f'<i style="left:{chance.uniform(0, 1600):.0f}px;top:{chance.uniform(0, 640):.0f}px;opacity:{chance.uniform(0.25, 0.8):.2f};'
                   f'width:{chance.uniform(2, 4):.1f}px;height:{chance.uniform(2, 4):.1f}px"></i>' for _ in range(count))


def page(key: str, base: str) -> str:
    tag, title, lead, chips = SLIDES[key]
    visual = {
        "hero": '<div class="floor" style="left:1000px;width:520px"></div><img class="debi" src="debi-wave.png" style="right:150px;bottom:40px;height:820px">'
                '<img class="brand" src="lockup.svg">',
        "live": '''<div class="screen"><div class="inner"><img src="scene.jpg" style="position:absolute;inset:0;width:1920px;height:1080px;object-fit:cover">
                    <img src="alert.png" style="position:absolute;left:510px;top:20px;width:900px">
                    <img src="chat.png" style="position:absolute;right:30px;top:250px;width:560px">
                    <img src="debi-front.png" style="position:absolute;left:30px;bottom:-760px;height:1700px;filter:drop-shadow(0 10px 20px rgba(0,0,0,.35))">
                    </div></div>''',
        "prep": '<div class="shot" style="left:700px;top:130px;width:600px;height:600px"><img src="settings.png" style="width:600px"></div>'
                '<div class="floor" style="left:1200px;width:360px"></div><img class="debi" src="debi-hip.png" style="right:50px;bottom:40px;height:720px">',
        "character": '<div class="floor" style="left:760px;width:780px"></div><img class="debi" src="debi-hip.png" style="left:780px;bottom:40px;height:660px">'
                     '<img class="debi" src="debi-wave.png" style="left:1010px;bottom:40px;height:760px">'
                     '<img class="debi" src="debi-relaxed.png" style="left:1300px;bottom:40px;height:660px">',
        "fun": '<div class="shot" style="left:720px;top:270px;width:540px"><img src="draw.png" style="width:540px"></div>'
               '<div class="floor" style="left:1200px;width:360px"></div><img class="debi" src="debi-cheer.png" style="right:30px;bottom:40px;height:660px">',
    }[key]
    chip_html = "".join(f"<span>{chip}</span>" for chip in chips)
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>
{fonts()}
html, body {{ margin: 0; width: 1600px; height: 900px; overflow: hidden; }}
body {{ position: relative; color: #fff; font-family: "Pretendard", sans-serif;
  background: radial-gradient(ellipse 60% 70% at 72% 42%, rgba(169, 139, 247, 0.5), transparent 70%), linear-gradient(180deg, #2b2249, #110e1d); }}
i {{ position: absolute; border-radius: 50%; background: #fff; }}
.copy {{ position: absolute; left: 96px; top: 170px; width: {560 if key in ("live", "fun", "prep") else 660}px; }}
.tag {{ display: inline-block; padding: 6px 16px; border-radius: 999px; background: #45d6b8; color: #231b3d; font-weight: 700; font-size: 22px; }}
h1 {{ font-family: "Black Han Sans", sans-serif; font-weight: 400; font-size: 66px; line-height: 1.2; margin: 24px 0 20px; letter-spacing: -0.5px; }}
p {{ margin: 0; font-size: 25px; line-height: 1.6; font-weight: 600; color: #ddd4f8; word-break: keep-all; }}
.chips {{ margin-top: 26px; }}
.chips span {{ display: inline-block; margin: 0 10px 10px 0; padding: 8px 16px; border-radius: 10px; background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2); font-size: 20px; font-weight: 600; }}
.shot {{ position: absolute; overflow: hidden; border-radius: 16px; border: 1px solid rgba(255, 255, 255, 0.18); box-shadow: 0 30px 70px rgba(0, 0, 0, 0.5); background: #fff; }}
.shot img {{ display: block; }}
.debi {{ position: absolute; filter: drop-shadow(0 24px 30px rgba(10, 5, 30, 0.55)); }}
.floor {{ position: absolute; bottom: 14px; height: 70px; border-radius: 50%; background: radial-gradient(closest-side, rgba(69, 214, 184, 0.55), transparent); }}
.brand {{ position: absolute; left: 96px; bottom: 64px; height: 48px; }}
.screen {{ position: absolute; left: 700px; top: 150px; width: 820px; height: 461px; overflow: hidden; border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.2); box-shadow: 0 30px 70px rgba(0, 0, 0, 0.5); }}
.screen .inner {{ position: relative; width: 1920px; height: 1080px; transform: scale(0.4271); transform-origin: 0 0; }}
.screen iframe {{ position: absolute; border: 0; background: transparent; }}
</style></head><body>{stars()}
<div class="copy"><span class="tag">{tag}</span><h1>{title}</h1><p>{lead}</p><div class="chips">{chip_html}</div></div>
{visual}</body></html>"""


def build() -> list[Path]:
    import build_screens
    from PIL import Image

    browsers = build_screens.find_browsers()
    made = []
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        os.environ["DEBUTKIT_SETTINGS"] = str(folder / "settings" / "settings.json")  # 이 PC의 설정 대신 임시 폴더
        server = build_screens.overlay_server()
        try:
            render_poses(browsers, server.url, folder)
            overlays(browsers, server.url, folder)
            shutil.copyfile(ROOT / "assets" / "brand" / "lockup" / "horizontal_dark-bg.svg", folder / "lockup.svg")
            shutil.copyfile(ROOT / "src" / "debutkit" / "overlay" / "static" / "games" / "scene-maplestory.jpg", folder / "scene.jpg")
            shutil.copyfile(OUT / "overlay-settings.png", folder / "settings.png")
            shutil.copyfile(OUT / "overlay-draw.png", folder / "draw.png")
            for key in SLIDES:
                html = folder / f"{key}.html"
                html.write_text(page(key, server.url), encoding="utf-8")
                shot = build_screens.capture(browsers, html.as_uri(), folder / f"{key}.png", (1600, 900), wait=7.0)
                out = OUT / f"promo-{key}.jpg"
                Image.open(shot).convert("RGB").save(out, "JPEG", quality=90, optimize=True, progressive=True)
                made.append(out)
                print(out.name, flush=True)
        finally:
            server.stop()
    return made


if __name__ == "__main__":
    build()
