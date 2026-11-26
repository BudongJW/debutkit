"""사이트와 문서용 화면 이미지 만들기(docs/images).

    python packaging/build_screens.py

- 설정 마법사: 화면에 띄우지 않고 창을 그려 저장. 점검 결과는 예시 PC 값(이 PC 정보 미사용)
- 저장 설정과 캐릭터 보관함은 임시 폴더 사용(이 PC에 등록한 캐릭터, 저장 설정이 이미지에 나오지 않음)
- 오버레이 설정 화면, 채팅창 표시 형태, 후원 알림: 예시 채팅을 넣은 오버레이 서버를 열고
  Chrome 또는 Edge 헤드리스 모드로 촬영(DEBUTKIT_BROWSER로 다른 브라우저 지정 가능)
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
                if transparent:  # 투명 배경 PNG(브랜드 파일): 페이지 배경을 투명하게
                    call("Emulation.setDefaultBackgroundColorOverride", color={"r": 0, "g": 0, "b": 0, "a": 0})
                call("Page.navigate", url=url)
                time.sleep(wait)
                out.write_bytes(base64.b64decode(call("Page.captureScreenshot", format="png")["data"]))
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


def overlay_shots(browser: list[str]) -> list[Path]:
    server = overlay_server()
    try:
        settings = capture(browser, server.url + "/", OUT / "overlay-settings.png", (1180, 1340))
        # 알림 꾸미기: 추천 모양과 배치의 그림 견본(그림은 화면에 보일 때 불러오므로 넉넉히 기다림)
        looks = capture(browser, server.url + "/alerts/control", OUT / "overlay-alerts-looks.png", (1200, 1180), wait=10.0)
        draws = draw_shot(browser, server.url)
        raffles = draw_shot(browser, server.url, OUT / "overlay-raffle.png", (("pick", "sample=raffle", 7.0), ("order", "sample=order", 5.0)))
    finally:
        server.stop()
    with tempfile.TemporaryDirectory() as folder:
        page = Path(folder) / "themes.html"
        page.write_text(themes_page(), encoding="utf-8")
        themes = capture(browser, page.as_uri(), OUT / "overlay-themes.png", (1200, 600))
    return [settings, looks, draws, raffles, themes]


def shrink(path: Path, width: int = 1200) -> None:
    from PIL import Image

    image = Image.open(path).convert("RGB")
    if image.width > width:
        image = image.resize((width, round(image.height * width / image.width)), Image.Resampling.LANCZOS)
    image.save(path, optimize=True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    scratch = tempfile.mkdtemp(prefix="debutkit-screens-")
    os.environ["DEBUTKIT_SETTINGS"] = str(Path(scratch) / "settings.json")
    shots = wizard_shots() + overlay_shots(find_browsers())
    for path in shots:
        shrink(path)
        print(f"{path.relative_to(ROOT)}  ({path.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
