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


def test_installer_script_is_utf8_with_bom_and_has_no_claude():
    raw = (ROOT / "packaging" / "installer.iss").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # Inno Setup이 한국어 문구를 UTF-8로 읽도록
    text = raw.decode("utf-8-sig")
    assert "AppId=" in text and "PrivilegesRequired=lowest" in text
    assert "claude" not in text.lower()
