"""사이트와 문서용 화면 이미지 만들기(docs/images).

    python packaging/build_screens.py

- 설정 마법사: 화면에 띄우지 않고 창을 그려 저장. 점검 결과는 예시 PC 값(이 PC 정보 미사용)
- 저장 설정과 캐릭터 보관함은 임시 폴더 사용(이 PC에 등록한 캐릭터, 저장 설정이 이미지에 나오지 않음)
- 오버레이 설정 화면, 채팅창 표시 형태, 후원 알림: 예시 채팅을 넣은 오버레이 서버를 열고
  Chrome 또는 Edge 헤드리스 모드로 촬영(DEBUTKIT_BROWSER로 다른 브라우저 지정 가능)
- 사이트 소개 그림(intro-*.jpg): 방송 연출과 방송 이미지 만들기의 그림 견본(?sample)을 촬영해 기능별로 모아 붙임

    python packaging/build_screens.py --only intro   # 사이트 소개 그림만
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "images"
sys.path.insert(0, str(ROOT / "src"))

BROWSERS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "google-chrome", "chromium", "msedge",
)


def find_browsers() -> list[str]:
    """설치된 촬영용 브라우저. 앞의 것이 촬영하지 못하면(정책으로 헤드리스 차단 등) 다음 것을 사용."""
    wanted = os.environ.get("DEBUTKIT_BROWSER")
    found = []
    for name in (wanted,) if wanted else BROWSERS:
        path = shutil.which(name) or (name if Path(name).is_file() else None)
        if path and path not in found:
            found.append(path)
    if not found:
        raise SystemExit("Chrome 또는 Edge 필요(DEBUTKIT_BROWSER로 지정 가능)")
    return found


def sample_system():
    from debutkit import doctor

    paths = {r"C:\Program Files\obs-studio\bin\64bit\obs64.exe", r"C:\Steam\steamapps\common\VTube Studio"}
    return doctor.System(
        os_name="Windows", env={"ProgramFiles": r"C:\Program Files"}, which=lambda name: None, exists=lambda path: path in paths,
        port_open=lambda host, port: False, memory_gb=lambda: 32.0, cpu_count=lambda: 12, disk_free_gb=lambda path: 412.0,
        gpu_names=lambda: ["NVIDIA GeForce RTX 4060"], package_version=lambda name: "0.14.1", steam_root=lambda: r"C:\Steam",
        read_text=lambda path: None, find_ffmpeg=lambda: None, audio_inputs=lambda: ["마이크 (USB Audio Device)"],
        cameras=lambda: ["HD Webcam"], home=r"C:\Users\streamer",
    )


def wizard_shots() -> list[Path]:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from debutkit import doctor
    from debutkit.gui.app import Backend, Wizard, style_sheet

    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(style_sheet())
    backend = Backend(run_checks=lambda **kw: doctor.run_checks(sample_system(), overlay_port=kw.get("overlay_port", 8790)),
                      chzzk_signed_in=lambda: True, can_download_ffmpeg=lambda: True, clip_dir=lambda: Path(r"C:\Users\streamer\Videos\debutkit-clips"))
    window = Wizard(backend)
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.resize(1000, 760)
    window.show()
    end = time.monotonic() + 5
    while not window.checked and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()
    saved = []
    check = OUT / "wizard-check.png"
    window.grab().save(str(check))
    saved.append(check)

    window.go(1)
    app.processEvents()
    character = OUT / "wizard-character.png"
    window.grab().save(str(character))
    saved.append(character)

    window.go(3)
    window.chzzk.setText("https://chzzk.naver.com/live/0123456789abcdef0123456789abcdef")
    window.soop.setText("https://play.sooplive.co.kr/streamer")
    window.youtube.setText("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    window.youtube_key.setText("example-key")
    window.autoclip.setChecked(True)
    for line in ("오버레이 실행 중: http://127.0.0.1:8790/chat (채팅창), http://127.0.0.1:8790/alerts (알림)", "CHZZK 공식 API 연결 시도",
                 "SOOP https://play.sooplive.co.kr/streamer 연결 시도", "자동 클립 시작(OBS 33.0.1). 저장 위치: C:\\Users\\streamer\\Videos\\debutkit-clips",
                 "클립 저장: live_20261122_210315.mp4 (스트리머 표시)"):
        window._append_log(line)
    app.processEvents()
    chat = OUT / "wizard-chat.png"
    window.grab().save(str(chat))
    saved.append(chat)
    window.close()
    window.deleteLater()
    app.processEvents()  # 파이썬 종료 전에 Qt 객체 정리
    return saved


SAMPLES = [
    ("chzzk", "chat", "치즈냥", "안녕하세요", "", 0.0, ""),
    ("soop", "chat", "숲속토끼", "첫 방송 축하드립니다", "", 0.0, ""),
    ("youtube", "chat", "별빛시청자", "목소리가 잘 들립니다", "", 0.0, ""),
    ("twitch", "chat", "Haru", "hello from Twitch", "", 0.0, ""),
    ("chzzk", "chat", "도토리", "오늘 방송 일정이 어떻게 되나요", "moderator", 0.0, ""),
    ("chzzk", "donation", "고양이집사", "데뷔 축하합니다", "", 10000.0, "원"),
    ("soop", "chat", "새벽감성", "배경 음악 제목이 궁금합니다", "", 0.0, ""),
    ("youtube", "chat", "debut_streamer", "오늘도 방문해 주셔서 감사합니다", "owner", 0.0, ""),
]


def overlay_server():
    from debutkit.overlay.events import OverlayEvent
    from debutkit.overlay.server import OverlayServer

    server = OverlayServer([], port=0).start()
    for index, (platform, kind, name, text, role, amount, unit) in enumerate(SAMPLES):
        server.hub.publish(OverlayEvent(platform, kind, name, (("text", text),), amount=amount, unit=unit, role=role, time=1_000_000 + index))
    return server


def _free_port() -> int:
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _devtools_capture(browser: str, url: str, out: Path, size: tuple[int, int], wait: float, transparent: bool = False) -> bool:
    """헤드리스 브라우저를 원격 디버깅(DevTools)으로 열고 ``wait`` 초 뒤 촬영.

    오버레이 화면은 사건 흐름(SSE) 연결이 계속 열려 있어 --screenshot, --virtual-time-budget의 촬영 시점이 일정하지 않다
    (채팅 줄 등장 효과 중간, 캐릭터 이미지를 불러오기 전에 찍힘). 실제 시간으로 기다린 뒤 촬영한다.
    """
    import base64

    def work(call) -> None:
        if transparent:  # 투명 배경 PNG(브랜드 파일): 페이지 배경을 투명하게
            call("Emulation.setDefaultBackgroundColorOverride", color={"r": 0, "g": 0, "b": 0, "a": 0})
        call("Page.navigate", url=url)
        time.sleep(wait)
        out.write_bytes(base64.b64decode(call("Page.captureScreenshot", format="png")["data"]))
    return _devtools(browser, size, work)


def _devtools(browser: str, size: tuple[int, int], work) -> bool:
    """헤드리스 브라우저를 원격 디버깅으로 열고 ``work(call)`` 실행(call(메서드, **값) -> 결과). 실행하지 못하면 False."""
    import itertools
    import json
    import urllib.request

    import websocket  # websocket-client(debutkit[live])

    port = _free_port()
    # Edge는 호환 계층 때문에 자기 자신을 다시 실행하고 처음 프로세스는 끝난다. 그러면 terminate로는 실제 브라우저가 남으므로
    # 다시 실행하지 않게 하고, 끝낼 때는 DevTools의 Browser.close로 브라우저 스스로 닫게 한다
    relaunch = ["--edge-skip-compat-layer-relaunch"] if Path(browser).name.lower() == "msedge.exe" else []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:  # 브라우저가 끝난 뒤에도 잠시 파일을 씀
        process = subprocess.Popen([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1", *relaunch,
                                    f"--remote-debugging-port={port}", f"--user-data-dir={profile}", f"--window-size={size[0]},{size[1]}", "about:blank"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            target, end = None, time.monotonic() + 20
            while target is None and time.monotonic() < end:
                if process.poll() is not None:  # 정책 등으로 헤드리스 실행이 막힌 브라우저
                    return False
                try:
                    targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2).read())
                    target = next((item for item in targets if item.get("type") == "page"), None)
                except OSError:
                    time.sleep(0.2)
            if target is None:
                return False
            socket_ = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)
            numbers = itertools.count(1)

            def call(method: str, **params: object) -> dict:
                number = next(numbers)
                socket_.send(json.dumps({"id": number, "method": method, "params": params}))
                while True:
                    reply = json.loads(socket_.recv())
                    if reply.get("id") == number:
                        return reply.get("result") or {}

            try:
                call("Emulation.setDeviceMetricsOverride", width=size[0], height=size[1], deviceScaleFactor=1, mobile=False)
                work(call)
            finally:
                socket_.close()
            return True
        finally:
            try:
                browser_socket = websocket.create_connection(json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2).read())
                                                             ["webSocketDebuggerUrl"], timeout=5, suppress_origin=True)
                browser_socket.send(json.dumps({"id": 1, "method": "Browser.close"}))
                browser_socket.close()
            except (OSError, ValueError, KeyError, websocket.WebSocketException):
                pass
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


def capture(browsers: list[str], url: str, out: Path, size: tuple[int, int], wait: float = 4.0, transparent: bool = False) -> Path:
    out.unlink(missing_ok=True)  # 이전 이미지가 남아 촬영 실패를 놓치지 않도록
    for browser in browsers:
        if _devtools_capture(browser, url, out, size, wait, transparent) and out.is_file():
            return out
    raise SystemExit(f"촬영 실패: {url}")


PLATFORM_LABELS = {"chzzk": ("치지직", "#00d68f"), "soop": ("SOOP", "#3d7bff"), "twitch": ("Twitch", "#9146ff"), "youtube": ("YouTube", "#ff0033")}


def chat_lines(samples: list[tuple]) -> str:
    """overlay.js의 채팅 줄과 같은 구조의 정적 HTML(애니메이션 없이 촬영하기 위해)."""
    import html

    lines = []
    for platform, kind, name, text, role, amount, unit in samples:
        label, color = PLATFORM_LABELS[platform]
        amount_html = f'<span class="amount">{amount:,.0f}{unit}</span>' if kind == "donation" else ""
        lines.append(f'<div class="line {kind}{" " + role if role else ""}" style="--line-color:{color};animation:none">'
                     f'<span class="platform" style="--platform:{color}">{label}</span><span class="name">{html.escape(name)}</span>'
                     f'{amount_html}<span class="text">{html.escape(text)}</span></div>')
    return "".join(lines)


def themes_page() -> str:
    import html

    css = (ROOT / "src" / "debutkit" / "overlay" / "static" / "overlay.css").read_text(encoding="utf-8")
    columns = []
    for theme, count in (("shadow", 8), ("card", 6), ("light", 7)):
        frame = (f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head>'
                 f'<body class="overlay" data-theme="{theme}" style="--font-size:19px"><div id="chat">{chat_lines(SAMPLES[-count:])}</div></body></html>')
        columns.append(f'<div class="col"><span>{theme}</span><iframe srcdoc="{html.escape(frame, quote=True)}"></iframe></div>')
    alert = ('<div class="alert donation" style="animation:none"><span class="platform" style="--platform:#00d68f">치지직</span>'
             '<div class="alert-title">고양이집사 님, 10,000원 후원 감사합니다</div><div class="alert-text">데뷔 축하합니다</div></div>')
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>{css}
body {{ margin: 0; background: #59626a; }}
.cols {{ display: grid; grid-template-columns: repeat(3, 1fr); height: 430px; }}
.col {{ position: relative; border-right: 1px solid #6b747b; }}
.col:last-child {{ border-right: 0; }}
.col span {{ position: absolute; left: 12px; top: 10px; color: #fff; font: 700 14px "Malgun Gothic", sans-serif; background: #1e2327; padding: 2px 8px; border-radius: 3px; }}
iframe {{ position: absolute; inset: 38px 0 0 0; width: 100%; height: calc(100% - 38px); border: 0; }}
.alerts {{ height: 170px; display: flex; align-items: center; justify-content: center; border-top: 1px solid #6b747b; font: 22px "Malgun Gothic", sans-serif; }}
</style></head><body><div class="cols">{"".join(columns)}</div><div class="alerts">{alert}</div></body></html>"""


def draw_shot(browser: list[str], base: str, out: Path = OUT / "overlay-draw.png",
              shots: tuple = (("card", "sample=card&count=3", 8.0), ("wheel", "sample=wheel", 11.0))) -> Path:
    """추첨 연출: 미리보기 주소(?sample)로 두 장면을 각각 촬영해 나란히 붙인다(기본 상품표, 예시 이름).

    후원 추첨은 카드 뒤집기와 룰렛, 시청자 참여 추첨은 당첨 카드와 순서표.
    """
    from PIL import Image

    with tempfile.TemporaryDirectory() as folder:
        parts = [capture(browser, f"{base}/draw?{query}", Path(folder) / f"{name}.png", (960, 800), wait=wait) for name, query, wait in shots]
        images = [Image.open(path).convert("RGB") for path in parts]
        joined = Image.new("RGB", (sum(image.width for image in images), max(image.height for image in images)), "#59626a")
        joined.paste(images[0], (0, 0))
        joined.paste(images[1], (images[0].width, 0))
        joined.save(out)
        for image in images:
            image.close()
    return out


#: 3D 데비 쇼케이스: (추천 자세, 각도, 표정). 가운데가 대표
SHOWCASE = (("hip", 0.3, "neutral"), ("wave", 0, "happy"), ("relaxed", 0.62, "relaxed"))


def character_shots(browsers: list[str], base: str) -> list[Path]:
    """기본 3D 캐릭터 데비: 캐릭터 그림 만들기 화면(헤드리스 브라우저, 소프트웨어 WebGL)에서 투명 포즈 그림 3장과 표정 시트를 받아
    무대 배경 위 쇼케이스(character-3d-debi.png)와 시트(character-sheet.png)로 저장."""
    import base64
    import json

    from PIL import Image

    pictures: dict[str, bytes] = {}

    def work(call) -> None:
        call("Page.navigate", url=f"{base}/character/sheet?id=debutkit-3d")
        evaluate = lambda expression: call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True).get("result", {}).get("value")  # noqa: E731
        end = time.monotonic() + 180  # 소프트웨어 WebGL은 모델을 그리는 데 오래 걸림
        while not evaluate("Boolean(window.debutkitSheet && window.debutkitSheet.ready())"):
            if time.monotonic() > end:
                raise SystemExit("캐릭터 그림 만들기 화면이 그림을 끝내지 못함")
            time.sleep(1)
        for index, (preset, angle, face) in enumerate(SHOWCASE):
            url = evaluate(f"window.debutkitSheet.pose({json.dumps(preset)}, {angle}, {json.dumps(face)}, 600, 900, false)")
            pictures[f"pose{index}"] = base64.b64decode(url.split(",", 1)[1])
        pictures["sheet"] = base64.b64decode(evaluate('window.debutkitSheet.sheet("wave")').split(",", 1)[1])

    if not any(_devtools(browser, (1280, 900), work) and pictures for browser in browsers):
        raise SystemExit("캐릭터 그림 촬영 실패")
    import io

    poses = [Image.open(io.BytesIO(pictures[f"pose{index}"])).convert("RGBA") for index in range(len(SHOWCASE))]
    showcase = OUT / "character-3d-debi.png"
    stage_picture(poses, (1200, 640)).save(showcase, optimize=True)
    sheet = OUT / "character-sheet.png"
    Image.open(io.BytesIO(pictures["sheet"])).convert("RGB").resize((1200, 675), Image.Resampling.LANCZOS).save(sheet, optimize=True)
    return [showcase, sheet]


def stage_picture(poses: list, size: tuple[int, int]):
    """무대 배경(캐릭터 그림 만들기 화면과 같은 남보라 그라데이션, 라벤더 빛, 작은 별, 민트 바닥 빛) 위에 투명 포즈 그림을 나란히."""
    import random

    from PIL import Image, ImageDraw, ImageFilter

    width, height = size
    picture = Image.new("RGB", size)
    draw = ImageDraw.Draw(picture)
    top, bottom = (43, 34, 73), (17, 14, 29)
    for y in range(height):
        t = y / (height - 1)
        draw.line([(0, y), (width, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom, strict=True)))
    glow = Image.new("L", size, 0)
    ImageDraw.Draw(glow).ellipse((width * 0.12, -height * 0.1, width * 0.88, height * 0.9), fill=120)
    picture = Image.composite(Image.new("RGB", size, (169, 139, 247)), picture, glow.filter(ImageFilter.GaussianBlur(140)))
    picture = picture.convert("RGBA")
    stars = ImageDraw.Draw(picture)
    chance = random.Random(7)
    for _ in range(40):
        x, y, r = chance.uniform(0, width), chance.uniform(0, height * 0.7), chance.uniform(0.6, 1.8)
        stars.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, round(chance.uniform(70, 200))))
    floor = height * 0.95
    for index, pose in enumerate(poses):
        figure = pose.crop(pose.getbbox())
        tall = height * (0.9 if index == len(poses) // 2 else 0.8)
        figure = figure.resize((round(figure.width * tall / figure.height), round(tall)), Image.Resampling.LANCZOS)
        center = width * (index + 0.5) / len(poses)
        shine = Image.new("L", size, 0)
        ImageDraw.Draw(shine).ellipse((center - figure.width * 0.75, floor - 16, center + figure.width * 0.75, floor + 16), fill=150)
        picture.alpha_composite(Image.composite(Image.new("RGBA", size, (69, 214, 184, 255)), Image.new("RGBA", size, (0, 0, 0, 0)),
                                                shine.filter(ImageFilter.GaussianBlur(14))))
        picture.alpha_composite(figure, (round(center - figure.width / 2), round(floor - figure.height)))
    return picture.convert("RGB")


def overlay_shots(browser: list[str]) -> list[Path]:
    server = overlay_server()
    try:
        settings = capture(browser, server.url + "/", OUT / "overlay-settings.png", (1180, 1340))
        # 알림 꾸미기: 추천 모양과 배치의 그림 견본(그림은 화면에 보일 때 불러오므로 넉넉히 기다림)
        looks = capture(browser, server.url + "/alerts/control", OUT / "overlay-alerts-looks.png", (1200, 1180), wait=10.0)
        draws = draw_shot(browser, server.url)
        raffles = draw_shot(browser, server.url, OUT / "overlay-raffle.png", (("pick", "sample=raffle", 7.0), ("order", "sample=order", 5.0)))
        characters = character_shots(browser, server.url)
    finally:
        server.stop()
    with tempfile.TemporaryDirectory() as folder:
        page = Path(folder) / "themes.html"
        page.write_text(themes_page(), encoding="utf-8")
        themes = capture(browser, page.as_uri(), OUT / "overlay-themes.png", (1200, 600))
    return [settings, looks, draws, raffles, *characters, themes]


def shrink(path: Path, width: int = 1200) -> None:
    from PIL import Image

    image = Image.open(path).convert("RGB")
    if image.width > width:
        image = image.resize((width, round(image.height * width / image.width)), Image.Resampling.LANCZOS)
    image.save(path, optimize=True)


#: 사이트 소개 그림의 견본 화면(예시 이름과 기본 설정. 견본 주소라 OBS와 다른 화면에는 나가지 않음)
#: 참여 레이스: (게임, 멈출 경기 시각 초, 기다릴 초). 구슬 레이스는 코스 계산이 길어 오래 기다림
RACE_SHOTS = (("marble", 9, 16), ("run", 6, 6), ("swim", 7, 6), ("survival", 8, 6))
#: 후원 추첨 연출: 결과가 다 열린 뒤 촬영
DRAW_SHOTS = ("card", "capsule", "scratch", "ticket", "drum", "tarot")
#: 뽑기판: (디자인, 칸 덮개)
PICK_SHOTS = (("card", "number"), ("balloon", "stars"), ("ticket", "dots"), ("envelope", "hearts"))
#: 방송 이미지 만들기: 줄마다 (그림 종류, 완성 프리셋)
DECOR_SHOTS = ((("thumbnail", "night"), ("profile", "heart"), ("shorts", "music")),
               (("cheki", "spring"), ("signature", "xmas"), ("twitch", "neon")))
INTRO_WIDTH = 1400
INTRO_BACK = (241, 237, 233)  # 사이트 화면 모음 배경(#f1ede9)


def _content_box(image, tolerance: int = 14):
    """왼쪽 위 색(배경)과 다른 부분의 영역."""
    from PIL import Image, ImageChops

    back = Image.new("RGB", image.size, image.getpixel((0, 0)))
    return ImageChops.difference(image, back).convert("L").point(lambda value: 255 if value > tolerance else 0).getbbox()


def _blank(image) -> bool:
    """거의 한 색인 그림(견본이 그려지기 전에 찍힘)."""
    box = _content_box(image)
    return box is None or (box[2] - box[0]) * (box[3] - box[1]) < image.width * image.height * 0.01


def trim(image, margin: int = 24):
    """배경을 잘라 내용만(사방 margin 여백)."""
    box = _content_box(image)
    if box is None:
        return image
    left, top, right, bottom = box
    return image.crop((max(0, left - margin), max(0, top - margin), min(image.width, right + margin), min(image.height, bottom + margin)))


def _card(image, radius: int):
    """둥근 모서리 그림(RGBA)과 옅은 그림자."""
    from PIL import Image, ImageDraw, ImageFilter

    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, image.width - 1, image.height - 1), radius, fill=255)
    card = image.convert("RGBA")
    card.putalpha(mask)
    shadow = Image.new("RGBA", (image.width + 40, image.height + 40), (0, 0, 0, 0))
    shadow.paste((30, 35, 39, 60), (20, 26), mask)
    return card, shadow.filter(ImageFilter.GaussianBlur(10))


def sheet(rows: list[list], width: int = INTRO_WIDTH, gap: int = 20, pad: int = 36, background: tuple = INTRO_BACK, radius: int = 10):
    """줄마다 같은 높이로 맞춰 가로를 채운 모음 그림(그림 비율 그대로, 둥근 모서리와 옅은 그림자)."""
    from PIL import Image

    inner = width - pad * 2
    placed, y = [], float(pad)
    for row in rows:
        height = (inner - gap * (len(row) - 1)) / sum(image.width / image.height for image in row)
        x = float(pad)
        for image in row:
            w = image.width * height / image.height
            placed.append((image.resize((round(w), round(height)), Image.Resampling.LANCZOS), (round(x), round(y))))
            x += w + gap
        y += height + gap
    out = Image.new("RGBA", (width, round(y - gap + pad)), (*background, 255))
    for image, (x, top) in placed:
        card, shadow = _card(image, radius)
        out.alpha_composite(shadow, (max(0, x - 20), max(0, top - 20)))
        out.alpha_composite(card, (x, top))
    return out.convert("RGB")


def save_intro(image, name: str) -> Path:
    path = OUT / name
    image.save(path, quality=86, optimize=True, progressive=True)
    return path


def intro_shots(browsers: list[str]) -> list[Path]:
    """사이트 소개 그림(docs/images/intro-*.jpg): 참여 레이스, 후원 추첨 연출, 뽑기판, 주사위 판, 후원 벽, 방송 화면 미리보기,
    방송 이미지 만들기."""
    import base64
    import io
    import json

    from PIL import Image

    server = overlay_server()
    saved: list[Path] = []
    try:
        base = server.url
        with tempfile.TemporaryDirectory() as folder:
            numbers = iter(range(1000))

            def shot(path: str, size: tuple[int, int], wait: float):
                for extra in (0, 6):  # 견본이 그려지기 전에 찍힌 빈 그림은 더 기다려 다시 촬영
                    out = capture(browsers, f"{base}/{path}", Path(folder) / f"{next(numbers)}.png", size, wait=wait + extra)
                    with Image.open(out) as opened:
                        image = opened.convert("RGB")
                    if not _blank(image):
                        return image
                raise SystemExit(f"그림 견본이 그려지지 않음: {path}")

            # 방송 화면 미리보기를 먼저: 앞선 촬영의 실시간 연결이 남아 있으면 겹쳐 보기의 채팅창이 비어 찍힘
            stage = shot("stage", (1440, 1000), 8).crop((0, 0, 1440, 745))  # 위쪽 메뉴, 추천 조합, 겹쳐 보기(아래 주소 줄 제외)
            saved.append(save_intro(sheet([[stage]], pad=28), "intro-stage.jpg"))

            races = [shot(f"race?sample={game}&still&t={at}&mute", (1920, 1080), wait) for game, at, wait in RACE_SHOTS]
            saved.append(save_intro(sheet([races[:2], races[2:]]), "intro-race.jpg"))

            draws = [shot(f"draw?sample={style}&mute", (960, 800), 9) for style in DRAW_SHOTS]
            boxes = [_content_box(image) for image in draws]
            union = (max(0, min(b[0] for b in boxes) - 30), max(0, min(b[1] for b in boxes) - 30),
                     min(960, max(b[2] for b in boxes) + 30), min(800, max(b[3] for b in boxes) + 30))
            draws = [image.crop(union) for image in draws]  # 여섯 연출을 같은 크기로
            saved.append(save_intro(sheet([draws[:3], draws[3:]]), "intro-draw.jpg"))

            picks = [trim(shot(f"pick?sample&mute&theme={theme}&cover={cover}", (1920, 1080), 7), 40) for theme, cover in PICK_SHOTS]
            saved.append(save_intro(sheet([picks[:2], picks[2:]]), "intro-pick.jpg"))

            board = trim(shot("board?sample&mute", (1920, 1080), 6), 40)
            saved.append(save_intro(sheet([[board]]), "intro-board.jpg"))

            wall = shot("wall?sample", (1920, 1080), 6)
            wall = trim(wall.crop((0, 0, wall.width, 300)), 40)  # 단위별 첫 줄(칸 이름과 첫 카드)
            saved.append(save_intro(sheet([[wall]]), "intro-wall.jpg"))

        pictures: dict[str, bytes] = {}

        def work(call) -> None:
            call("Page.navigate", url=f"{base}/decor")
            evaluate = lambda expression: call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True).get("result", {}).get("value")  # noqa: E731
            end = time.monotonic() + 60
            while not evaluate("Boolean(window.debutkitDecor)"):
                if time.monotonic() > end:
                    raise SystemExit("방송 이미지 만들기 화면이 열리지 않음")
                time.sleep(0.5)
            time.sleep(4)  # 캐릭터 그림과 글꼴
            for row in DECOR_SHOTS:
                for key, preset in row:
                    evaluate(f"window.debutkitDecor.preset({json.dumps(preset)})")
                    time.sleep(1.5)
                    url = evaluate(f"window.debutkitDecor.draw({json.dumps(key)}, 0.25)")
                    pictures[key] = base64.b64decode(url.split(",", 1)[1])

        if not any(_devtools(browser, (1440, 1000), work) and pictures for browser in browsers):
            raise SystemExit("방송 이미지 촬영 실패")
        rows = [[Image.open(io.BytesIO(pictures[key])).convert("RGB") for key, _ in row] for row in DECOR_SHOTS]
        saved.append(save_intro(sheet(rows), "intro-decor.jpg"))
    finally:
        server.stop()
    return saved


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="사이트와 문서용 화면 이미지 만들기")
    parser.add_argument("--only", choices=["intro"], help="intro: 사이트 소개 그림(intro-*.jpg)만")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="debutkit-screens-")
    os.environ["DEBUTKIT_SETTINGS"] = str(Path(scratch) / "settings.json")
    browsers = find_browsers()
    if args.only == "intro":
        shots = intro_shots(browsers)
    else:
        shots = wizard_shots() + overlay_shots(browsers)
        for path in shots:
            shrink(path)
        shots += intro_shots(browsers)
    for path in shots:
        print(f"{path.relative_to(ROOT)}  ({path.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
