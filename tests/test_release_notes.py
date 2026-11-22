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


def test_oldest_version_has_no_compare_link():
    assert "compare/" not in release_notes.notes("v0.2.0", CHANGELOG)


def test_missing_version_fails():
    with pytest.raises(ValueError, match="0.9.0"):
        release_notes.notes("v0.9.0", CHANGELOG)


def test_real_changelog_has_the_current_version():
    from debutkit import __version__

    text = release_notes.notes(f"v{__version__}", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    assert "claude" not in text.lower() and "anthropic" not in text.lower()
