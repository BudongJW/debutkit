"""프로젝트 사이트 만들기: ``site/`` 의 페이지와 브랜드 파일을 출력 폴더에 모으고 내부 링크를 확인한다.

    python packaging/build_site.py            # dist/site (폴더를 서버로 열어 확인)
    python packaging/build_site.py -o _site   # GitHub Pages 배포용 (.github/workflows/pages.yml)

페이지는 HTML과 CSS만 쓴다. 로고, 파비콘은 저장소에 두 번 두지 않고 ``assets/brand`` 에서
복사한다(:data:`ASSETS`). GitHub Pages가 그대로 서비스하도록 ``.nojekyll`` 을 넣는다.
사이트 주소: https://budongjw.github.io/debutkit/
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"

#: 사이트 안 경로와 저장소 파일
ASSETS: dict[str, str] = {
    "assets/lockup.svg": "assets/brand/lockup/horizontal_light-bg.svg",
    "assets/symbol.svg": "assets/brand/symbol/symbol_light-bg.svg",
    "assets/shots/wizard-check.png": "docs/images/wizard-check.png",
    "assets/shots/wizard-chat.png": "docs/images/wizard-chat.png",
    "assets/shots/wizard-character.png": "docs/images/wizard-character.png",
    "assets/shots/overlay-settings.png": "docs/images/overlay-settings.png",
    "assets/shots/overlay-alerts-looks.png": "docs/images/overlay-alerts-looks.png",
    "assets/shots/overlay-themes.png": "docs/images/overlay-themes.png",
    "assets/shots/overlay-draw.png": "docs/images/overlay-draw.png",
    "assets/shots/overlay-raffle.png": "docs/images/overlay-raffle.png",
    "assets/shots/game-packages.png": "docs/images/game-packages.png",
    "assets/shots/character-3d-debi.png": "docs/images/character-3d-debi.png",
    "assets/shots/character-sheet.png": "docs/images/character-sheet.png",
    "assets/favicon.svg": "assets/brand/favicon/favicon.svg",
    "assets/favicon.ico": "assets/brand/favicon/favicon.ico",
    "assets/apple-touch-icon.png": "assets/brand/favicon/favicon-180.png",
    "assets/social.png": "assets/brand/app-icon/app-icon_dark.png",
}

_LINK = re.compile(r'(?:href|src)="([^"]+)"')
_ID = re.compile(r'\sid="([^"]+)"')


def internal_links(page: Path) -> list[str]:
    """페이지 안의 사이트 내부 링크(외부 주소, 메일 제외)."""
    found = []
    for target in _LINK.findall(page.read_text(encoding="utf-8")):
        if re.match(r"^[a-z]+:", target) or target.startswith("//"):
            continue
        found.append(target)
    return found


def broken_links(site: Path) -> list[str]:
    """깨진 내부 링크 목록 ("페이지: 링크"). 파일과 ``#id`` 둘 다 확인한다."""
    site = Path(site).resolve()  # 상대 경로(-o _site)여도 링크 대상과 같은 기준으로 비교
    ids = {page: set(_ID.findall(page.read_text(encoding="utf-8"))) for page in site.rglob("*.html")}
    broken = []
    for page in sorted(ids):
        for link in internal_links(page):
            path, _, anchor = link.partition("#")
            target = (page.parent / path).resolve() if path else page
            if target.is_dir():
                target = target / "index.html"
            if not target.is_file():
                broken.append(f"{page.relative_to(site)}: {link}")
            elif anchor and target.suffix == ".html" and anchor not in ids.get(target, set()):
                broken.append(f"{page.relative_to(site)}: {link}")
    return broken


def build(out: str | Path) -> Path:
    """``site/`` 를 ``out`` 에 복사(먼저 비움)하고 폴더를 돌려준다. 깨진 링크가 있으면 실패."""
    target = Path(out)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(SITE, target)
    for name, source in ASSETS.items():
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source, destination)
    (target / ".nojekyll").write_text("", encoding="utf-8")
    broken = broken_links(target)
    if broken:
        raise SystemExit("깨진 내부 링크:\n  " + "\n  ".join(broken))
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-o", "--output", default=str(ROOT / "dist" / "site"), help="출력 폴더 (기본 dist/site)")
    args = parser.parse_args(argv)
    site = build(args.output)
    print(f"site  {site}  ({sum(1 for p in site.rglob('*') if p.is_file())} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
