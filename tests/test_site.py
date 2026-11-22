"""사이트와 문서: 내부 링크, 표기 원칙(중간점, 꺽쇠, 화살표 등 특수문자 미사용)."""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packaging"))

import build_site  # noqa: E402

#: 문서와 화면 글에 쓰지 않는 문자
FORBIDDEN = "·・‧∙→←↔⇒⇐〈〉《》「」『』【】※×—–…“”‘’"
DOCS = [ROOT / "README.md", ROOT / "CHANGELOG.md", ROOT / "CONTRIBUTING.md", *sorted((ROOT / "docs").glob("*.md")),
        *sorted((ROOT / "membership").glob("*.md"))]
PAGES = sorted((ROOT / "site").rglob("*.html"))
SOURCES = sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "src").rglob("*.html")) + sorted((ROOT / "src").rglob("*.js"))


def _prose_markdown(text: str) -> str:
    """코드 블록, mermaid 블록, 인라인 코드, 링크 주소, 표 구분선을 뺀 본문."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", "", text)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    text = re.sub(r"<[^>\n]+>", "", text)  # README 머리의 HTML 태그
    return text


def _prose_html(text: str) -> str:
    text = re.sub(r"<(pre|code|script|style)\b.*?</\1>", "", text, flags=re.S)
    return re.sub(r"<[^>]+>", " ", text)


def test_site_has_no_broken_internal_links(tmp_path):
    built = build_site.build(tmp_path / "site")
    assert (built / ".nojekyll").is_file() and (built / "index.html").is_file()
    assert build_site.broken_links(built) == []


def test_relative_output_folder(tmp_path, monkeypatch):
    """Pages 워크플로처럼 상대 경로(-o _site)로 만들어도 #id 링크를 제대로 찾는다."""
    monkeypatch.chdir(tmp_path)
    built = build_site.build("_site")
    assert build_site.broken_links(Path("_site")) == [] and built.name == "_site"


def test_broken_link_is_found(tmp_path):
    (tmp_path / "index.html").write_text('<a href="missing.html">x</a><a href="#top">y</a><a href="https://example.com">z</a>', encoding="utf-8")
    assert build_site.broken_links(tmp_path) == ["index.html: missing.html", "index.html: #top"]


@pytest.mark.parametrize("path", DOCS + PAGES + SOURCES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_forbidden_characters(path):
    text = path.read_text(encoding="utf-8")
    found = sorted({ch for ch in text if ch in FORBIDDEN})
    assert not found, f"{path.name}: {''.join(found)}"


@pytest.mark.parametrize("path", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_markdown_has_no_angle_bracket_paths(path):
    """메뉴 경로를 꺽쇠로 쓰지 않는다(예: 도구 > 설정). 인용문 표시(줄 맨 앞 >)는 제외."""
    lines = [line for line in _prose_markdown(path.read_text(encoding="utf-8")).splitlines() if not line.lstrip().startswith(">")]
    bad = [line for line in lines if re.search(r"\S\s*>\s*\S", line) or re.search(r"\S\s*<\s*\S", line)]
    assert not bad, "\n".join(bad)


@pytest.mark.parametrize("path", PAGES, ids=lambda p: str(p.relative_to(ROOT)))
def test_pages_have_no_angle_bracket_text(path):
    prose = _prose_html(path.read_text(encoding="utf-8"))
    assert "&gt;" not in prose and "&lt;" not in prose


#: 표기 원칙(CONTRIBUTING.md)에서 쓰지 않는 표현: 홍보성 수식어, 번역체, 구어체, 통일한 용어의 다른 표기
BANNED = {
    "홍보성 수식어": r"한 번에|손쉽|강력한|완벽|한눈에|핵심",
    "번역체": r"[을를] 통해|에 대해|에 대한|에 있어|로부터|되어지|[을를] 가지[고는다]|하는 것이 가능",
    "구어체": r"껐다 켜|쓰려면|모양 맞추|[가-힣](?:어|아|해|여|워|게|세|래|죠)요(?=[\s.,)!?]|$)",
    "용어": r"내려받|방장|시청자 읽기|시청자로 읽기",
}
#: 시청자 채팅을 흉내 내는 데모 문구(구어체가 정상)가 있는 파일
CHAT_SAMPLES = {"events.py"}


def _prose(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".md":
        return _prose_markdown(text)
    if path.suffix == ".html":
        return _prose_html(text)
    return text


@pytest.mark.parametrize("path", DOCS + PAGES + SOURCES, ids=lambda p: str(p.relative_to(ROOT)))
def test_writing_style(path):
    prose = _prose(path)
    found = []
    for kind, pattern in BANNED.items():
        if kind == "구어체" and path.name in CHAT_SAMPLES:
            continue
        found += [f"{kind}: {line.strip()[:80]}" for line in prose.splitlines() if re.search(pattern, line)]
    assert not found, "\n".join(found)


@pytest.mark.parametrize("path", DOCS + PAGES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_exclamation_or_slogan_headings(path):
    prose = _prose(path)
    exclaimed = [line.strip()[:80] for line in prose.splitlines() if re.search(r"[가-힣A-Za-z0-9)\]]!(?!=)", line)]
    assert not exclaimed, "\n".join(exclaimed)
    headings = re.findall(r"^#{1,4} (.+)$", prose, flags=re.M) if path.suffix == ".md" else re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", path.read_text(encoding="utf-8"))
    colon_titles = [title for title in headings if re.search(r"\S: \S", re.sub(r"<[^>]+>", "", title))]
    assert not colon_titles, "\n".join(colon_titles)


def test_pages_do_not_point_at_the_account_blog():
    for path in PAGES + SOURCES:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"budongjw\.github\.io/(?!debutkit/)", text), path.name
