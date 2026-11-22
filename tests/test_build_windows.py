import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packaging"))

import build_windows  # noqa: E402

FFMPEG = SimpleNamespace(url="https://example.com/ff.zip", filename="ff.zip", sha256="ab" * 32, megabytes=115)


def test_installer_command_passes_version_folders_and_ffmpeg(tmp_path):
    command = build_windows.installer_command("ISCC.exe", tmp_path / "debutkit", tmp_path, "0.5.0", FFMPEG, machine="AMD64")
    assert command[0] == "ISCC.exe" and command[-1].endswith("installer.iss")
    assert "/DAppVersion=0.5.0" in command and "/DOutputName=debutkit-0.5.0-windows-x64-setup" in command
    assert f"/DFfmpegUrl={FFMPEG.url}" in command and "/DFfmpegSize=115" in command and f"/DFfmpegSha256={FFMPEG.sha256}" in command


def test_find_iscc_from_environment(monkeypatch, tmp_path):
    iscc = tmp_path / "ISCC.exe"
    iscc.write_bytes(b"")
    monkeypatch.setenv("DEBUTKIT_ISCC", str(iscc))
    assert build_windows.find_iscc() == str(iscc)
    monkeypatch.setenv("DEBUTKIT_ISCC", str(tmp_path / "missing.exe"))
    assert build_windows.find_iscc() is None


def test_make_installer_runs_iscc_and_finds_the_file(tmp_path):
    ran = []

    def run(command, check):
        ran.append(command)
        (tmp_path / f"{build_windows.installer_name('0.5.0')}.exe").write_bytes(b"MZ")  # 이 PC 아키텍처 이름(x64, arm64)

    setup = build_windows.make_installer(tmp_path / "debutkit", tmp_path, "0.5.0", iscc="ISCC.exe", ffmpeg=FFMPEG, run=run)
    assert setup.name.endswith("-setup.exe") and ran


def test_signing_is_skipped_without_a_certificate(monkeypatch, tmp_path):
    monkeypatch.delenv("DEBUTKIT_SIGN_PFX", raising=False)
    ran = []
    assert build_windows.sign([tmp_path / "debutkit.exe"], run=lambda *a, **k: ran.append(a)) is False and ran == []


def test_signing_uses_signtool_with_timestamp(monkeypatch, tmp_path):
    pfx = tmp_path / "cert.pfx"
    pfx.write_bytes(b"x")
    monkeypatch.setenv("DEBUTKIT_SIGN_PFX", str(pfx))
    monkeypatch.setenv("DEBUTKIT_SIGN_PASSWORD", "pw")
    monkeypatch.setattr(build_windows, "find_signtool", lambda: "signtool.exe")
    ran = []
    assert build_windows.sign([tmp_path / "a.exe", tmp_path / "b.exe"], run=lambda command, check: ran.append(command))
    command = ran[0]
    assert command[:3] == ["signtool.exe", "sign", "/fd"] and "/tr" in command and "/td" in command
    assert command[-2:] == [str(tmp_path / "a.exe"), str(tmp_path / "b.exe")]


def test_archive_names_per_system():
    import build_app

    assert build_app.archive_name("0.6.0", "AMD64", "win32") == "debutkit-0.6.0-windows-x64"
    assert build_app.archive_name("0.6.0", "arm64", "darwin") == "debutkit-0.6.0-macos-arm64"
    assert build_app.archive_name("0.6.0", "x86_64", "linux") == "debutkit-0.6.0-linux-x64"
    cli, gui = build_app.programs(Path("dist/debutkit.app"), "darwin")
    assert cli.parts[-3:] == ("Contents", "MacOS", "debutkit") and gui.name == "debutkit-gui"
    assert build_app.programs(Path("dist/debutkit"), "linux")[0].name == "debutkit"


def test_unused_qt_files_are_dropped_and_needed_ones_kept():
    import build_app

    dropped = ["PySide6\\Qt6Quick.dll", "PySide6\\Qt6QmlModels.dll", "PySide6\\Qt6Pdf.dll", "PySide6\\opengl32sw.dll",
               "PySide6\\plugins\\imageformats\\qpdf.dll", "PySide6/Qt/plugins/platforminputcontexts/libqtvirtualkeyboardplugin.so",
               "PySide6/Qt/lib/libQt6Quick.so.6", "PySide6/Qt/lib/QtPdf.framework/Versions/A/QtPdf"]
    kept = ["PySide6\\Qt6Core.dll", "PySide6\\Qt6Gui.dll", "PySide6\\Qt6Widgets.dll", "PySide6\\Qt6OpenGL.dll", "PySide6\\plugins\\platforms\\qwindows.dll",
            "PySide6/Qt/plugins/platforms/libqxcb.so", "PySide6/Qt/plugins/platformthemes/libqgtk3.so", "PySide6/Qt/lib/libicudata.so.73",
            "PySide6/Qt/plugins/platforms/libqcocoa.dylib", "grpc/_cython/cygrpc.cpython-312-x86_64-linux-gnu.so", "numpy.libs/libscipy_openblas64_.so"]
    assert all(build_app.unused(name) for name in dropped)
    assert not any(build_app.unused(name) for name in kept)


def test_installer_script_is_utf8_with_bom_and_has_no_claude():
    raw = (ROOT / "packaging" / "installer.iss").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # Inno Setup이 한국어 문구를 UTF-8로 읽도록
    text = raw.decode("utf-8-sig")
    assert "AppId=" in text and "PrivilegesRequired=lowest" in text
    assert "claude" not in text.lower()
