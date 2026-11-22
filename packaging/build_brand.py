"""브랜드 파일(assets/brand)로 프로그램 아이콘 만들기.

    pip install pillow
    python packaging/build_brand.py

- ``assets/brand/app-icon/debutkit.ico``: Windows 실행 파일 아이콘. 48 px 이상은 앱 아이콘(마이크 포함),
  32 px 이하는 작은 크기용 단순화 심볼(파비콘)을 써서 작게 봐도 형태 유지
- ``src/debutkit/gui/icon.png``: 설정 마법사 창 아이콘(256 px)
- ``src/debutkit/overlay/static/favicon.svg``: 오버레이 설정 화면 탭 아이콘

만든 파일은 저장소에 함께 넣는다(빌드 때 Pillow 불필요).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "assets" / "brand"
ICO = BRAND / "app-icon" / "debutkit.ico"
GUI_ICON = ROOT / "src" / "debutkit" / "gui" / "icon.png"
OVERLAY_FAVICON = ROOT / "src" / "debutkit" / "overlay" / "static" / "favicon.svg"

LARGE = (256, 128, 64, 48)
SMALL = {32: "favicon-32.png", 24: "favicon-48.png", 16: "favicon-16.png"}


def build() -> list[Path]:
    from PIL import Image

    app = Image.open(BRAND / "app-icon" / "app-icon_dark_rounded.png").convert("RGBA")
    frames = [app.resize((size, size), Image.Resampling.LANCZOS) for size in LARGE]
    for size, name in SMALL.items():
        small = Image.open(BRAND / "favicon" / name).convert("RGBA")
        frames.append(small if small.size == (size, size) else small.resize((size, size), Image.Resampling.LANCZOS))
    frames[0].save(ICO, format="ICO", sizes=[frame.size for frame in frames], append_images=frames[1:])
    app.resize((256, 256), Image.Resampling.LANCZOS).save(GUI_ICON, optimize=True)
    shutil.copyfile(BRAND / "favicon" / "favicon.svg", OVERLAY_FAVICON)
    return [ICO, GUI_ICON, OVERLAY_FAVICON]


def main() -> int:
    for path in build():
        print(f"{path.relative_to(ROOT)}  ({path.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
