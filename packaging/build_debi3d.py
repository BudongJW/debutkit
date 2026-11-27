"""기본 3D 캐릭터 데비(VRM) 만들기: CC0 VRoid 샘플의 색을 데비 팔레트로 바꾸고 텍스처를 줄인다.

    python packaging/build_debi3d.py 베이스.vrm [썸네일.png]

- 베이스: pixiv VRoid β Ver 샘플 "Victoria Rubin"(파일 메타 licenseName CC0, 사용 허용 Everyone, 상업 이용 Allow).
  저장소에는 넣지 않고 SHA-256으로 같은 파일인지 확인. 사이드 포니테일과 리본이 데비(라벤더 사이드 포니테일, 별 머리핀)와 같은 실루엣
- 바꾸는 것(모양, 뼈, 표정, 흔들림 뼈는 그대로)
  - 머리: 재질 색 라벤더, 머리끝 분홍은 보라로. 눈썹 라벤더. 눈동자 민트. 옷과 신발의 분홍은 라벤더(금색 단추는 그대로)
  - 리본: 노랑(데비 별 머리핀 색). 이름, 작성자, 참고(베이스), 미리보기 그림(썸네일.png를 주면 그것으로)
  - 텍스처 한 변 1024px 이하(character.shrink_vrm)
- 결과: src/debutkit/overlay/static/character/debi3d/ 의 debi.vrm, thumbnail.png(썸네일을 줬을 때), manifest.json(베이스, 바꾼 것, 해시)
- 필요: Pillow, numpy
"""

from __future__ import annotations

import datetime
import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from debutkit import character  # noqa: E402

OUT = ROOT / "src" / "debutkit" / "overlay" / "static" / "character" / "debi3d"
BASE_SHA256 = "b1372131bdbf233f46320146d565f342a7e4f6f4b8f2aefb301f1a283ec07e1e"
BASE = {"name": "Victoria Rubin", "collection": "pixiv VRoid β Ver 샘플 모델(CC0)", "license": "CC0 1.0(파일 메타 licenseName CC0)",
        "file": "VRoid_Victoria_Rubin.vrm", "sha256": BASE_SHA256, "obtained": "github.com/madjin/vrm-samples(β 샘플 사본), 2019년 VRoid 내보내기"}

#: 데비 팔레트(sRGB 0~255): 머리 라벤더와 그늘, 눈썹, 리본 노랑, 머리 빛
HAIR, HAIR_SHADE, HAIR_GLOW = (198, 170, 244), (146, 112, 214), (232, 222, 255)
BROW, BROW_SHADE = (150, 118, 214), (112, 84, 176)
RIBBON, RIBBON_SHADE, RIBBON_GLOW = (255, 201, 60), (232, 158, 36), (90, 64, 10)
#: 재질 이름 -> 바꿀 색 {속성: 색}
MATERIALS = {
    "F00_000_HairBack_00_HAIR": {"_Color": HAIR, "_ShadeColor": HAIR_SHADE, "_EmissionColor": HAIR_GLOW},
    "F00_000_Hair_00_HAIR_01": {"_Color": HAIR, "_ShadeColor": HAIR_SHADE, "_EmissionColor": HAIR_GLOW},
    "F00_000_Hair_00_HAIR_02": {"_Color": HAIR, "_ShadeColor": HAIR_SHADE, "_EmissionColor": HAIR_GLOW},
    "F00_000_Hair_00_HAIR_03": {"_Color": RIBBON, "_ShadeColor": RIBBON_SHADE, "_EmissionColor": RIBBON_GLOW},
    "F00_000_00_FaceBrow_00_FACE": {"_Color": BROW, "_ShadeColor": BROW_SHADE},
}
#: 그림 이름 -> 색상 범위 바꾸기 [(시작 도, 끝 도, 옮길 도)]. 채도 낮은 흰색, 회색과 투명도는 그대로
HUES = {
    "F00_000_Hair_00_01": [(285, 350, -48)],  # 머리끝 분홍 -> 보라
    "F00_000_EyeIris_00": [(185, 255, -52)],  # 파랑 -> 민트
    "F00_002_Onepiece_01": [(285, 352, -52)],  # 옷 분홍 -> 라벤더(베이지, 금색은 범위 밖)
    "F00_002_Shoes_01": [(285, 352, -52)],
}


def linear(color: tuple[int, int, int]) -> list[float]:
    return [round((channel / 255) ** 2.2, 6) for channel in color] + [1.0]


def unit(color: tuple[int, int, int]) -> list[float]:
    return [round(channel / 255, 6) for channel in color] + [1.0]


def shift_hues(blob: bytes, ranges: list[tuple[int, int, int]], min_saturation: int = 24) -> bytes:
    with Image.open(io.BytesIO(blob)) as picture:
        rgba = picture.convert("RGBA")
    hue, saturation, value = (np.asarray(channel, dtype=np.int16) for channel in rgba.convert("RGB").convert("HSV").split())
    hue = hue.copy()
    for low, high, shift in ranges:
        mask = (hue >= round(low * 255 / 360)) & (hue <= round(high * 255 / 360)) & (saturation >= min_saturation)
        hue[mask] = (hue[mask] + round(shift * 255 / 360)) % 256
    merged = Image.merge("HSV", [Image.fromarray(channel.astype(np.uint8)) for channel in (hue, saturation, value)]).convert("RGB").convert("RGBA")
    merged.putalpha(rgba.getchannel("A"))
    out = io.BytesIO()
    merged.save(out, "PNG", optimize=True)
    return out.getvalue()


def build(base: Path, thumbnail: Path | None) -> dict:
    digest = hashlib.sha256(base.read_bytes()).hexdigest()
    if digest != BASE_SHA256:
        raise SystemExit(f"베이스 파일이 다름(SHA-256 {digest}): {BASE['file']}")
    gltf, binary = character.read_glb(base)
    vrm = gltf["extensions"]["VRM"]
    changed: list[str] = []
    materials = {material.get("name"): material for material in gltf["materials"]}  # VRM 0.x 재질 속성은 이름으로 짝지음
    for props in vrm["materialProperties"]:
        colors = MATERIALS.get(props["name"])
        if not colors:
            continue
        for key, color in colors.items():
            props["vectorProperties"][key] = unit(color)
        materials[props["name"]].setdefault("pbrMetallicRoughness", {})["baseColorFactor"] = linear(colors["_Color"])
        changed.append(f"재질 {props['name']}: " + ", ".join(f"{key} #{''.join(f'{c:02x}' for c in color)}" for key, color in colors.items()))
    replaced: dict[int, bytes] = {}
    for index, image in enumerate(gltf["images"]):
        name = image.get("name") or ""
        view = image["bufferView"]
        if name in HUES:
            replaced[view] = shift_hues(character._image_bytes(gltf, binary, index)[0], HUES[name])
            changed.append(f"그림 {name}: 색상 " + ", ".join(f"{low}~{high}도를 {shift:+d}도" for low, high, shift in HUES[name]))
        elif name == "Thumbnail" and thumbnail:
            with Image.open(thumbnail) as picture:
                small = picture.convert("RGBA")
            small.thumbnail((512, 512), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            small.save(out, "PNG", optimize=True)
            replaced[view] = out.getvalue()
            image["mimeType"] = "image/png"
            changed.append("미리보기 그림: debutkit 캐릭터 그림 만들기로 그린 데비 3D")
    vrm["meta"].update(title="데비", version="1.0", author="debutkit", contactInformation="https://github.com/BudongJW/debutkit",
                       reference=f"{BASE['collection']} {BASE['name']}의 색을 바꿈")
    with tempfile.TemporaryDirectory() as folder:
        recolored = Path(folder) / "debi.vrm"
        recolored.write_bytes(character.repack_glb(gltf, binary, replaced))
        light, shrunk = character.shrink_vrm(recolored, character.LIGHT_TEXTURE)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "debi.vrm").write_bytes(light)
    if thumbnail:
        with Image.open(thumbnail) as picture:
            picture.convert("RGBA").resize((512, 512), Image.Resampling.LANCZOS).save(OUT / "thumbnail.png", optimize=True)
    changed.append(f"텍스처 {len(shrunk)}장을 한 변 {character.LIGHT_TEXTURE}px로 줄임")
    manifest = {"name": "데비(3D)", "base": BASE, "license": "CC0 1.0(베이스와 같음). 누구나 방송, 수익 방송, 소속사, 수정, 재배포 가능",
                "changes": changed, "file": {"name": "debi.vrm", "bytes": len(light), "sha256": hashlib.sha256(light).hexdigest()},
                "tool": "packaging/build_debi3d.py", "date": datetime.date.today().isoformat()}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    print(json.dumps(build(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None), ensure_ascii=False, indent=2))
