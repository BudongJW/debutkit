"""사이트와 문서용 화면 이미지 만들기(docs/images).

    python packaging/build_screens.py

- 설정 마법사: 화면에 띄우지 않고 창을 그려 저장. 점검 결과는 예시 PC 값(이 PC 정보 미사용)
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


def find_browser() -> str:
    wanted = os.environ.get("DEBUTKIT_BROWSER")
    for name in (wanted,) if wanted else BROWSERS:
        found = shutil.which(name) or (name if Path(name).is_file() else None)
        if found:
            return found
    raise SystemExit("Chrome 또는 Edge 필요(DEBUTKIT_BROWSER로 지정 가능)")


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


def capture(browser: str, url: str, out: Path, size: tuple[int, int]) -> Path:
    with tempfile.TemporaryDirectory() as profile:
        # 오버레이 화면은 사건 흐름(SSE) 연결이 계속 열려 있어 virtual-time-budget이 끝나지 않는다: 고정 대기 후 촬영
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1", f"--user-data-dir={profile}",
                        f"--window-size={size[0]},{size[1]}", "--timeout=5000", f"--screenshot={out}", url],
                       check=True, capture_output=True, timeout=90)
    if not out.is_file():
        raise SystemExit(f"촬영 실패: {url}")
    return out


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


def overlay_shots(browser: str) -> list[Path]:
    server = overlay_server()
    try:
        settings = capture(browser, server.url + "/", OUT / "overlay-settings.png", (1180, 900))
    finally:
        server.stop()
    with tempfile.TemporaryDirectory() as folder:
        page = Path(folder) / "themes.html"
        page.write_text(themes_page(), encoding="utf-8")
        themes = capture(browser, page.as_uri(), OUT / "overlay-themes.png", (1200, 600))
    return [settings, themes]


def shrink(path: Path, width: int = 1200) -> None:
    from PIL import Image

    image = Image.open(path).convert("RGB")
    if image.width > width:
        image = image.resize((width, round(image.height * width / image.width)), Image.Resampling.LANCZOS)
    image.save(path, optimize=True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    shots = wizard_shots() + overlay_shots(find_browser())
    for path in shots:
        shrink(path)
        print(f"{path.relative_to(ROOT)}  ({path.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
