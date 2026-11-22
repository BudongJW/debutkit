"""실행 파일 만들기(Windows, macOS, Linux): PyInstaller로 만들고, 파이썬 없이 실행해 확인한 뒤 압축한다.

    pip install -e ".[gui,build]"
    python packaging/build_app.py

| 운영체제 | 결과 |
|---|---|
| Windows | dist/debutkit-버전-windows-x64.zip (debutkit 폴더) |
| macOS | dist/debutkit-버전-macos-arm64.zip (debutkit.app) |
| Linux | dist/debutkit-버전-linux-x64.tar.gz (debutkit 폴더) |

Windows 설치 프로그램과 코드 서명은 packaging/build_windows.py가 담당한다.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "debutkit.spec"
SYSTEMS = {"win32": "windows", "darwin": "macos"}


def project_version() -> str:
    for line in (ROOT / "src" / "debutkit" / "__init__.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit("버전을 찾지 못함")


def system_name(platform_name: str | None = None) -> str:
    return SYSTEMS.get(platform_name or sys.platform, "linux")


def archive_name(version: str, machine: str | None = None, platform_name: str | None = None) -> str:
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get((machine or platform.machine()).lower(), "x64")
    return f"debutkit-{version}-{system_name(platform_name)}-{arch}"


def build(dist: Path, work: Path) -> None:
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(dist), "--workpath", str(work), str(SPEC)],
                   check=True, cwd=ROOT)


def product(dist: Path, platform_name: str | None = None) -> Path:
    """배포할 폴더: macOS는 debutkit.app, 그 밖은 debutkit 폴더."""
    return dist / ("debutkit.app" if (platform_name or sys.platform) == "darwin" else "debutkit")


def programs(item: Path, platform_name: str | None = None) -> tuple[Path, Path]:
    """(명령줄, 설정 마법사) 실행 파일 경로."""
    platform_name = platform_name or sys.platform
    if platform_name == "darwin":
        base = item / "Contents" / "MacOS"
        return base / "debutkit", base / "debutkit-gui"
    suffix = ".exe" if platform_name == "win32" else ""
    return item / f"debutkit{suffix}", item / f"debutkit-gui{suffix}"


def smoke_test(cli: Path, gui: Path) -> None:
    """파이썬 없이 켜지는지: 명령줄은 버전, 점검, 장면 설계, 준비 도구, 설정 마법사는 화면 없이 띄웠다 닫기."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    for args in (["--version"], ["doctor", "--json"], ["scenes", "--dry-run"], ["setup"]):
        done = subprocess.run([str(cli), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=180)
        if done.returncode not in (0, 1):  # doctor는 필요 항목이, setup은 ffmpeg가 없으면 1
            raise SystemExit(f"debutkit {' '.join(args)} 실패 ({done.returncode}): {done.stderr[-800:]}")
        print(f"  debutkit {' '.join(args)}: 정상")
    process = subprocess.Popen([str(gui)], env={**env, "QT_QPA_PLATFORM": "offscreen", "DEBUTKIT_SMOKE": "1"})
    try:
        code = process.wait(timeout=90)
    except subprocess.TimeoutExpired:
        process.kill()
        raise SystemExit("debutkit-gui가 종료되지 않음") from None
    if code != 0:
        raise SystemExit(f"debutkit-gui 실패 ({code})")
    print("  debutkit-gui(화면 없이 열고 닫기): 정상")


def archive(item: Path, dist: Path, name: str, platform_name: str | None = None) -> Path:
    platform_name = platform_name or sys.platform
    if platform_name == "darwin":  # 실행 권한과 묶음 구조를 보존하는 macOS 기본 도구
        out = dist / f"{name}.zip"
        out.unlink(missing_ok=True)
        subprocess.run(["ditto", "-c", "-k", "--keepParent", str(item), str(out)], check=True)
        return out
    if platform_name == "win32":
        return Path(shutil.make_archive(str(dist / name), "zip", root_dir=dist, base_dir=item.name))
    return Path(shutil.make_archive(str(dist / name), "gztar", root_dir=dist, base_dir=item.name))


def size_mb(item: Path) -> float:
    return sum(path.stat().st_size for path in item.rglob("*") if path.is_file()) / 1024**2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dist", default=str(ROOT / "dist"))
    parser.add_argument("--no-smoke", action="store_true", help="만든 프로그램 실행 확인 생략")
    args = parser.parse_args(argv)
    dist = Path(args.dist)
    build(dist, ROOT / "build" / "pyinstaller")
    item = product(dist)
    for name in ("LICENSE", "README.md"):
        target = item / "Contents" / "Resources" if sys.platform == "darwin" else item
        shutil.copy2(ROOT / name, target / name)
    if not args.no_smoke:
        smoke_test(*programs(item))
    out = archive(item, dist, archive_name(project_version()))
    print(f"{out}  (압축 해제 시 {size_mb(item):.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
