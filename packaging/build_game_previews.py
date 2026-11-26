"""게임 패키지 그림 견본 만들기(src/debutkit/overlay/static/games/thumb-*.jpg).

    python packaging/build_game_previews.py

- 게임마다 /games/preview?game=키 (그 게임 느낌의 배경 그림 + 실제 캐릭터 프레임, 채팅창, 후원 알림)를 헤드리스 Chrome 또는 Edge로 찍어
  960x540 JPEG로 저장. 방송 화면 미리보기의 게임 패키지 단추에 쓴다(iframe 여러 개 대신 가벼운 그림)
- 사용 설명서 그림 docs/images/game-packages.png (10장을 5x2로)도 함께
- 저장 설정은 임시 폴더(이 PC 설정이 그림에 나오지 않음). 배경 그림은 packaging/build_game_scenes.py가 먼저 만든다
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "debutkit" / "overlay" / "static" / "games"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "packaging"))


def main() -> int:
    os.environ["DEBUTKIT_SETTINGS"] = str(Path(tempfile.mkdtemp(prefix="debutkit-games-")) / "settings.json")
    import build_screens
    from PIL import Image

    from debutkit.overlay import games
    from debutkit.overlay.server import OverlayServer

    browsers = build_screens.find_browsers()
    server = OverlayServer([], port=0).start()
    try:
        with tempfile.TemporaryDirectory() as folder:
            for key in games.GAMES:
                shot = build_screens.capture(browsers, f"{server.url}/games/preview?game={key}", Path(folder) / f"{key}.png", (1920, 1080), wait=6.0)
                out = OUT / f"thumb-{key}.jpg"
                with Image.open(shot) as image:
                    image.convert("RGB").resize((960, 540), Image.Resampling.LANCZOS).save(out, quality=82, optimize=True, progressive=True)
                print(f"{out.name}  ({out.stat().st_size / 1024:.0f} KB)")
    finally:
        server.stop()
    montage()
    return 0


def montage() -> Path:
    """사용 설명서 그림: 게임 패키지 그림 견본 10장을 5x2로(docs/images/game-packages.png). 순서는 games.GAMES와 같음."""
    from PIL import Image

    from debutkit.overlay import games

    width, height, gap = 236, 133, 5
    sheet = Image.new("RGB", (5 * width + 6 * gap, 2 * height + 3 * gap), "#1e2327")
    for index, key in enumerate(games.GAMES):
        with Image.open(OUT / f"thumb-{key}.jpg") as image:
            sheet.paste(image.resize((width, height), Image.Resampling.LANCZOS), (gap + (index % 5) * (width + gap), gap + (index // 5) * (height + gap)))
    out = ROOT / "docs" / "images" / "game-packages.png"
    sheet.save(out, optimize=True)
    print(f"{out.relative_to(ROOT)}  ({out.stat().st_size / 1024:.0f} KB)")
    return out


if __name__ == "__main__":
    sys.exit(main())
