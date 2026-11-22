"""릴리스 노트 만들기: CHANGELOG.md의 해당 버전 항목에 설치 안내와 비교 링크를 붙여 출력한다.

    python packaging/release_notes.py v0.3.0 > notes.md

.github/workflows/release.yml 이 태그 릴리스를 만들 때 사용한다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/BudongJW/debutkit"


def section(changelog: str, version: str) -> str:
    """``## 0.3.0 (날짜)`` 제목 아래부터 다음 ``## `` 제목 전까지. 없으면 ValueError."""
    found = re.search(rf"^## {re.escape(version)}\b.*?$\n(.*?)(?=^## |\Z)", changelog, flags=re.M | re.S)
    if not found:
        raise ValueError(f"CHANGELOG.md에 {version} 항목 없음")
    return found.group(1).strip()


def previous(changelog: str, version: str) -> str | None:
    versions = re.findall(r"^## (\d+\.\d+\.\d+)\b", changelog, flags=re.M)
    if version in versions and versions.index(version) + 1 < len(versions):
        return versions[versions.index(version) + 1]
    return None


def notes(tag: str, changelog: str) -> str:
    version = tag.lstrip("v")
    body = section(changelog, version)
    lines = [
        "## 설치",
        "",
        f"- `debutkit-{version}-windows-x64.zip` 다운로드, 압축 해제 후 `debutkit-gui.exe` 실행",
        "- 파이썬, 관리자 권한 불필요. 코드 서명 미적용(SmartScreen 경고 시 추가 정보 선택 후 실행)",
        "- 사용 설명서: https://budongjw.github.io/debutkit/guide.html",
        "",
        body.replace("### ", "## "),
        "",
    ]
    before = previous(changelog, version)
    link = f"[CHANGELOG]({REPO}/blob/main/CHANGELOG.md)"
    if before:
        link += f", [v{before} 이후 비교]({REPO}/compare/v{before}...v{version})"
    lines.append(f"전체 변경 내역: {link}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("사용: python packaging/release_notes.py v0.3.0", file=sys.stderr)
        return 2
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print(notes(args[0], (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
