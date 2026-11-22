"""캐릭터 등록과 확인: PNGTuber 이미지, VRM(3D), 일반 3D 모델(GLB, FBX), Live2D, Inochi2D.

- 등록하면 파일을 이 PC의 캐릭터 보관함(저장 설정과 같은 폴더의 ``characters``)에 복사하고 ``character.json`` 에 정보를 적는다
- 확인은 공개 규격만으로 한다(독점 SDK 없음): VRM, GLB는 glTF 바이너리의 JSON, FBX는 파일 구조(노드 이름),
  Live2D는 model3.json과 moc3 머리글, PNG는 IHDR 머리글, Inochi2D는 파일 머리글
- GLB, FBX는 뼈 이름으로 VRM 사람 모양 뼈를 찾는다(humanoid.py). 캐릭터 화면이 같은 표로 VRM처럼 움직인다
- 방송: PNGTuber, VRM, GLB, FBX는 debutkit 캐릭터 화면(오버레이 ``/character``)이 표시, Live2D는 VTube Studio로 전달(라이선스, docs/CHARACTER.md)
"""

from __future__ import annotations

import json
import re
import shutil
import struct
import tempfile
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import humanoid, settings

KINDS = {"png": "PNGTuber", "vrm": "3D(VRM)", "model": "3D(GLB, FBX)", "live2d": "Live2D", "inochi2d": "Inochi2D"}
#: PNGTuber 상태: 입 다묾, 입 벌림, 눈 감음, 입 벌리고 눈 감음
PNG_STATES = ("idle", "talk", "blink", "talk_blink")
STATE_NAMES = {"idle": "입 다묾", "talk": "입 벌림", "blink": "눈 감음", "talk_blink": "입 벌리고 눈 감음"}
SAMPLE_ID = "debutkit"
MAX_ZIP_BYTES = 1024 * 1024 * 1024  # 압축 해제 후 1 GB
BROADCAST = {"png": "debutkit 캐릭터 화면", "vrm": "debutkit 캐릭터 화면, Warudo, VMagicMirror, VSeeFace(VRM 0.x)",
             "model": "debutkit 캐릭터 화면", "live2d": "VTube Studio", "inochi2d": "Inochi Session"}
#: 캐릭터 화면이 불러오는 텍스처 이미지(FBX 외부 텍스처). TGA는 표시하지 않음
TEXTURE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


class CharacterError(ValueError):
    """등록할 수 없는 파일. 메시지는 한국어 안내."""


@dataclass
class Character:
    id: str
    name: str
    kind: str
    files: dict[str, str]  # 역할 -> 보관함 폴더 기준 상대 경로. png: 상태별 이미지, vrm: model, model: model과 texture1.., live2d: model(model3.json), inochi2d: model
    author: str = ""
    version: str = ""  # VRM 0.x, 1.0 / Live2D model3 버전
    thumbnail: str = ""
    license: list[str] = field(default_factory=list)  # 사용 조건 요약
    warnings: list[str] = field(default_factory=list)  # 방송 전에 확인할 점
    builtin: bool = False

    @property
    def kind_name(self) -> str:
        return KINDS.get(self.kind, self.kind)

    @property
    def broadcast(self) -> str:
        return BROADCAST.get(self.kind, "")

    @property
    def renders_in_overlay(self) -> bool:
        """debutkit 캐릭터 화면에 표시할 수 있는지(PNGTuber, VRM, GLB, FBX)."""
        return self.kind in ("png", "vrm", "model")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- 위치


def library_dir() -> Path:
    return settings.settings_path().parent / "characters"


def sample_dir() -> Path:
    return Path(__file__).resolve().parent / "overlay" / "static" / "character" / "sample"


def sample() -> Character:
    """debutkit 기본 캐릭터(고양이 귀 마이크). 바로 시험할 수 있도록 함께 배포. Apache-2.0."""
    return Character(SAMPLE_ID, "debutkit 기본 캐릭터", "png", {state: f"{state}.svg" for state in PNG_STATES}, author="debutkit",
                     thumbnail="idle.svg", license=["Apache-2.0(debutkit). 방송, 수익 방송, 소속사 사용 가능"], builtin=True)


def folder_of(character: Character) -> Path:
    return sample_dir() if character.builtin else library_dir() / character.id


# --------------------------------------------------------------------------- 형식 확인


def png_info(path: Path) -> tuple[int, int, bool]:
    """(너비, 높이, 투명 여부). PNG가 아니면 CharacterError."""
    with path.open("rb") as handle:
        head = handle.read(33)
        if len(head) < 33 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
            raise CharacterError(f"PNG 이미지가 아님: {path.name}")
        width, height, _, color = struct.unpack(">IIBB", head[16:26])
        if color in (4, 6):  # 회색조+알파, RGBA
            return width, height, True
        while True:  # 팔레트 투명도(tRNS) 확인
            chunk = handle.read(8)
            if len(chunk) < 8:
                return width, height, False
            length, kind = struct.unpack(">I4s", chunk)
            if kind == b"tRNS":
                return width, height, True
            if kind == b"IDAT":
                return width, height, False
            handle.seek(length + 4, 1)


def read_glb(path: Path) -> tuple[dict[str, Any], bytes]:
    """glTF 바이너리의 (JSON, BIN 청크)."""
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise CharacterError(f"VRM(glTF 바이너리) 파일이 아님: {path.name}")
    version, total = struct.unpack("<II", data[4:12])
    if version != 2:
        raise CharacterError(f"지원하지 않는 glTF 버전 {version}: {path.name}")
    offset, gltf, binary = 12, None, b""
    while offset + 8 <= min(total, len(data)):
        length, kind = struct.unpack("<I4s", data[offset:offset + 8])
        body = data[offset + 8:offset + 8 + length]
        if kind == b"JSON":
            gltf = json.loads(body.decode("utf-8"))
        elif kind == b"BIN\x00":
            binary = body
        offset += 8 + length
    if not isinstance(gltf, dict):
        raise CharacterError(f"glTF JSON 청크 없음: {path.name}")
    return gltf, binary


def _image_bytes(gltf: dict[str, Any], binary: bytes, index: Any) -> tuple[bytes, str] | None:
    images = gltf.get("images") or []
    if not isinstance(index, int) or not 0 <= index < len(images):
        return None
    image = images[index]
    views = gltf.get("bufferViews") or []
    view_index = image.get("bufferView")
    if not isinstance(view_index, int) or not 0 <= view_index < len(views):
        return None
    view = views[view_index]
    start = int(view.get("byteOffset") or 0)
    blob = binary[start:start + int(view.get("byteLength") or 0)]
    suffix = ".jpg" if image.get("mimeType") == "image/jpeg" else ".png"
    return (blob, suffix) if blob else None


def vrm_details(gltf: dict[str, Any], binary: bytes = b"") -> dict[str, Any]:
    """VRM 0.x, 1.0의 이름, 제작자, 버전, 사용 조건 요약과 경고, 미리보기 이미지."""
    extensions = gltf.get("extensions") or {}
    license_: list[str] = []
    warnings: list[str] = []
    if isinstance((extensions.get("VRMC_vrm") or {}).get("meta"), dict):
        vrm = extensions["VRMC_vrm"]
        meta = vrm["meta"]
        permission = meta.get("avatarPermission") or "onlyAuthor"
        commercial = meta.get("commercialUsage") or "personalNonProfit"
        license_ += [f"아바타 사용 허용 대상: {_AVATAR_1.get(permission, permission)}", f"상업적 이용: {_COMMERCIAL_1.get(commercial, commercial)}"]
        if permission != "everyone":
            warnings.append("모델 제작자가 정한 사람만 사용 가능. 본인이 제작자이거나 별도 허락을 받았는지 확인")
        if commercial == "personalNonProfit":
            warnings.append("수익 방송(후원, 광고) 불가")
        elif commercial == "personalProfit":
            warnings.append("법인(소속사) 사용 불가. 개인 수익 방송은 가능")
        if (meta.get("creditNotation") or "required") == "required":
            license_.append("크레딧 표기 필요")
        warnings += _maker_warnings(meta)
        details = {"version": f"VRM {vrm.get('specVersion') or '1.0'}", "name": meta.get("name") or "", "author": ", ".join(meta.get("authors") or []),
                   "thumbnail": _image_bytes(gltf, binary, meta.get("thumbnailImage"))}
    elif isinstance((extensions.get("VRM") or {}).get("meta"), dict):
        meta = extensions["VRM"]["meta"]
        allowed = meta.get("allowedUserName") or "OnlyAuthor"
        commercial = meta.get("commercialUssageName") or "Disallow"
        license_ += [f"아바타 사용 허용 대상: {_AVATAR_0.get(allowed, allowed)}", f"상업적 이용: {'허용' if commercial == 'Allow' else '불가'}",
                     f"라이선스: {meta.get('licenseName') or '지정 안 됨'}"]
        if allowed != "Everyone":
            warnings.append("모델 제작자가 정한 사람만 사용 가능. 본인이 제작자이거나 별도 허락을 받았는지 확인")
        if commercial != "Allow":
            warnings.append("수익 방송(후원, 광고) 불가")
        else:
            warnings.append("VRM 0.x는 법인(소속사) 사용 여부를 따로 표시하지 않음. 소속사 활동은 제작자에게 확인")
        warnings += _maker_warnings(meta)
        texture = meta.get("texture")
        source = None
        textures = gltf.get("textures") or []
        if isinstance(texture, int) and 0 <= texture < len(textures):
            source = textures[texture].get("source")
        details = {"version": "VRM 0.x", "name": meta.get("title") or "", "author": meta.get("author") or "", "thumbnail": _image_bytes(gltf, binary, source)}
    else:
        raise CharacterError("VRM 정보(VRM 또는 VRMC_vrm 확장) 없음: 일반 glTF 모델은 VRoid Studio, Blender VRM Add-on으로 VRM 변환 필요")
    details.update(license=license_, warnings=warnings)
    return details


def _maker_warnings(meta: dict[str, Any]) -> list[str]:
    """제작 도구별 약관 경고. Vket Avatar Maker 출력으로 보이면(meta의 문자열에 Vket, HIKKY) 저작권과 법인 사용 조건 안내."""
    text = " ".join(str(value) for value in meta.values() if isinstance(value, (str, list))).lower()
    if "vket" in text or "hikky" in text:
        return ["Vket Avatar Maker로 만든 모델로 보임: 저작권은 HIKKY, 법인(소속사) 사용은 HIKKY 사전 확인 필요, 모델 데이터 배포와 판매 금지"]
    return []


_AVATAR_1 = {"onlyAuthor": "제작자 본인", "onlySeparatelyLicensedPerson": "별도 허락을 받은 사람", "everyone": "모든 사람"}
_COMMERCIAL_1 = {"personalNonProfit": "개인 비영리만", "personalProfit": "개인 영리 가능", "corporation": "법인 포함 가능"}
_AVATAR_0 = {"OnlyAuthor": "제작자 본인", "ExplicitlyLicensedPerson": "별도 허락을 받은 사람", "Everyone": "모든 사람"}


def _live2d_refs(model: Path) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """(model3.json 내용, FileReferences, 참조 파일 상대 경로)."""
    try:
        data = json.loads(model.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise CharacterError(f"model3.json을 읽지 못함: {error}") from error
    refs = data.get("FileReferences") if isinstance(data, dict) else None
    if not isinstance(refs, dict) or not refs.get("Moc") or not isinstance(refs.get("Textures"), list) or not refs["Textures"]:
        raise CharacterError("model3.json에 Moc 또는 Textures 항목 없음(Live2D Cubism 3 이상 모델 필요)")
    paths = [refs["Moc"], *refs["Textures"]]
    for key in ("Physics", "Pose", "DisplayInfo", "UserData"):
        if refs.get(key):
            paths.append(refs[key])
    for item in refs.get("Expressions") or []:
        if isinstance(item, dict) and item.get("File"):
            paths.append(item["File"])
    for group in (refs.get("Motions") or {}).values():
        for item in group if isinstance(group, list) else []:
            if isinstance(item, dict) and item.get("File"):
                paths.append(item["File"])
            if isinstance(item, dict) and item.get("Sound"):
                paths.append(item["Sound"])
    return data, refs, list(dict.fromkeys(str(path) for path in paths))


def live2d_files(model: Path) -> list[str]:
    """등록, 보내기에 복사할 파일(모델 폴더 기준 상대 경로): model3.json, 참조 파일, VTube Studio 설정(.vtube.json)과 아이콘."""
    _, _, paths = _live2d_refs(model)
    base = model.parent
    extras = [item.name for item in sorted(base.iterdir()) if item.is_file() and
              (item.name.lower().endswith(".vtube.json") or (item.suffix.lower() == ".png" and item.name.lower().startswith("ico_")))]
    found = []
    for relative in [model.name, *paths, *extras]:
        target = (base / relative).resolve()
        if target.is_file() and target.is_relative_to(base.resolve()) and relative not in found:
            found.append(relative)
    return found


def live2d_details(model: Path) -> dict[str, Any]:
    """model3.json과 참조 파일 확인. 문제가 있으면 CharacterError."""
    data, refs, paths = _live2d_refs(model)
    base = model.parent
    missing = []
    for relative in paths:
        if not (base / relative).resolve().is_relative_to(base.resolve()):
            raise CharacterError(f"model3.json이 모델 폴더 밖 파일을 가리킴: {relative}")
        if not (base / relative).is_file():
            missing.append(relative)
    if missing:
        raise CharacterError("model3.json이 가리키는 파일 없음: " + ", ".join(missing[:5]) + (" 외" if len(missing) > 5 else ""))
    with (base / refs["Moc"]).open("rb") as handle:
        if handle.read(4) != b"MOC3":
            raise CharacterError(f"moc3 파일 형식이 아님: {refs['Moc']}")
    warnings = []
    if not refs.get("Physics"):
        warnings.append("물리 설정(physics3.json) 없음: VTube Studio에서 머리카락 등 흔들림이 동작하지 않음")
    return {"version": f"Live2D model3 v{data.get('Version', '?')}", "name": model.name.removesuffix(".model3.json"), "author": "",
            "license": ["Live2D 모델 사용 조건은 판매처, 제작자 약관 확인(영리, 법인 사용, 개변, 크레딧)"], "warnings": warnings}


# --------------------------------------------------------------------------- 일반 3D 모델(GLB, FBX)

FBX_MAGIC = b"Kaydara FBX Binary  \x00"


def _fbx_binary(data: bytes) -> list[tuple[str, list[Any], list[Any]]]:
    """FBX 바이너리의 노드 트리(이름, 속성, 자식). 숫자 배열은 건너뛰고 문자열, 숫자 하나(ID, 시간 등), 원시 자료 길이만 읽는다.

    형식: https://code.blender.org/2013/08/fbx-binary-file-format-specification/ (7.5부터 노드 머리글 64비트)
    """
    version = struct.unpack_from("<I", data, 23)[0]
    head = struct.Struct("<QQQB" if version >= 7500 else "<IIIB")
    scalars = {code: struct.Struct(fmt) for code, fmt in ((b"Y", "<h"), (b"C", "<?"), (b"I", "<i"), (b"F", "<f"), (b"D", "<d"), (b"L", "<q"))}

    def node(offset: int, depth: int) -> tuple[Any, int]:
        end, count, _, name_length = head.unpack_from(data, offset)
        if end == 0:
            return None, offset + head.size
        if end > len(data) or depth > 32:
            raise CharacterError("FBX 파일 구조가 올바르지 않음(손상 또는 다른 형식)")
        position = offset + head.size
        name = data[position:position + name_length].decode("utf-8", "replace")
        position += name_length
        properties: list[Any] = []
        for _ in range(count):
            code = data[position:position + 1]
            position += 1
            if code in (b"S", b"R"):
                size = struct.unpack_from("<I", data, position)[0]
                raw = data[position + 4:position + 4 + size]
                properties.append(raw.decode("utf-8", "replace") if code == b"S" else len(raw))
                position += 4 + size
            elif code in scalars:
                properties.append(scalars[code].unpack_from(data, position)[0])
                position += scalars[code].size
            elif code in (b"f", b"d", b"l", b"i", b"b"):
                properties.append(None)
                position += 12 + struct.unpack_from("<I", data, position + 8)[0]
            else:
                raise CharacterError("FBX 파일 구조가 올바르지 않음(손상 또는 다른 형식)")
        children = []
        while position < end:
            child, position = node(position, depth + 1)
            if child is None:
                break
            children.append(child)
        return (name, properties, children), end

    nodes, position = [], 27
    while position + head.size <= len(data):
        found, position = node(position, 0)
        if found is None:
            break
        nodes.append(found)
    return nodes


def fbx_details(path: Path) -> dict[str, Any]:
    """FBX의 버전, 뼈 이름(LimbNode), 형태 변형 이름(BlendShapeChannel), 텍스처 파일(Video)."""
    data = path.read_bytes()
    bones: list[str] = []
    morphs: list[str] = []
    textures: list[tuple[str, bool]] = []  # (상대 경로, 파일 안에 포함)
    if data.startswith(FBX_MAGIC):
        version = struct.unpack_from("<I", data, 23)[0]
        try:
            tree = _fbx_binary(data)
        except struct.error as error:
            raise CharacterError(f"FBX 파일을 끝까지 읽지 못함(손상): {path.name}") from error
        objects = next((children for name, _, children in tree if name == "Objects"), [])
        for name, properties, children in objects:
            label = properties[1] if len(properties) > 2 and isinstance(properties[1], str) else ""
            kind = properties[2] if len(properties) > 2 and isinstance(properties[2], str) else ""
            if name == "Model" and kind in ("LimbNode", "Root"):
                bones.append(label.split("\x00\x01")[0])
            elif name == "Deformer" and kind == "BlendShapeChannel":
                morphs.append(label.split("\x00\x01")[0])
            elif name == "Video":
                fields = {child[0]: child[1][0] for child in children if child[1]}
                relative = fields.get("RelativeFilename") or fields.get("Filename") or ""
                if isinstance(relative, str) and relative:
                    textures.append((relative, bool(fields.get("Content"))))
    else:
        text = data.decode("utf-8", "replace")
        match = re.search(r"FBXVersion:\s*(\d+)", text)
        if not text.lstrip().startswith(";") or not match:
            raise CharacterError(f"FBX 파일이 아님: {path.name}")
        version = int(match.group(1))
        bones = re.findall(r'Model:\s*-?\d+,\s*"Model::([^"]*)",\s*"(?:LimbNode|Root)"', text)
        morphs = re.findall(r'Deformer:\s*-?\d+,\s*"SubDeformer::([^"]*)",\s*"BlendShapeChannel"', text)
        textures = [(name, False) for name in dict.fromkeys(re.findall(r'RelativeFilename:\s*"([^"]+)"', text))]
    if version < 7000:
        raise CharacterError(f"FBX {version / 1000:.1f} 형식은 지원하지 않음: FBX 2011(7.0) 이후 형식으로 다시 내보내기")
    return {"version": f"FBX {version // 1000}.{version % 1000 // 100}", "bones": bones, "morphs": morphs,
            "textures": list(dict.fromkeys(textures))}


def glb_details(gltf: dict[str, Any]) -> dict[str, Any]:
    """VRM 정보가 없는 GLB의 뼈 이름(스킨 관절), 형태 변형 이름(mesh.extras.targetNames), 외부 이미지."""
    nodes = gltf.get("nodes") or []
    joints = [index for skin in gltf.get("skins") or [] if isinstance(skin, dict) for index in skin.get("joints") or []]
    bones = [str(nodes[index].get("name") or "") for index in dict.fromkeys(joints)
             if isinstance(index, int) and 0 <= index < len(nodes) and isinstance(nodes[index], dict)]
    morphs = [str(name) for mesh in gltf.get("meshes") or [] if isinstance(mesh, dict)
              for name in ((mesh.get("extras") or {}).get("targetNames") or []) if isinstance(mesh.get("extras"), dict)]
    external = [str(image["uri"]) for image in gltf.get("images") or [] if isinstance(image, dict) and image.get("uri")
                and not str(image["uri"]).startswith("data:")]
    return {"version": "GLB(glTF 2.0)", "bones": bones, "morphs": list(dict.fromkeys(morphs)), "external": external}


def model_details(model: Path) -> dict[str, Any]:
    """GLB, FBX를 캐릭터로 쓸 수 있는지 확인. 사람 모양 뼈(VRM 필수 15개)가 없으면 CharacterError."""
    if model.suffix.lower() == ".fbx":
        details = fbx_details(model)
    else:
        try:
            details = glb_details(read_glb(model)[0])
        except CharacterError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError, IndexError, struct.error) as error:
            raise CharacterError(f"GLB 파일 정보를 읽지 못함(손상 또는 다른 형식): {model.name}") from error
    if not details["bones"]:
        raise CharacterError("뼈대(스킨)가 없는 3D 모델: 캐릭터로 사용하려면 Mixamo 자동 리깅(무료)이나 VRoid Studio로 뼈를 넣은 파일 필요")
    bones = humanoid.match_bones(details["bones"])
    missing = humanoid.missing_bones(bones)
    if missing:
        labels = ", ".join(humanoid.bone_label(bone) for bone in missing[:6]) + (f" 외 {len(missing) - 6}개" if len(missing) > 6 else "")
        raise CharacterError(f"사람 모양 뼈를 찾지 못함({labels}). 지원하는 뼈 이름: Mixamo, VRoid, Unreal, Blender(Rigify), MMD, "
                             "Character Creator, 3ds Max Biped 방식. 다른 방식은 Mixamo 자동 리깅 후 FBX로 받아 등록")
    expressions = humanoid.match_expressions(details["morphs"])
    warnings = []
    if "aa" not in expressions:
        warnings.append("입 모양 표정 없음: 턱 뼈로 입 움직임 표현" if "jaw" in bones else "입 모양 표정과 턱 뼈 없음: 말할 때 입이 움직이지 않음")
    if "blink" not in expressions and "blinkLeft" not in expressions:
        warnings.append("눈 감기 표정 없음: 눈 깜빡임 미표시")
    license_ = ["GLB, FBX에는 사용 조건 정보가 없음: 수익 방송, 소속사 사용, 수정 허용 여부를 제작자, 판매처 조건으로 확인"]
    if any(humanoid.normalize(name).startswith("mixamorig") for name in details["bones"]):
        license_.append("Mixamo 뼈 이름: Mixamo에서 받은 캐릭터는 방송 사용 가능, 원본 파일 재배포 불가(Adobe Mixamo 약관)")
    return {"version": details["version"], "name": model.stem, "bones": bones, "expressions": expressions, "license": license_,
            "warnings": warnings, "textures": details.get("textures", []), "external": details.get("external", [])}


def model_textures(model: Path, textures: list[tuple[str, bool]]) -> tuple[list[str], list[str]]:
    """FBX 외부 텍스처: (모델 폴더 안에서 찾은 상대 경로, 찾지 못한 이름). 파일 안에 포함된 텍스처는 제외."""
    base = model.parent.resolve()
    found, missing = [], []
    for relative, embedded in textures:
        if embedded:
            continue
        cleaned = relative.replace("\\", "/")
        target = (base / cleaned).resolve()
        if target.is_file() and target.is_relative_to(base) and target.suffix.lower() in TEXTURE_SUFFIXES:
            found.append(target.relative_to(base).as_posix())
        else:
            missing.append(Path(cleaned).name)
    return list(dict.fromkeys(found)), list(dict.fromkeys(missing))


def _model_character(model: Path) -> Character:
    details = model_details(model)
    warnings = list(details["warnings"])
    if model.suffix.lower() == ".fbx":
        found, missing = model_textures(model, details["textures"])
        tga = [name for name in missing if name.lower().endswith(".tga")]
        others = [name for name in missing if name not in tga]
        if others:
            warnings.append(f"텍스처 파일 {len(others)}개를 찾지 못함({', '.join(others[:3])}): 색이 빠질 수 있음. "
                            "FBX를 텍스처 포함(Embed Media)으로 다시 내보내거나 텍스처를 FBX와 같은 폴더에 두기")
        if tga:
            warnings.append("TGA 텍스처는 표시하지 않음: PNG로 바꿔 다시 내보내기")
        files = {"model": model.name, **{f"texture{number}": path for number, path in enumerate(found, 1)}}
    else:
        if details["external"]:
            warnings.append("GLB 밖의 이미지 파일을 쓰는 모델: 색이 빠질 수 있음. 이미지를 포함한 GLB로 다시 내보내기")
        files = {"model": model.name}
    warnings.append("debutkit 캐릭터 화면 전용: Warudo, VSeeFace 등 다른 프로그램에는 VRM 변환 필요")
    return Character("", details["name"], "model", files, version=details["version"], license=details["license"], warnings=warnings)


# --------------------------------------------------------------------------- 등록


def _slug(name: str, taken: set[str]) -> str:
    """보관함 폴더와 명령줄에 쓰는 이름. 한글 등 글자는 유지하고 공백, 기호는 하이픈으로."""
    base = re.sub(r"[^\w]+|_+", "-", name.lower()).strip("-")[:40] or "character"
    candidate, number = base, 2
    while candidate in taken or candidate == SAMPLE_ID:
        candidate, number = f"{base}-{number}", number + 1
    return candidate


def _extract(archive: Path, target: Path) -> Path:
    """zip 압축을 안전하게 풀기(상위 폴더 경로, 지나치게 큰 압축 거부). Mac에서 만든 압축의 __MACOSX 폴더는 풀지 않는다."""
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = [info for info in bundle.infolist() if not _mac_junk(Path(info.filename))]
            if sum(info.file_size for info in members) > MAX_ZIP_BYTES:
                raise CharacterError("압축 해제 크기가 1 GB를 넘음")
            for info in members:
                destination = (target / info.filename).resolve()
                if not destination.is_relative_to(target.resolve()):
                    raise CharacterError(f"압축 파일에 허용하지 않는 경로: {info.filename}")
            bundle.extractall(target, members)
    except CharacterError:
        raise
    except zipfile.BadZipFile as error:
        raise CharacterError(f"zip 압축 파일이 아니거나 손상됨: {archive.name}") from error
    except (RuntimeError, NotImplementedError) as error:  # 암호, 지원하지 않는 압축 방식
        raise CharacterError(f"풀 수 없는 압축(암호 또는 지원하지 않는 방식, 일반 zip으로 다시 압축 필요): {error}") from error
    return target


def _mac_junk(path: Path) -> bool:
    """Mac이 압축에 함께 넣는 부가 파일(__MACOSX 폴더, ._ 로 시작하는 파일)."""
    return "__MACOSX" in path.parts or path.name.startswith("._") or path.name == ".DS_Store"


def _find(folder: Path, pattern: str) -> list[Path]:
    return sorted(path for path in folder.rglob(pattern) if not _mac_junk(path.relative_to(folder)))


def detect(path: Path) -> tuple[str, Path]:
    """(종류, 모델 파일 또는 폴더)."""
    if path.is_file():
        suffix = path.suffix.lower()
        if suffix == ".vrm":
            return "vrm", path
        if suffix == ".glb":
            return ("vrm" if _is_vrm(path) else "model"), path
        if suffix == ".fbx":
            return "model", path
        if suffix == ".gltf":
            raise CharacterError("glTF(.gltf) 파일은 지원하지 않음: Blender 등에서 GLB(.glb)로 내보낸 파일 등록")
        if suffix in (".pmx", ".pmd"):
            raise CharacterError("MMD 모델(PMX)은 지원하지 않음: Blender(MMD Tools)에서 FBX나 VRM으로 변환 후 등록")
        if path.name.lower().endswith(".model3.json"):
            return "live2d", path
        if suffix in (".inp", ".inx"):
            return "inochi2d", path
        if suffix == ".png":
            raise CharacterError("PNG 이미지는 상태별로 지정해야 함: debutkit character png --idle 입다문.png --talk 입벌린.png")
        raise CharacterError(f"지원하지 않는 파일: {path.name}(VRM, GLB, FBX, Live2D model3.json 또는 zip, 이미지 폴더, Inochi2D)")
    if path.is_dir():
        models = _find(path, "*.model3.json")
        if models:
            return "live2d", models[0]
        vrms = _find(path, "*.vrm")
        if vrms:
            return "vrm", vrms[0]
        models = _find(path, "*.glb") + _find(path, "*.fbx")
        if models:
            return detect(models[0])
        if any((path / f"{state}.png").is_file() for state in ("idle", "talk")):
            return "png", path
        raise CharacterError("폴더에서 캐릭터 파일을 찾지 못함(model3.json, .vrm, .glb, .fbx, idle.png와 talk.png)")
    raise CharacterError(f"파일 또는 폴더 없음: {path}")


def _is_vrm(path: Path) -> bool:
    """VRM 확장이 있는 GLB(확장자만 .glb인 VRM)."""
    try:
        extensions = read_glb(path)[0].get("extensions") or {}
    except CharacterError:
        return False
    return isinstance(extensions, dict) and ("VRM" in extensions or "VRMC_vrm" in extensions)


def inspect(path: str | Path) -> Character:
    """등록 전 확인(복사하지 않음). zip은 임시 폴더에 풀어서 확인."""
    path = Path(path)
    if path.is_file() and path.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory() as temporary:
            return inspect(_extract(path, Path(temporary)))
    kind, model = detect(path)
    if kind == "png":
        return png_character(*(model / f"{state}.png" if (model / f"{state}.png").is_file() else None for state in PNG_STATES))
    if kind == "vrm":
        try:
            gltf, binary = read_glb(model)
            details = vrm_details(gltf, binary)
        except CharacterError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError, IndexError, struct.error) as error:  # 형식이 어긋난 glTF JSON
            raise CharacterError(f"VRM 파일 정보를 읽지 못함(손상 또는 다른 형식): {model.name}") from error
        return Character("", details["name"] or model.stem, "vrm", {"model": model.name}, author=details["author"], version=details["version"],
                         license=details["license"], warnings=details["warnings"])
    if kind == "live2d":
        details = live2d_details(model)
        return Character("", details["name"], "live2d", {"model": model.name}, version=details["version"], license=details["license"],
                         warnings=details["warnings"])
    if kind == "model":
        return _model_character(model)
    with model.open("rb") as handle:
        if model.suffix.lower() == ".inp" and handle.read(8) != b"TRNSRTS\x00":
            raise CharacterError(f"Inochi2D 파일 형식이 아님: {model.name}")
    return Character("", model.stem, "inochi2d", {"model": model.name}, license=["Inochi2D 모델 사용 조건은 제작자에게 확인"],
                     warnings=["debutkit 캐릭터 화면은 Inochi2D를 표시하지 않음: Inochi Session에서 불러와 방송"])


def png_character(idle: Path | None, talk: Path | None, blink: Path | None = None, talk_blink: Path | None = None, *, name: str = "") -> Character:
    """상태별 PNG로 PNGTuber 캐릭터 정보 만들기(입 다묾, 입 벌림 필수)."""
    given = {"idle": idle, "talk": talk, "blink": blink, "talk_blink": talk_blink}
    if not idle or not talk:
        raise CharacterError("PNGTuber에는 입 다문 이미지(idle)와 입 벌린 이미지(talk)가 필요")
    sizes, warnings, files = set(), [], {}
    for state, image in given.items():
        if image is None:
            continue
        image = Path(image)
        if not image.is_file():
            raise CharacterError(f"이미지 파일 없음: {image}")
        width, height, transparent = png_info(image)
        sizes.add((width, height))
        if not transparent:
            warnings.append(f"{STATE_NAMES[state]} 이미지에 투명 배경 없음: 방송 화면에 사각형 배경이 보임")
        if max(width, height) > 4096:
            warnings.append(f"{STATE_NAMES[state]} 이미지가 큼({width}x{height}): 2048px 이하 권장")
        files[state] = f"{state}.png"
    if len(sizes) > 1:
        warnings.append("상태별 이미지 크기가 다름: 같은 캔버스 크기 권장")
    return Character("", name or Path(idle).parent.name or "PNGTuber", "png", files, thumbnail="idle.png",
                     license=["직접 그렸거나 사용 허락을 받은 이미지인지 확인"], warnings=warnings)


def _save(character: Character, folder: Path) -> None:
    (folder / "character.json").write_text(json.dumps(character.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def add(path: str | Path, name: str = "") -> Character:
    """확인 후 보관함에 복사해 등록."""
    path = Path(path)
    with tempfile.TemporaryDirectory() as temporary:
        if path.is_file() and path.suffix.lower() == ".zip":
            path = _extract(path, Path(temporary))
        character = inspect(path)
        kind, model = detect(path)
        if kind == "png":
            sources = {state: model / f"{state}.png" for state in character.files}
            return _store(character, name, lambda folder: [shutil.copy2(src, folder / f"{state}.png") for state, src in sources.items()])
        if kind == "live2d":  # model3.json이 가리키는 파일만(하위 폴더 구조 유지). 같은 폴더의 다른 파일은 복사하지 않음
            def copy_live2d(folder: Path) -> None:
                for relative in live2d_files(model):
                    (folder / relative).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(model.parent / relative, folder / relative)
            return _store(character, name, copy_live2d)
        if kind == "vrm":
            gltf, binary = read_glb(model)
            thumb = vrm_details(gltf, binary)["thumbnail"]

            def copy_vrm(folder: Path) -> None:
                shutil.copy2(model, folder / model.name)
                if thumb:
                    (folder / f"thumbnail{thumb[1]}").write_bytes(thumb[0])
                    character.thumbnail = f"thumbnail{thumb[1]}"
            return _store(character, name, copy_vrm)
        if kind == "model":  # 모델 파일과 캐릭터 화면이 불러올 텍스처(하위 폴더 구조 유지)
            def copy_model(folder: Path) -> None:
                for relative in character.files.values():
                    (folder / relative).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(model.parent / relative, folder / relative)
            return _store(character, name, copy_model)
        return _store(character, name, lambda folder: shutil.copy2(model, folder / model.name))


def add_png(idle: Path, talk: Path, blink: Path | None = None, talk_blink: Path | None = None, *, name: str) -> Character:
    """상태별 PNG로 PNGTuber 캐릭터를 만들어 등록."""
    character = png_character(idle, talk, blink, talk_blink, name=name)
    sources = {"idle": idle, "talk": talk, "blink": blink, "talk_blink": talk_blink}
    return _store(character, name, lambda folder: [shutil.copy2(Path(sources[state]), folder / f"{state}.png") for state in character.files])


def _store(character: Character, name: str, copy: Any) -> Character:
    library = library_dir()
    library.mkdir(parents=True, exist_ok=True)
    taken = {item.name for item in library.iterdir() if item.is_dir()}
    character.name = name or character.name
    character.id = _slug(character.name, taken)
    folder = library / character.id
    folder.mkdir()
    try:
        copy(folder)
        _save(character, folder)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return character


def load(folder: Path) -> Character | None:
    try:
        data = json.loads((folder / "character.json").read_text(encoding="utf-8"))
        return Character(**{key: data[key] for key in Character.__dataclass_fields__ if key in data})
    except (OSError, ValueError, TypeError, KeyError):
        return None


def all_characters() -> list[Character]:
    """기본 캐릭터와 등록한 캐릭터."""
    found = [sample()]
    library = library_dir()
    if library.is_dir():
        for folder in sorted(library.iterdir()):
            character = load(folder) if folder.is_dir() else None
            if character is not None:
                found.append(character)
    return found


def get(character_id: str | None) -> Character | None:
    for character in all_characters():
        if character.id == character_id:
            return character
    return None


def remove(character_id: str) -> Path | None:
    if character_id == SAMPLE_ID:
        raise CharacterError("기본 캐릭터는 삭제할 수 없음")
    folder = library_dir() / character_id
    if not (folder / "character.json").is_file():
        return None
    shutil.rmtree(folder)
    return folder


def active() -> Character:
    """방송에 사용할 캐릭터(저장 설정의 character). 없으면 기본 캐릭터."""
    return get(settings.load().get("character")) or sample()


def use(character_id: str) -> Character:
    character = get(character_id)
    if character is None:
        raise CharacterError(f"등록한 캐릭터 없음: {character_id}")
    settings.save({**settings.load(), "character": character.id})
    return character


def file_path(character: Character, relative: str) -> Path | None:
    """캐릭터 화면이 요청한 파일. 캐릭터 폴더 밖이나 등록하지 않은 파일은 None."""
    folder = folder_of(character).resolve()
    allowed = set(character.files.values()) | ({character.thumbnail} if character.thumbnail else set())
    if relative not in allowed:
        return None
    target = (folder / relative).resolve()
    return target if target.is_file() and target.is_relative_to(folder) else None


# --------------------------------------------------------------------------- 방송 프로그램으로 보내기

#: Steam 라이브러리 기준 모델 폴더(공식 문서는 프로그램 안의 폴더 열기 버튼으로 안내. 찾지 못하면 --folder 로 지정)
APP_FOLDERS = {
    "vts": ("VTube Studio", "live2d", ["steamapps/common/VTube Studio/VTube Studio_Data/StreamingAssets/Live2DModels",
                                       "steamapps/common/VTube Studio/VTube Studio.app/Contents/Resources/Data/StreamingAssets/Live2DModels"]),
    "warudo": ("Warudo", "vrm", ["steamapps/common/Warudo/Warudo_Data/StreamingAssets/Characters"]),
}


def steam_libraries(steam_root: str | None = None) -> list[Path]:
    """Steam 설치 폴더와 추가 라이브러리 폴더(libraryfolders.vdf)."""
    if steam_root is None:
        from .doctor import _steam_root

        steam_root = _steam_root()
    if not steam_root:
        return []
    root = Path(steam_root)
    found = [root]
    try:
        text = (root / "steamapps" / "libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return found
    for raw in re.findall(r'"path"\s+"([^"]+)"', text):
        library = Path(raw.replace("\\\\", "\\"))
        if library not in found:
            found.append(library)
    return found


def app_folder(app: str, libraries: list[Path] | None = None) -> Path | None:
    _, _, candidates = APP_FOLDERS[app]
    for library in steam_libraries() if libraries is None else libraries:
        for relative in candidates:
            if (library / relative).is_dir():
                return library / relative
    return None


def send(character: Character, app: str, folder: str | Path | None = None, *, libraries: list[Path] | None = None) -> Path:
    """캐릭터를 방송 프로그램의 모델 폴더에 복사. 반환: 복사한 위치."""
    if app not in APP_FOLDERS:
        raise CharacterError(f"지원하지 않는 프로그램: {app}(vts, warudo)")
    title, kind, _ = APP_FOLDERS[app]
    if character.kind != kind:
        raise CharacterError(f"{title}에는 {KINDS[kind]} 캐릭터만 보낼 수 있음(이 캐릭터: {character.kind_name})")
    target_root = Path(folder) if folder else app_folder(app, libraries)
    if target_root is None or not target_root.is_dir():
        raise CharacterError(f"{title} 모델 폴더를 찾지 못함: {title}의 모델 폴더 열기 기능으로 위치를 확인한 뒤 --folder 로 지정")
    source = folder_of(character)
    if kind == "live2d":
        target = target_root / character.id
        shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("character.json"))
        return target
    model = source / character.files["model"]
    target = target_root / (model.stem + ".vrm")  # 확장자가 .glb인 VRM도 .vrm으로(Warudo는 .vrm만 인식)
    shutil.copy2(model, target)
    return target
