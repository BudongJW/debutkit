"""함께 배포하는 한글 글꼴 만들기: google/fonts(SIL OFL 1.1, 예약 글꼴 이름 없는 것만)의 TTF를 자주 쓰는 한글 2,350자와 영문, 문장 부호만 남긴 WOFF2로.

    python packaging/build_fonts.py 받은_TTF_폴더

- 받은 폴더에는 TTF와 OFL-<폴더 이름>.txt, 받은 커밋을 적은 COMMIT 파일(build_fonts.py가 읽지 않는 파일은 무시)
- 결과: src/debutkit/overlay/static/vendor/fonts/<파일 이름>.subset.woff2 와 OFL-<글꼴>.txt. 출처, 커밋, SHA-256을 출력(vendor/README.txt에 옮김)
- 예약 글꼴 이름(Reserved Font Name)이 있는 글꼴은 줄이거나 바꾸면 이름을 바꿔야 해서 받지 않음(나눔손글씨 펜 등)
- 2,350자 밖의 글자(예: 똠, 햏)는 브라우저가 다음 글꼴(맑은 고딕 등)로 표시
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "debutkit" / "overlay" / "static" / "vendor" / "fonts"

#: (google/fonts 폴더, TTF 파일, 라이선스 파일 이름에 쓸 글꼴 이름)
SOURCES = (
    ("dohyeon", "DoHyeon-Regular.ttf", "DoHyeon"),
    ("jua", "Jua-Regular.ttf", "Jua"),
    ("bagelfatone", "BagelFatOne-Regular.ttf", "BagelFatOne"),
    ("gowundodum", "GowunDodum-Regular.ttf", "GowunDodum"),
    ("sunflower", "Sunflower-Bold.ttf", "Sunflower"),
    ("dongle", "Dongle-Bold.ttf", "Dongle"),
    ("cutefont", "CuteFont-Regular.ttf", "CuteFont"),
    ("gamjaflower", "GamjaFlower-Regular.ttf", "GamjaFlower"),
    ("eastseadokdo", "EastSeaDokdo-Regular.ttf", "EastSeaDokdo"),
    ("gowunbatang", "GowunBatang-Bold.ttf", "GowunBatang"),
    ("songmyung", "SongMyung-Regular.ttf", "SongMyung"),
    ("yeonsung", "YeonSung-Regular.ttf", "YeonSung"),
    ("kiranghaerang", "KirangHaerang-Regular.ttf", "KirangHaerang"),
    ("stylish", "Stylish-Regular.ttf", "Stylish"),
)
#: 남길 글자 범위(한글 음절은 KS X 1001 2,350자만 따로 더함)
RANGES = ((0x20, 0x7E), (0xA0, 0xFF), (0x2010, 0x206F), (0x2190, 0x21FF), (0x2460, 0x24FF), (0x25A0, 0x25FF), (0x2600, 0x26FF),
          (0x3000, 0x303F), (0x3131, 0x318E), (0x3200, 0x321E), (0x3260, 0x327E), (0xFF01, 0xFF5E))


def ksx1001_hangul() -> list[int]:
    """EUC-KR 두 바이트로 적히는 한글 음절(KS X 1001 완성형 2,350자). 나머지는 8바이트 조합 문자열이 되어 빠짐."""
    return [code for code in range(0xAC00, 0xD7A4) if len(chr(code).encode("euc_kr", errors="ignore")) == 2]


def unicodes() -> list[int]:
    found = set(ksx1001_hangul())
    for low, high in RANGES:
        found.update(range(low, high + 1))
    return sorted(found)


def reserved_name(license_text: str) -> bool:
    head = license_text.split("This Font Software is licensed", 1)[0]
    return "Reserved Font Name" in head


def subset(source: Path, target: Path) -> None:
    from fontTools import subset as fonttools_subset  # 개발 도구(fonttools, brotli)

    options = fonttools_subset.Options()
    options.flavor = "woff2"
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.name_languages = ["*"]
    options.hinting = False  # 화면 글꼴은 힌팅 없이도 깨끗하고 파일이 작아짐
    options.notdef_outline = True
    font = fonttools_subset.load_font(str(source), options)
    subsetter = fonttools_subset.Subsetter(options)
    subsetter.populate(unicodes=unicodes())
    subsetter.subset(font)
    fonttools_subset.save_font(font, str(target), options)


def main(folder: Path) -> int:
    commit = (folder / "COMMIT").read_text(encoding="utf-8").strip() if (folder / "COMMIT").exists() else "(기록 없음)"
    lines = []
    for directory, file, name in SOURCES:
        source = folder / file
        license_file = folder / f"OFL-{directory}.txt"
        text = license_file.read_text(encoding="utf-8")
        if reserved_name(text):
            raise SystemExit(f"{file}: 예약 글꼴 이름이 있어 줄일 수 없음")
        target = OUT / file.replace(".ttf", ".subset.woff2")
        subset(source, target)
        shutil.copyfile(license_file, OUT / f"OFL-{name}.txt")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        lines.append(f"{target.stat().st_size:>8}  {target.name}  <- ofl/{directory}/{file} sha256 {digest}")
    print(f"google/fonts 커밋 {commit}")
    print("\n".join(lines))
    print("\nSHA-256")
    for _, file, name in SOURCES:
        for path in (OUT / file.replace(".ttf", ".subset.woff2"), OUT / f"OFL-{name}.txt"):
            print(f"  {hashlib.sha256(path.read_bytes()).hexdigest()}  fonts/{path.name}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    sys.exit(main(Path(sys.argv[1])))
