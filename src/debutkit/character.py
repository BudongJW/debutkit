"""캐릭터 등록과 확인: PNGTuber 이미지, VRM(3D), Live2D, Inochi2D.

- 등록하면 파일을 이 PC의 캐릭터 보관함(저장 설정과 같은 폴더의 ``characters``)에 복사하고 ``character.json`` 에 정보를 적는다
- 확인은 공개 규격만으로 한다(독점 SDK 없음): VRM은 glTF 바이너리의 JSON, Live2D는 model3.json과 moc3 머리글,
  PNG는 IHDR 머리글, Inochi2D는 파일 머리글
- 방송: PNGTuber와 VRM은 debutkit 캐릭터 화면(오버레이 ``/character``)이 표시, Live2D는 VTube Studio로 전달(라이선스, docs/CHARACTER.md)
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

from . import settings

KINDS = {"png": "PNGTuber", "vrm": "3D(VRM)", "live2d": "Live2D", "inochi2d": "Inochi2D"}
#: PNGTuber 상태: 입 다묾, 입 벌림, 눈 감음, 입 벌리고 눈 감음
PNG_STATES = ("idle", "talk", "blink", "talk_blink")
STATE_NAMES = {"idle": "입 다묾", "talk": "입 벌림", "blink": "눈 감음", "talk_blink": "입 벌리고 눈 감음"}
SAMPLE_ID = "debutkit"
MAX_ZIP_BYTES = 1024 * 1024 * 1024  # 압축 해제 후 1 GB
BROADCAST = {"png": "debutkit 캐릭터 화면", "vrm": "debutkit 캐릭터 화면, Warudo, VMagicMirror, VSeeFace(VRM 0.x)",
             "live2d": "VTube Studio", "inochi2d": "Inochi Session"}


class CharacterError(ValueError):
    """등록할 수 없는 파일. 메시지는 한국어 안내."""


@dataclass
class Character:
    id: str
    name: str
    kind: str
    files: dict[str, str]  # 역할 -> 보관함 폴더 기준 상대 경로. png: 상태별 이미지, vrm: model, live2d: model(model3.json), inochi2d: model
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
        """debutkit 캐릭터 화면에 표시할 수 있는지(PNGTuber, VRM)."""
        return self.kind in ("png", "vrm")

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


_AVATAR_1 = {"onlyAuthor": "제작자 본인", "onlySeparatelyLicensedPerson": "별도 허락을 받은 사람", "everyone": "모든 사람"}
_COMMERCIAL_1 = {"personalNonProfit": "개인 비영리만", "personalProfit": "개인 영리 가능", "corporation": "법인 포함 가능"}
_AVATAR_0 = {"OnlyAuthor": "제작자 본인", "ExplicitlyLicensedPerson": "별도 허락을 받은 사람", "Everyone": "모든 사람"}


def live2d_details(model: Path) -> dict[str, Any]:
    """model3.json과 참조 파일 확인. 문제가 있으면 CharacterError."""
    try:
        data = json.loads(model.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise CharacterError(f"model3.json을 읽지 못함: {error}") from error
    refs = data.get("FileReferences") if isinstance(data, dict) else None
    if not isinstance(refs, dict) or not refs.get("Moc") or not refs.get("Textures"):
        raise CharacterError("model3.json에 Moc 또는 Textures 항목 없음(Live2D Cubism 3 이상 모델 필요)")
    base = model.parent
    missing = []
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
    for relative in paths:
        if not (base / str(relative)).is_file():
            missing.append(str(relative))
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


# --------------------------------------------------------------------------- 등록


def _slug(name: str, taken: set[str]) -> str:
    """보관함 폴더와 명령줄에 쓰는 이름. 한글 등 글자는 유지하고 공백, 기호는 하이픈으로."""
    base = re.sub(r"[^\w]+|_+", "-", name.lower()).strip("-")[:40] or "character"
    candidate, number = base, 2
    while candidate in taken or candidate == SAMPLE_ID:
        candidate, number = f"{base}-{number}", number + 1
    return candidate


def _extract(archive: Path, target: Path) -> Path:
    """zip 압축을 안전하게 풀기(상위 폴더 경로, 지나치게 큰 압축 거부)."""
    with zipfile.ZipFile(archive) as bundle:
        total = sum(info.file_size for info in bundle.infolist())
        if total > MAX_ZIP_BYTES:
            raise CharacterError("압축 해제 크기가 1 GB를 넘음")
        for info in bundle.infolist():
            destination = (target / info.filename).resolve()
            if not str(destination).startswith(str(target.resolve())):
                raise CharacterError(f"압축 파일에 허용하지 않는 경로: {info.filename}")
        bundle.extractall(target)
    return target


def detect(path: Path) -> tuple[str, Path]:
    """(종류, 모델 파일 또는 폴더)."""
    if path.is_file():
        suffix = path.suffix.lower()
        if suffix == ".vrm":
            return "vrm", path
        if path.name.lower().endswith(".model3.json"):
            return "live2d", path
        if suffix in (".inp", ".inx"):
            return "inochi2d", path
        if suffix == ".png":
            raise CharacterError("PNG 이미지는 상태별로 지정해야 함: debutkit character png --idle 입다문.png --talk 입벌린.png")
        raise CharacterError(f"지원하지 않는 파일: {path.name}(VRM, Live2D model3.json 또는 zip, 이미지 폴더, Inochi2D)")
    if path.is_dir():
        models = sorted(path.rglob("*.model3.json"))
        if models:
            return "live2d", models[0]
        vrms = sorted(path.rglob("*.vrm"))
        if vrms:
            return "vrm", vrms[0]
        if any((path / f"{state}.png").is_file() for state in ("idle", "talk")):
            return "png", path
        raise CharacterError("폴더에서 캐릭터 파일을 찾지 못함(model3.json, .vrm, idle.png와 talk.png)")
    raise CharacterError(f"파일 또는 폴더 없음: {path}")


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
        gltf, binary = read_glb(model)
        details = vrm_details(gltf, binary)
        return Character("", details["name"] or model.stem, "vrm", {"model": model.name}, author=details["author"], version=details["version"],
                         license=details["license"], warnings=details["warnings"])
    if kind == "live2d":
        details = live2d_details(model)
        return Character("", details["name"], "live2d", {"model": model.name}, version=details["version"], license=details["license"],
                         warnings=details["warnings"])
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
        if kind == "live2d":  # 모델 폴더 전체(참조 파일이 하위 폴더에 있음)
            def copy_live2d(folder: Path) -> None:
                shutil.copytree(model.parent, folder, dirs_exist_ok=True)
            return _store(character, name, copy_live2d, model=model.name)
        if kind == "vrm":
            gltf, binary = read_glb(model)
            thumb = vrm_details(gltf, binary)["thumbnail"]

            def copy_vrm(folder: Path) -> None:
                shutil.copy2(model, folder / model.name)
                if thumb:
                    (folder / f"thumbnail{thumb[1]}").write_bytes(thumb[0])
                    character.thumbnail = f"thumbnail{thumb[1]}"
            return _store(character, name, copy_vrm)
        return _store(character, name, lambda folder: shutil.copy2(model, folder / model.name))


def add_png(idle: Path, talk: Path, blink: Path | None = None, talk_blink: Path | None = None, *, name: str) -> Character:
    """상태별 PNG로 PNGTuber 캐릭터를 만들어 등록."""
    character = png_character(idle, talk, blink, talk_blink, name=name)
    sources = {"idle": idle, "talk": talk, "blink": blink, "talk_blink": talk_blink}
    return _store(character, name, lambda folder: [shutil.copy2(Path(sources[state]), folder / f"{state}.png") for state in character.files])


def _store(character: Character, name: str, copy: Any, *, model: str = "") -> Character:
    library = library_dir()
    library.mkdir(parents=True, exist_ok=True)
    taken = {item.name for item in library.iterdir() if item.is_dir()}
    character.name = name or character.name
    character.id = _slug(character.name, taken)
    folder = library / character.id
    folder.mkdir()
    try:
        copy(folder)
        if model:
            character.files = {"model": str(next(folder.rglob(model)).relative_to(folder).as_posix())}
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
    return target if target.is_file() and str(target).startswith(str(folder)) else None


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
    target = target_root / model.name
    shutil.copy2(model, target)
    return target
