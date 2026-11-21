"""Windows 실행 파일 만들기: PyInstaller로 한 폴더를 만들고 zip으로 묶은 뒤, 만든 프로그램을 실제로 실행해 확인한다.

    pip install -e ".[gui,build]"
    python packaging/build_windows.py            # dist/debutkit-<버전>-windows-x64.zip
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


def project_version() -> str:
    for line in (ROOT / "src" / "debutkit" / "__init__.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit("버전을 찾지 못함")


def archive_name(version: str, machine: str | None = None) -> str:
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64"}.get((machine or platform.machine()).lower(), "x64")
    return f"debutkit-{version}-windows-{arch}"


def smoke_test(folder: Path) -> None:
    """만든 프로그램이 파이썬 없이 켜지는지: 명령줄은 버전·점검·설계도, 창은 화면 없이 띄웠다 닫기."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    for args in (["--version"], ["doctor", "--json"], ["scenes", "--dry-run"]):
        done = subprocess.run([str(folder / "debutkit.exe"), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=120)
        if done.returncode not in (0, 1):  # doctor는 '필요' 항목이 있으면 1
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", default=str(ROOT / "dist"))
    parser.add_argument("--no-smoke", action="store_true", help="만든 프로그램 실행 확인 생략")
    args = parser.parse_args(argv)
    dist, work = Path(args.dist), ROOT / "build" / "pyinstaller"
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(dist), "--workpath", str(work),
                    str(ROOT / "packaging" / "debutkit.spec")], check=True)
    folder = dist / "debutkit"
    for name in ("LICENSE", "README.md"):
        shutil.copy2(ROOT / name, folder / name)
    if not args.no_smoke:
        smoke_test(folder)
    name = archive_name(project_version())
    archive = shutil.make_archive(str(dist / name), "zip", root_dir=dist, base_dir="debutkit")
    size = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()) / 1024**2
    print(f"{archive}  (풀면 {size:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
