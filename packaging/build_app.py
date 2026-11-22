"""실행 파일 만들기(Windows, macOS, Linux): PyInstaller로 만들고, 파이썬 없이 실행해 확인한 뒤 압축한다.

    pip install -e ".[gui,build]"
    python packaging/build_app.py

| 운영체제 | 결과 |
|---|---|
| Windows | dist/debutkit-버전-windows-x64.zip (debutkit 폴더) |
| macOS | dist/debutkit-버전-macos-arm64.zip (debutkit.app) |
| Linux | dist/debutkit-버전-linux-x64.tar.gz (debutkit 폴더) |

Windows 설치 프로그램과 코드 서명은 packaging/build_windows.py가 담당한다.

macOS 서명: 강화된 런타임(hardened runtime)과 packaging/macos/entitlements.plist로 debutkit.app 전체에 서명한 뒤
실행을 확인한다. 환경 변수 DEBUTKIT_MACOS_IDENTITY(Developer ID Application 인증서 이름)가 없으면 임시 서명(ad-hoc).
DEBUTKIT_NOTARY_APPLE_ID, DEBUTKIT_NOTARY_TEAM_ID, DEBUTKIT_NOTARY_PASSWORD(앱 암호)가 있으면 공증과 스테이플까지 진행.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "debutkit.spec"
ENTITLEMENTS = ROOT / "packaging" / "macos" / "entitlements.plist"
SYSTEMS = {"win32": "windows", "darwin": "macos"}
# 위젯 화면만 사용: Qt Quick, QML, PDF, 가상 키보드, 소프트웨어 OpenGL 라이브러리는 PySide6 수집 규칙이 함께 넣지만 쓰지 않음
UNUSED_QT = ("qt6quick", "qtquick", "qt6qml", "qtqml", "qt6pdf", "qtpdf", "qpdf", "virtualkeyboard", "opengl32sw")


def unused(dest: str) -> bool:
    """묶음에서 뺄 Qt 파일인지."""
    name = dest.replace("\\", "/").lower()
    return "pyside6/" in name and any(part in name for part in UNUSED_QT)


def dropped(entry: tuple[Any, ...]) -> bool:
    """PyInstaller 목록(TOC)에서 뺄 항목(debutkit.spec에서 사용).

    macOS에서 PyInstaller가 만드는 최상위 바로 가기(예: Contents/Frameworks/QtPdf, 형식 SYMLINK)는
    이름에 PySide6 경로가 없으므로 가리키는 대상으로 판단한다. 남기면 대상이 없는 바로 가기가 되어 서명 검증 실패.
    """
    dest, source, kind = str(entry[0]), str(entry[1]), entry[2] if len(entry) > 2 else ""
    return unused(dest) or (kind == "SYMLINK" and unused(source))


def windows_version_info(version: str, description: str, filename: str) -> Any:
    """Windows 실행 파일의 버전 정보(제품 이름, 제품 버전 등). 코드 서명 서비스가 이 값으로 서명 대상을 확인한다."""
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    numbers = tuple((list(map(int, version.split(".")[:3])) + [0, 0, 0, 0])[:4])
    strings = [("CompanyName", "debutkit"), ("FileDescription", description), ("FileVersion", version), ("InternalName", Path(filename).stem),
               ("LegalCopyright", "Apache-2.0"), ("OriginalFilename", filename), ("ProductName", "debutkit"), ("ProductVersion", version)]
    return VSVersionInfo(ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
                         kids=[StringFileInfo([StringTable("041204B0", [StringStruct(name, value) for name, value in strings])]),
                               VarFileInfo([VarStruct("Translation", [0x0412, 1200])])])


def version_strings(path: Path) -> dict[str, str]:
    """Windows 실행 파일에 기록된 버전 정보 문자열(Windows 전용)."""
    import ctypes
    from ctypes import wintypes

    api = ctypes.windll.version  # type: ignore[attr-defined]
    size = api.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        return {}
    data = ctypes.create_string_buffer(size)
    api.GetFileVersionInfoW(str(path), 0, size, data)
    pointer, length = ctypes.c_void_p(), wintypes.UINT()
    if not api.VerQueryValueW(data, "\\VarFileInfo\\Translation", ctypes.byref(pointer), ctypes.byref(length)) or not length.value:
        return {}
    language, codepage = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_ushort * 2)).contents
    found = {}
    for name in ("ProductName", "ProductVersion", "FileDescription", "OriginalFilename", "CompanyName"):
        value = ctypes.c_void_p()
        if api.VerQueryValueW(data, f"\\StringFileInfo\\{language:04x}{codepage:04x}\\{name}", ctypes.byref(value), ctypes.byref(length)) and length.value:
            found[name] = ctypes.wstring_at(value, length.value - 1).rstrip("\x00 ")  # Inno Setup은 문자열 끝을 공백으로 채움
    return found


def check_version_info(files: list[Path], version: str) -> None:
    """서명 전에 제품 이름과 버전이 기록되었는지 확인(Windows)."""
    for path in files:
        found = version_strings(path)
        if found.get("ProductName") != "debutkit" or found.get("ProductVersion") != version:
            raise SystemExit(f"버전 정보 누락 또는 불일치: {path.name} {found}")
        print(f"  버전 정보: {path.name}, {found['ProductName']} {found['ProductVersion']}, {found.get('FileDescription', '')}")


def remove_broken_links(item: Path) -> list[str]:
    """대상이 없는 바로 가기 삭제(서명 검증과 공증은 이를 오류로 처리)."""
    removed = []
    for folder, dirs, files in os.walk(item):
        for name in dirs + files:
            path = Path(folder) / name
            if path.is_symlink() and not path.exists():
                path.unlink()
                removed.append(path.relative_to(item).as_posix())
    return removed


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
    smoke_gui(gui, env)
    print("  debutkit-gui(화면 없이 열고 닫기): 정상")


def smoke_gui(gui: Path, env: dict[str, str], *, attempts: int = 2, popen: Callable[..., Any] = subprocess.Popen) -> None:
    """설정 마법사를 화면 없이 열고 닫는다. 신호로 종료되면(macOS에서 간헐 발생, docs/ROADMAP.md) 경고 후 한 번 더 시도."""
    for attempt in range(1, attempts + 1):
        process = popen([str(gui)], env={**env, "QT_QPA_PLATFORM": "offscreen", "DEBUTKIT_SMOKE": "1"})
        try:
            code = process.wait(timeout=90)
        except subprocess.TimeoutExpired:
            process.kill()
            raise SystemExit("debutkit-gui가 종료되지 않음") from None
        if code == 0:
            return
        if code > 0 or attempt == attempts:
            raise SystemExit(f"debutkit-gui 실패 ({code})")
        print(f"::warning::debutkit-gui가 신호 {-code}로 종료됨({attempt}회차). 다시 시도")


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


def sign_macos(app: Path, identity: str | None = None, *, run: Callable[..., Any] = subprocess.run) -> str:
    """debutkit.app 전체를 강화된 런타임으로 서명하고 검증. 반환: 사용한 서명 이름("-"는 임시 서명)."""
    identity = identity or os.environ.get("DEBUTKIT_MACOS_IDENTITY") or "-"
    command = ["codesign", "--force", "--deep", "--options", "runtime", "--entitlements", str(ENTITLEMENTS), "--sign", identity]
    if identity != "-":
        command.append("--timestamp")  # 공증에 필요
    run([*command, str(app)], check=True)
    run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)], check=True)
    return identity


def notary_config() -> tuple[str, str, str] | None:
    values = tuple(os.environ.get(name, "") for name in ("DEBUTKIT_NOTARY_APPLE_ID", "DEBUTKIT_NOTARY_TEAM_ID", "DEBUTKIT_NOTARY_PASSWORD"))
    return values if all(values) else None  # type: ignore[return-value]


def notarize(app: Path, dist: Path, config: tuple[str, str, str], *, run: Callable[..., Any] = subprocess.run) -> str:
    """Apple 공증 제출, 승인 대기, 스테이플, Gatekeeper 평가. 반환: 제출 ID."""
    apple_id, team, password = config
    upload = dist / "notarize.zip"
    upload.unlink(missing_ok=True)
    run(["ditto", "-c", "-k", "--keepParent", str(app), str(upload)], check=True)
    done = run(["xcrun", "notarytool", "submit", str(upload), "--apple-id", apple_id, "--team-id", team, "--password", password,
                "--wait", "--output-format", "json"], check=True, capture_output=True, text=True)
    upload.unlink(missing_ok=True)
    result = json.loads(done.stdout or "{}")
    if result.get("status") != "Accepted":
        submission = str(result.get("id", ""))
        if submission:
            log = run(["xcrun", "notarytool", "log", submission, "--apple-id", apple_id, "--team-id", team, "--password", password],
                      capture_output=True, text=True)
            print(log.stdout[-3000:])
        raise SystemExit(f"공증 실패: {result.get('status')} {result.get('message', '')}")
    run(["xcrun", "stapler", "staple", str(app)], check=True)
    run(["spctl", "--assess", "--type", "execute", "--verbose=2", str(app)], check=True)
    return str(result.get("id", ""))


def size_mb(item: Path) -> float:
    return sum(path.stat().st_size for path in item.rglob("*") if path.is_file()) / 1024**2


def largest(item: Path, count: int = 8) -> list[str]:
    """용량 점검용: 큰 파일 목록."""
    files = sorted((path for path in item.rglob("*") if path.is_file() and not path.is_symlink()), key=lambda path: path.stat().st_size, reverse=True)
    return [f"{path.stat().st_size / 1024**2:6.1f} MB  {path.relative_to(item)}" for path in files[:count]]


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
    broken = remove_broken_links(item)
    if broken:
        print(f"  대상이 없는 바로 가기 {len(broken)}개 삭제: " + ", ".join(broken[:8]))
    if sys.platform == "darwin":  # 파일을 넣은 뒤 서명해야 묶음 서명이 유효
        identity = sign_macos(item)
        print("  서명: " + ("임시 서명(ad-hoc), 강화된 런타임" if identity == "-" else f"{identity}, 강화된 런타임"))
    if not args.no_smoke:
        smoke_test(*programs(item))
    if sys.platform == "darwin" and (config := notary_config()):
        if identity == "-":
            raise SystemExit("공증에는 Developer ID 서명 필요: DEBUTKIT_MACOS_IDENTITY(인증서) 확인")
        print(f"  공증 완료: 제출 {notarize(item, dist, config)}, 스테이플, Gatekeeper 확인")
        if os.environ.get("GITHUB_OUTPUT"):  # 릴리스 노트용
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
                output.write("notarized=true\n")
    out = archive(item, dist, archive_name(project_version()))
    print(f"{out}  (압축 해제 시 {size_mb(item):.0f} MB)")
    print("큰 파일:\n  " + "\n  ".join(largest(item)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
