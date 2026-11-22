"""Windows 배포 파일 만들기: 실행 파일(zip), 설치 프로그램(setup.exe), 코드 서명(인증서가 있을 때).

    pip install -e ".[gui,build]"
    python packaging/build_windows.py                    # dist/debutkit-<버전>-windows-x64.zip
    python packaging/build_windows.py --installer        # 설치 프로그램 dist/debutkit-<버전>-windows-x64-setup.exe 도
    python packaging/build_windows.py --installer-only   # 이미 만든 dist/debutkit 폴더로 설치 프로그램만

- 설치 프로그램: Inno Setup 6(ISCC.exe) 필요. PATH, Program Files, 또는 환경 변수 DEBUTKIT_ISCC
- 코드 서명: 환경 변수 DEBUTKIT_SIGN_PFX(인증서 파일)와 DEBUTKIT_SIGN_PASSWORD가 있으면 실행 파일과
  설치 프로그램에 서명(signtool, SHA-256, 타임스탬프). 없으면 서명 없이 진행. 절차: docs/RELEASING.md
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_app  # noqa: E402

ROOT = build_app.ROOT
INSTALLER = Path(__file__).with_name("installer.iss")
ISCC_PLACES = (r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe", r"C:\Program Files\Inno Setup 6\ISCC.exe")
TIMESTAMP_URL = os.environ.get("DEBUTKIT_SIGN_TIMESTAMP", "http://timestamp.digicert.com")
project_version = build_app.project_version


def archive_name(version: str, machine: str | None = None) -> str:
    return build_app.archive_name(version, machine, "win32")


def installer_name(version: str, machine: str | None = None) -> str:
    return archive_name(version, machine) + "-setup"


def find_iscc(places: tuple[str, ...] = ISCC_PLACES) -> str | None:
    """Inno Setup 명령줄 컴파일러: DEBUTKIT_ISCC, PATH, 기본 설치 폴더 순서."""
    wanted = os.environ.get("DEBUTKIT_ISCC")
    if wanted:
        return wanted if Path(wanted).is_file() else None
    found = shutil.which("iscc") or shutil.which("ISCC")
    if found:
        return found
    return next((place for place in places if Path(place).is_file()), None)


def ffmpeg_build() -> Any:
    """설치 프로그램이 다운로드할 ffmpeg: 채팅 연결 모듈에 고정된 빌드."""
    from stream2clip.tools import FFMPEG_BUILD

    return FFMPEG_BUILD


def installer_command(iscc: str, folder: Path, dist: Path, version: str, ffmpeg: Any, machine: str | None = None) -> list[str]:
    """packaging/installer.iss 컴파일: 만든 폴더를 넣고 ``dist`` 에 ``-setup.exe`` 를 만든다."""
    return [
        iscc, "/Qp", f"/DAppVersion={version}", f"/DSourceDir={folder.resolve()}", f"/DOutputDir={dist.resolve()}",
        f"/DOutputName={installer_name(version, machine)}",
        f"/DFfmpegUrl={ffmpeg.url}", f"/DFfmpegFile={ffmpeg.filename}", f"/DFfmpegSha256={ffmpeg.sha256}", f"/DFfmpegSize={ffmpeg.megabytes}",
        str(INSTALLER),
    ]


def make_installer(folder: Path, dist: Path, version: str, *, iscc: str | None = None, ffmpeg: Any = None,
                   run: Callable[..., Any] = subprocess.run) -> Path:
    iscc = iscc or find_iscc()
    if not iscc:
        raise SystemExit("설치 프로그램에는 Inno Setup 6(ISCC.exe) 필요: 설치하거나 DEBUTKIT_ISCC 에 경로 지정")
    run(installer_command(iscc, folder, dist, version, ffmpeg or ffmpeg_build()), check=True)
    setup = dist / f"{installer_name(version)}.exe"
    if not setup.is_file():
        raise SystemExit(f"설치 프로그램이 만들어지지 않음: {setup}")
    return setup


def find_signtool() -> str | None:
    """Windows SDK의 signtool.exe(가장 높은 버전의 x64)."""
    found = shutil.which("signtool")
    if found:
        return found
    candidates = sorted(glob.glob(r"C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe"))
    return candidates[-1] if candidates else None


def signing() -> tuple[str, str] | None:
    """(인증서 파일, 비밀번호). 서명 설정이 없으면 None."""
    pfx, password = os.environ.get("DEBUTKIT_SIGN_PFX", ""), os.environ.get("DEBUTKIT_SIGN_PASSWORD", "")
    return (pfx, password) if pfx and Path(pfx).is_file() else None


def sign_command(signtool: str, pfx: str, password: str, files: list[Path]) -> list[str]:
    return [signtool, "sign", "/fd", "SHA256", "/f", pfx, "/p", password, "/tr", TIMESTAMP_URL, "/td", "SHA256", *[str(file) for file in files]]


def sign(files: list[Path], *, run: Callable[..., Any] = subprocess.run) -> bool:
    """서명 설정이 있으면 서명하고 True, 없으면 False."""
    config = signing()
    if config is None:
        return False
    signtool = find_signtool()
    if not signtool:
        raise SystemExit("코드 서명에는 signtool.exe(Windows SDK) 필요")
    run(sign_command(signtool, *config, files), check=True)
    print("  코드 서명: " + ", ".join(file.name for file in files))
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dist", default=str(ROOT / "dist"))
    parser.add_argument("--no-smoke", action="store_true", help="만든 프로그램 실행 확인 생략")
    parser.add_argument("--installer", action="store_true", help="설치 프로그램도 만들기 (Inno Setup 6 필요)")
    parser.add_argument("--installer-only", action="store_true", help="빌드 없이 이미 만든 dist/debutkit 폴더로 설치 프로그램만")
    args = parser.parse_args(argv)
    dist = Path(args.dist)
    folder = dist / "debutkit"
    version = project_version()
    if args.installer_only:
        if not (folder / "debutkit.exe").is_file():
            parser.error("--installer-only 에는 먼저 만든 dist/debutkit 폴더 필요")
        setup = make_installer(folder, dist, version)
        sign([setup])
        print(setup)
        return 0
    if args.installer and not find_iscc():  # 긴 빌드 전에 확인
        parser.error("--installer 에는 Inno Setup 6(ISCC.exe) 필요: 설치하거나 DEBUTKIT_ISCC 에 경로 지정")
    build_app.build(dist, ROOT / "build" / "pyinstaller")
    for name in ("LICENSE", "README.md"):
        shutil.copy2(ROOT / name, folder / name)
    cli, gui = build_app.programs(folder, "win32")
    sign([cli, gui])
    if not args.no_smoke:
        build_app.smoke_test(cli, gui)
    archive = build_app.archive(folder, dist, archive_name(version), "win32")
    print(f"{archive}  (압축 해제 시 {build_app.size_mb(folder):.0f} MB)")
    if args.installer:
        setup = make_installer(folder, dist, version)
        sign([setup])
        print(setup)
    return 0


if __name__ == "__main__":
    sys.exit(main())
