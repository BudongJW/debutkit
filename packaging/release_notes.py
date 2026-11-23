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
    versions = re.findall(r"^## (\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?)\b", changelog, flags=re.M)
    if version in versions and versions.index(version) + 1 < len(versions):
        return versions[versions.index(version) + 1]
    return None


SIGNING_POLICY = "https://budongjw.github.io/debutkit/signing.html"
VERIFY_URL = "https://budongjw.github.io/debutkit/join.html#verify"


def signing_line(windows_signed: bool, macos_notarized: bool) -> str:
    """서명 상태 한 줄. 서명하지 않은 운영체제만 경고 안내."""
    states = ["Windows 서명 적용" if windows_signed else "Windows 서명 미적용(SmartScreen 경고 표시 가능)",
              "macOS 공증 적용" if macos_notarized else "macOS 공증 미적용(Gatekeeper 경고 표시 가능)"]
    return f"- 코드 서명: {', '.join(states)}. [코드 서명 정책]({SIGNING_POLICY})"


def notes(tag: str, changelog: str, *, installer: bool = True, unix: bool = True, windows_signed: bool = False, macos_notarized: bool = False,
          android: bool = False, android_signed: bool = False) -> str:
    """``installer``, ``unix`` 가 False면 해당 파일 줄 생략(0.5.0 이전은 Windows zip만, 0.6.0 이전은 Windows만).

    ``android``: 휴대폰 앱 APK 줄(1.0.0rc14부터). ``android_signed`` 가 False면 시험용 디버그 키 안내.

    ``windows_signed``, ``macos_notarized``: 릴리스 작업의 실제 서명, 공증 결과. 적용된 운영체제는 경고 안내를 뺀다.
    """
    version = tag.lstrip("v")
    body = section(changelog, version)
    lines = []
    if re.search(r"\d(?:a|b|rc)\d+$", version):
        lines += [f"사전 릴리스(1.0 후보). 실제 PC와 방송 계정으로 확인할 사용자를 위한 버전이며, 확인 방법과 보고 양식은 [실제 환경 확인]({VERIFY_URL}) 참고", ""]
    lines += ["## 설치", ""]
    if installer:
        lines.append(f"- Windows 설치 프로그램: `debutkit-{version}-windows-x64-setup.exe` 실행. 시작 메뉴에 debutkit 등록")
    lines.append(f"- Windows 압축 파일: `debutkit-{version}-windows-x64.zip` 압축 해제 후 `debutkit-gui.exe` 실행")
    if unix:
        first_run = "" if macos_notarized else ". 첫 실행은 Finder에서 우클릭 후 열기"
        lines += [
            f"- macOS(Apple Silicon): `debutkit-{version}-macos-arm64.zip` 압축 해제 후 debutkit.app 실행{first_run}",
            f"- Linux(x64): `debutkit-{version}-linux-x64.tar.gz` 압축 해제 후 `debutkit/debutkit-gui` 실행",
        ]
    if android:
        key = "" if android_signed else ". 시험용 서명이라 새 버전은 이전 앱을 지운 뒤 설치"
        lines += [f"- 휴대폰 앱(안드로이드 8 이상): `debutkit-phone-{version}-android.apk`를 휴대폰에서 설치(출처를 알 수 없는 앱 설치 허용){key}",
                  "- 휴대폰 앱(아이폰, 아이패드): 앱 스토어 배포 전. Mac과 Xcode로 직접 빌드(mobile/ios/README.md)"]
    lines += [
        "- 파이썬, 관리자 권한 불필요",
        signing_line(windows_signed, macos_notarized and unix),
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
    flags = ("--zip-only", "--windows-only", "--windows-signed", "--macos-notarized", "--android", "--android-signed")
    zip_only = "--zip-only" in args  # 0.5.0 이전: Windows zip만
    windows_only = "--windows-only" in args  # 0.5.x: Windows 설치 프로그램과 zip
    args_left = [arg for arg in args if arg not in flags]
    if len(args_left) != 1:
        print("사용: python packaging/release_notes.py v0.8.0 [--windows-only | --zip-only] [--windows-signed] [--macos-notarized] [--android] [--android-signed]",
              file=sys.stderr)
        return 2
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    text = notes(args_left[0], (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), installer=not zip_only, unix=not (zip_only or windows_only),
                 windows_signed="--windows-signed" in args, macos_notarized="--macos-notarized" in args, android="--android" in args,
                 android_signed="--android-signed" in args)
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
