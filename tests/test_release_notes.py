import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packaging"))

import release_notes  # noqa: E402

CHANGELOG = """# 변경 내역

## 0.3.0 (2026-11-22)

### 추가
- 기능 A

### 수정
- 문제 B

## 0.2.0 (2026-11-21)

- 이전 항목
"""


def test_notes_take_the_version_section_with_install_and_compare_link():
    text = release_notes.notes("v0.3.0", CHANGELOG)
    assert text.startswith("## 설치")
    assert "debutkit-0.3.0-windows-x64.zip" in text
    assert "## 추가\n- 기능 A" in text and "## 수정\n- 문제 B" in text
    assert "이전 항목" not in text
    assert "compare/v0.2.0...v0.3.0" in text


def test_zip_only_releases_omit_the_installer():
    text = release_notes.notes("v0.3.0", CHANGELOG, installer=False, unix=False)
    assert "setup.exe" not in text and "macos" not in text and "debutkit-0.3.0-windows-x64.zip" in text


def test_current_releases_list_every_platform():
    text = release_notes.notes("v0.3.0", CHANGELOG)
    for name in ("windows-x64-setup.exe", "windows-x64.zip", "macos-arm64.zip", "linux-x64.tar.gz"):
        assert f"debutkit-0.3.0-{name}" in text


def test_oldest_version_has_no_compare_link():
    assert "compare/" not in release_notes.notes("v0.2.0", CHANGELOG)


def test_missing_version_fails():
    with pytest.raises(ValueError, match="0.9.0"):
        release_notes.notes("v0.9.0", CHANGELOG)


def test_real_changelog_has_the_current_version():
    from debutkit import __version__

    text = release_notes.notes(f"v{__version__}", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    assert "claude" not in text.lower() and "anthropic" not in text.lower()


def test_signing_state_follows_the_release_job():
    unsigned = release_notes.notes("v0.3.0", CHANGELOG)
    assert "Windows 서명 미적용" in unsigned and "macOS 공증 미적용" in unsigned and "우클릭 후 열기" in unsigned
    assert "[코드 서명 정책](https://budongjw.github.io/debutkit/signing.html)" in unsigned
    signed = release_notes.notes("v0.3.0", CHANGELOG, windows_signed=True, macos_notarized=True)
    assert "Windows 서명 적용, macOS 공증 적용" in signed and "경고" not in signed and "우클릭" not in signed
    assert "코드 서명 정책" in signed


def test_cli_flags(capsys, monkeypatch):
    monkeypatch.setattr(release_notes, "ROOT", ROOT)
    from debutkit import __version__

    assert release_notes.main([f"v{__version__}", "--windows-signed"]) == 0
    out = capsys.readouterr().out
    assert "Windows 서명 적용" in out and "macOS 공증 미적용" in out


def test_prerelease_notes_and_compare_link():
    changelog = CHANGELOG.replace("# 변경 내역\n", "# 변경 내역\n\n## 1.0.0rc1 (2026-11-23)\n\n- 후보\n")
    text = release_notes.notes("v1.0.0rc1", changelog)
    assert text.startswith("사전 릴리스(1.0 후보)") and "join.html#verify" in text and "compare/v0.3.0...v1.0.0rc1" in text
    assert "debutkit-1.0.0rc1-windows-x64-setup.exe" in text
    assert "사전 릴리스" not in release_notes.notes("v0.3.0", changelog)


def test_version_helpers():
    import build_app

    assert build_app.numeric_version("1.0.0rc1") == "1.0.0" and build_app.numeric_version("0.9.0") == "0.9.0"
    assert build_app.is_prerelease("1.0.0rc1") and not build_app.is_prerelease("1.0.0")
