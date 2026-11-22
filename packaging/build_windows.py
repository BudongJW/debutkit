"""Windows 실행 파일 만들기: PyInstaller로 한 폴더를 만들고 zip으로 묶은 뒤, 만든 프로그램을 실제로 실행해 확인한다.

    pip install -e ".[gui,build]"
    python packaging/build_windows.py                    # dist/debutkit-<버전>-windows-x64.zip
    python packaging/build_windows.py --installer        # 설치 프로그램 dist/debutkit-<버전>-windows-x64-setup.exe 도
    python packaging/build_windows.py --installer-only   # 이미 만든 dist/debutkit 폴더로 설치 프로그램만

설치 프로그램에는 Inno Setup 6(ISCC.exe)이 필요하다: PATH, Program Files, 또는 환경 변수 DEBUTKIT_ISCC.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = Path(__file__).with_name("installer.iss")
ISCC_PLACES = (r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe", r"C:\Program Files\Inno Setup 6\ISCC.exe")


def project_version() -> str:
    for line in (ROOT / "src" / "debutkit" / "__init__.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit("버전을 찾지 못함")


def archive_name(version: str, machine: str | None = None) -> str:
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64"}.get((machine or platform.machine()).lower(), "x64")
    return f"debutkit-{version}-windows-{arch}"


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
    """설치 프로그램이 내려받을 ffmpeg: 채팅 연결 모듈에 고정된 빌드."""
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


def smoke_test(folder: Path) -> None:
    """만든 프로그램이 파이썬 없이 켜지는지: 명령줄은 버전, 점검, 설계도, 창은 화면 없이 띄웠다 닫기."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    for args in (["--version"], ["doctor", "--json"], ["scenes", "--dry-run"], ["setup"]):
        done = subprocess.run([str(folder / "debutkit.exe"), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=120)
        if done.returncode not in (0, 1):  # doctor는 필요 항목이, setup은 ffmpeg가 없으면 1
            raise SystemExit(f"debutkit {' '.join(args)} 실패 ({done.returncode}): {done.stderr[-500:]}")
        print(f"  debutkit {' '.join(args)}: ok")
    gui = subprocess.Popen([str(folder / "debutkit-gui.exe")], env={**env, "QT_QPA_PLATFORM": "offscreen", "DEBUTKIT_SMOKE": "1"})
    try:
        code = gui.wait(timeout=60)
    except subprocess.TimeoutExpired:
        gui.kill()
        raise SystemExit("debutkit-gui 가 스스로 끝나지 않음") from None
    if code != 0:
        raise SystemExit(f"debutkit-gui 실패 ({code})")
    print("  debutkit-gui (화면 없이 열고 닫기): ok")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dist", default=str(ROOT / "dist"))
    parser.add_argument("--no-smoke", action="store_true", help="만든 프로그램 실행 확인 생략")
    parser.add_argument("--installer", action="store_true", help="설치 프로그램도 만들기 (Inno Setup 6 필요)")
    parser.add_argument("--installer-only", action="store_true", help="빌드 없이 이미 만든 dist/debutkit 폴더로 설치 프로그램만")
    args = parser.parse_args(argv)
    dist, work = Path(args.dist), ROOT / "build" / "pyinstaller"
    folder = dist / "debutkit"
    if args.installer_only:
        if not (folder / "debutkit.exe").is_file():
            parser.error("--installer-only 에는 먼저 만든 dist/debutkit 폴더 필요")
        print(make_installer(folder, dist, project_version()))
        return 0
    if args.installer and not find_iscc():  # 긴 빌드 전에 확인
        parser.error("--installer 에는 Inno Setup 6(ISCC.exe) 필요: 설치하거나 DEBUTKIT_ISCC 에 경로 지정")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(dist), "--workpath", str(work),
                    str(ROOT / "packaging" / "debutkit.spec")], check=True)
    for name in ("LICENSE", "README.md"):
        shutil.copy2(ROOT / name, folder / name)
    if not args.no_smoke:
        smoke_test(folder)
    name = archive_name(project_version())
    archive = shutil.make_archive(str(dist / name), "zip", root_dir=dist, base_dir="debutkit")
    size = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()) / 1024**2
    print(f"{archive}  (풀면 {size:.0f} MB)")
    if args.installer:
        print(make_installer(folder, dist, project_version()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
