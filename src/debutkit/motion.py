"""3D 캐릭터 동작: VRMA(VRM Animation), 사람 모양 뼈가 있는 FBX, GLB 동작 파일의 등록, 확인, 실행 요청.

- 등록하면 파일을 이 PC의 동작 보관함(저장 설정과 같은 폴더의 ``motions``)에 복사하고 ``motion.json`` 에 정보를 적는다
- 확인은 공개 규격만으로 한다: VRMA는 glTF 바이너리의 ``VRMC_vrm_animation`` 확장, GLB는 ``animations``, FBX는 파일 구조
  (AnimationStack, AnimationCurveNode, 뼈 이름). FBX, GLB의 뼈는 캐릭터와 같은 표(humanoid.py)로 VRM 사람 모양 뼈에 대응
- 캐릭터 화면(character.js)이 3D 캐릭터(VRM, GLB, FBX)에 맞춰 재생: VRMA는 three-vrm-animation, FBX와 GLB는 뼈 이름 대응 후 변환
- 기본 동작(대기 중 반복)은 저장 설정 ``idle_motion``, 후원 반응은 ``motion_reactions`` (``"최소 금액:동작"``)
- 동작 파일은 함께 배포하지 않는다(Mixamo 원본 재배포 금지, VRoid 공식 동작 추출 가능 형태 재배포 금지). 사용자가 받은 파일만 이 PC에서 사용
"""

from __future__ import annotations

import json
import re
import shutil
import struct
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import character, humanoid, settings

KINDS = {"vrma": "VRMA", "fbx": "FBX", "glb": "GLB"}
SUFFIXES = (".vrma", ".fbx", ".glb")
#: FBX 시간 단위(KTime): 1초
KTIME = 46_186_158_000
#: 캐릭터 화면이 동작에서 쓰지 않는 표정(입 모양, 눈 감기, 웃음은 목소리, 눈 깜빡임, 얼굴 추적이 정함)
DRIVEN_EXPRESSIONS = ("aa", "ih", "ou", "ee", "oh", "blink", "blinkLeft", "blinkRight", "happy")


class MotionError(ValueError):
    """등록할 수 없는 동작 파일. 메시지는 한국어 안내."""


@dataclass
class Motion:
    id: str
    name: str
    kind: str  # vrma, fbx, glb
    file: str  # 보관함 폴더 기준 파일 이름
    clip: str = ""  # 파일 안의 동작 이름(FBX AnimationStack, GLB animation). 비면 첫 동작
    duration: float = 0.0  # 초
    version: str = ""
    bones: int = 0  # 움직이는 사람 모양 뼈 수
    clips: list[str] = field(default_factory=list)  # 파일 안의 동작 이름 전체
    license: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def kind_name(self) -> str:
        return KINDS.get(self.kind, self.kind)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- 형식 확인


def _read_glb(path: Path) -> dict[str, Any]:
    try:
        return character.read_glb(path)[0]
    except character.CharacterError as error:
        raise MotionError(str(error).replace("VRM(glTF 바이너리) 파일이 아님", "VRMA, GLB(glTF 바이너리) 파일이 아님")) from error
    except (ValueError, UnicodeDecodeError, struct.error) as error:
        raise MotionError(f"동작 파일 정보를 읽지 못함(손상 또는 다른 형식): {path.name}") from error


def _duration(gltf: dict[str, Any], animation: dict[str, Any]) -> float:
    """glTF 애니메이션 길이: 시간 접근자(input)의 최댓값(glTF 규격상 필수 항목)."""
    accessors = gltf.get("accessors") or []
    longest = 0.0
    for sampler in animation.get("samplers") or []:
        index = sampler.get("input") if isinstance(sampler, dict) else None
        if isinstance(index, int) and 0 <= index < len(accessors) and isinstance(accessors[index], dict):
            top = accessors[index].get("max") or []
            if top and isinstance(top[0], (int, float)):
                longest = max(longest, float(top[0]))
    return round(longest, 3)


def vrma_details(gltf: dict[str, Any]) -> dict[str, Any]:
    """VRMA(VRMC_vrm_animation 1.0): 뼈는 VRM 뼈 이름으로 지정되어 있어 이름 대응이 필요 없다."""
    extension = (gltf.get("extensions") or {}).get("VRMC_vrm_animation")
    if not isinstance(extension, dict):
        raise MotionError("VRMA 정보(VRMC_vrm_animation 확장)가 없는 파일")
    bones = (extension.get("humanoid") or {}).get("humanBones") or {}
    if not isinstance(bones, dict) or "hips" not in bones:
        raise MotionError("VRMA에 엉덩이(hips) 뼈 정보 없음: VRM Animation 1.0 형식으로 다시 내보내기")
    animations = [item for item in gltf.get("animations") or [] if isinstance(item, dict)]
    if not animations:
        raise MotionError("VRMA에 동작(animation) 없음")
    preset = ((extension.get("expressions") or {}).get("preset") or {})
    warnings = []
    if any(name in preset for name in DRIVEN_EXPRESSIONS):
        warnings.append("동작에 든 입 모양, 눈 감기, 웃음 표정은 사용하지 않음(목소리, 눈 깜빡임, 얼굴 추적 우선)")
    nodes = {item.get("node") for item in bones.values() if isinstance(item, dict)}
    animated = {channel["target"].get("node") for channel in animations[0].get("channels") or []
                if isinstance(channel, dict) and isinstance(channel.get("target"), dict)} & nodes
    if not animated:
        raise MotionError("VRMA에 사람 모양 뼈를 움직이는 동작이 없음")
    return {"version": f"VRMA {extension.get('specVersion', '1.0')}", "duration": _duration(gltf, animations[0]), "bones": len(animated),
            "clips": [], "clip": "", "warnings": warnings}


def glb_details(gltf: dict[str, Any], clip: str = "") -> dict[str, Any]:
    """동작이 든 GLB(Mixamo 캐릭터를 Blender에서 내보낸 파일 등). 뼈 이름으로 VRM 뼈를 찾는다."""
    extensions = gltf.get("extensions") or {}
    if isinstance(extensions, dict) and ("VRM" in extensions or "VRMC_vrm" in extensions):
        raise MotionError("VRM 캐릭터 파일: 캐릭터로 등록(debutkit character add)")
    animations = [item for item in gltf.get("animations") or [] if isinstance(item, dict)]
    if not animations:
        raise MotionError("동작(animation)이 없는 GLB: 동작을 포함해 다시 내보내기")
    names = [str(item.get("name") or f"animation_{index}") for index, item in enumerate(animations)]  # three.js GLTFLoader와 같은 이름
    chosen = _choose(names, clip)
    nodes = [node if isinstance(node, dict) else {} for node in gltf.get("nodes") or []]
    matched = _humanoid([str(node.get("name") or "") for node in nodes])
    animated = {nodes[channel["target"]["node"]].get("name") for channel in animations[chosen].get("channels") or []
                if isinstance(channel, dict) and isinstance(channel.get("target"), dict) and isinstance(channel["target"].get("node"), int)
                and 0 <= channel["target"]["node"] < len(nodes)}
    return {"version": "GLB(glTF 2.0)", "duration": _duration(gltf, animations[chosen]), "bones": _count(matched, animated),
            "clips": names, "clip": names[chosen], "warnings": _clip_warnings(names, chosen)}


def fbx_details(path: Path, clip: str = "") -> dict[str, Any]:
    """동작이 든 FBX(Mixamo 등). 동작(AnimationStack)과 움직이는 뼈(AnimationCurveNode 연결)를 확인.

    연결(Connections): 곡선 묶음(AnimationCurveNode)은 뼈(OP)와 동작 층(AnimationLayer, OO)에, 동작 층은 동작(OO)에 연결된다.
    Mixamo FBX에는 비어 있는 동작(Take 001)이 함께 들어 있어, 곡선이 연결된 동작만 목록에 넣고 곡선이 가장 많은 동작을 기본으로 고른다.
    """
    data = path.read_bytes()
    stacks: list[tuple[Any, str, float]] = []  # (ID, 이름, 길이 초)
    bones: dict[Any, str] = {}
    curves: set[Any] = set()
    layers: set[Any] = set()
    links: list[tuple[str, Any, Any]] = []  # (종류, 자식, 부모)
    if data.startswith(character.FBX_MAGIC):
        version = struct.unpack_from("<I", data, 23)[0]
        try:
            tree = character._fbx_binary(data)
        except struct.error as error:
            raise MotionError(f"FBX 파일을 끝까지 읽지 못함(손상): {path.name}") from error
        except character.CharacterError as error:
            raise MotionError(str(error)) from error
        top = {name: children for name, _, children in tree}
        for name, properties, children in top.get("Objects", []):
            label = properties[1].split("\x00\x01")[0] if len(properties) > 2 and isinstance(properties[1], str) else ""
            kind = properties[2] if len(properties) > 2 and isinstance(properties[2], str) else ""
            if name == "Model" and kind in ("LimbNode", "Root"):
                bones[properties[0]] = label
            elif name == "AnimationCurveNode" and properties:
                curves.add(properties[0])
            elif name == "AnimationLayer" and properties:
                layers.add(properties[0])
            elif name == "AnimationStack" and properties:
                values = {item[1][0]: item[1][-1] for group in children if group[0] == "Properties70" for item in group[2] if item[1]}
                stop = values.get("LocalStop", values.get("ReferenceStop", 0))
                stacks.append((properties[0], label, float(stop) / KTIME if isinstance(stop, (int, float)) else 0.0))
        links = [(item[1][0], item[1][1], item[1][2]) for item in top.get("Connections", [])
                 if item[0] == "C" and len(item[1]) >= 3 and item[1][0] in ("OO", "OP")]
    else:
        text = data.decode("utf-8", "replace")
        match = re.search(r"FBXVersion:\s*(\d+)", text)
        if not text.lstrip().startswith(";") or not match:
            raise MotionError(f"FBX 파일이 아님: {path.name}")
        version = int(match.group(1))
        bones = {int(number): name for number, name in re.findall(r'Model:\s*(-?\d+),\s*"Model::([^"]*)",\s*"(?:LimbNode|Root)"', text)}
        curves = {int(number) for number in re.findall(r'AnimationCurveNode:\s*(-?\d+),', text)}
        layers = {int(number) for number in re.findall(r'AnimationLayer:\s*(-?\d+),', text)}
        found = re.findall(r'AnimationStack:\s*(-?\d+),\s*"AnimStack::([^"]*)"', text)
        stops = [int(value) / KTIME for value in re.findall(r'P:\s*"LocalStop",\s*"KTime",\s*"Time",\s*"",\s*(-?\d+)', text)]
        stacks = [(int(number), name, stops[index] if index < len(stops) else 0.0) for index, (number, name) in enumerate(found)]
        links = [(kind, int(child), int(parent)) for kind, child, parent in re.findall(r'C:\s*"(OO|OP)",\s*(-?\d+),\s*(-?\d+)', text)]
    if version < 7000:
        raise MotionError(f"FBX {version / 1000:.1f} 형식은 지원하지 않음: FBX 2011(7.0) 이후 형식으로 다시 내보내기")
    # 동작마다 연결된 곡선 묶음. 동작 층 연결이 없는 파일은 모든 곡선을 모든 동작의 것으로 본다
    owner = {child: parent for kind, child, parent in links if kind == "OO" and child in layers}
    stack_of = {child: owner.get(parent) for kind, child, parent in links if kind == "OO" and child in curves and parent in layers}
    usable = []
    for number, name, seconds in stacks:
        own = {curve for curve, stack in stack_of.items() if stack == number} if stack_of else curves
        if own:
            usable.append((name, seconds, own))
    if not usable:
        raise MotionError("동작이 없는 FBX: Mixamo에서는 동작을 고른 뒤 받은 파일(Skin은 With, Without 모두 가능) 등록")
    names = [name or f"animation_{index}" for index, (name, _, _) in enumerate(usable)]
    chosen = _choose(names, clip) if clip else max(range(len(usable)), key=lambda index: (len(usable[index][2]), usable[index][1]))
    matched = _humanoid(list(bones.values()))
    own = usable[chosen][2]
    animated = {bones[parent] for kind, child, parent in links if kind == "OP" and child in own and parent in bones}
    has_targets = any(kind == "OP" and child in curves for kind, child, _ in links)
    return {"version": f"FBX {version // 1000}.{version % 1000 // 100}", "duration": round(usable[chosen][1], 3),
            "bones": _count(matched, animated) if has_targets else len(matched), "clips": names, "clip": names[chosen],
            "warnings": _clip_warnings(names, chosen)}


def _choose(names: list[str], clip: str) -> int:
    if not clip:
        return 0
    if clip not in names:
        raise MotionError(f"파일에 없는 동작 이름: {clip}. 동작 목록: {', '.join(names)}")
    return names.index(clip)


def _clip_warnings(names: list[str], chosen: int) -> list[str]:
    if len(names) < 2:
        return []
    others = [name for index, name in enumerate(names) if index != chosen]
    return [f"파일 안의 동작 {len(names)}개 중 {names[chosen]} 사용. 다른 동작({', '.join(others[:5])}{' 등' if len(others) > 5 else ''})은 동작 이름을 지정해 다시 등록"]


def _humanoid(names: list[str]) -> dict[str, str]:
    """VRM 뼈 이름 -> 파일의 뼈 이름. 사람 모양 뼈(VRM 필수 15개)가 없으면 MotionError."""
    matched = humanoid.match_bones(names)
    missing = humanoid.missing_bones(matched)
    if missing:
        labels = ", ".join(humanoid.bone_label(bone) for bone in missing[:6]) + (f" 외 {len(missing) - 6}개" if len(missing) > 6 else "")
        raise MotionError(f"사람 모양 뼈를 찾지 못함({labels}). 지원하는 뼈 이름: Mixamo, VRoid, Unreal, Blender(Rigify), MMD, "
                          "Character Creator, 3ds Max Biped 방식")
    return matched


def _count(matched: dict[str, str], animated: Iterable[Any]) -> int:
    count = len({name for name in animated if name} & set(matched.values()))
    if not count:
        raise MotionError("사람 모양 뼈를 움직이는 동작이 없음: 동작을 뼈대(Armature)에 적용해 다시 내보내기")
    return count


def detect(path: Path) -> str:
    """동작 파일 종류(vrma, fbx, glb)."""
    suffix = path.suffix.lower()
    if suffix == ".fbx":
        return "fbx"
    if suffix in (".vrma", ".glb"):
        extensions = _read_glb(path).get("extensions") or {}
        return "vrma" if isinstance(extensions, dict) and "VRMC_vrm_animation" in extensions else "glb" if suffix == ".glb" else "vrma"
    if suffix == ".bvh":
        raise MotionError("BVH 동작은 지원하지 않음: VRM 공식 변환 도구(bvh2vrma)로 VRMA로 바꿔 등록")
    if suffix == ".vrm":
        raise MotionError("VRM 캐릭터 파일: 캐릭터로 등록(debutkit character add)")
    raise MotionError(f"지원하지 않는 동작 파일: {path.name}(VRMA, FBX, GLB 또는 이 파일들을 담은 zip, 폴더)")


def inspect(path: str | Path, clip: str = "") -> Motion:
    """등록 전 확인(복사하지 않음)."""
    path = Path(path)
    if not path.is_file():
        raise MotionError(f"파일 없음: {path}")
    kind = detect(path)
    try:
        if kind == "fbx":
            details = fbx_details(path, clip)
        else:
            gltf = _read_glb(path)
            details = vrma_details(gltf) if kind == "vrma" else glb_details(gltf, clip)
    except MotionError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, struct.error) as error:
        raise MotionError(f"동작 파일 정보를 읽지 못함(손상 또는 다른 형식): {path.name}") from error
    license_ = ["동작 파일 사용 조건은 배포처 조건 확인(표기 필요 여부, 수익 방송, 재배포 금지)"]
    if kind == "vrma":
        license_.append("VRoid 공식 동작(BOOTH 무료 배포)은 표기 조건으로 개인, 법인 방송 사용 가능, 파일 재배포 불가")
    if kind in ("fbx", "glb") and details["bones"]:
        license_.append("Mixamo 동작: 방송 사용 가능, 원본 파일 재배포 불가(Adobe Mixamo 약관)")
    warnings = list(details["warnings"])
    if details["duration"] <= 0:
        warnings.append("동작 길이를 확인하지 못함: 캐릭터 화면에서 재생해 확인")
    elif details["duration"] > 60:
        warnings.append(f"긴 동작({details['duration']:.0f}초): 후원 반응에는 10초 이내 동작 권장")
    # FBX, GLB는 동작 이름을 함께 저장(캐릭터 화면이 이름으로 찾음. 파일 안 첫 동작이 비어 있는 경우가 있음)
    return Motion("", path.stem, kind, path.name, details["clip"], details["duration"], details["version"], details["bones"], details["clips"],
                  license_, warnings)


# --------------------------------------------------------------------------- 보관함


def library_dir() -> Path:
    return settings.settings_path().parent / "motions"


def _files(path: Path) -> list[Path]:
    """폴더 안의 동작 파일(Mac 부가 파일 제외, VRM 캐릭터 GLB 제외)."""
    found = []
    for item in sorted(path.rglob("*")):
        if item.is_file() and item.suffix.lower() in SUFFIXES and not character._mac_junk(item.relative_to(path)):
            found.append(item)
    return found


def add(path: str | Path, name: str = "", clip: str = "") -> tuple[list[Motion], list[str]]:
    """확인 후 보관함에 복사해 등록. zip, 폴더는 안의 동작 파일을 모두 등록. 반환: (등록한 동작, 건너뛴 파일 안내)."""
    path = Path(path)
    with tempfile.TemporaryDirectory() as temporary:
        if path.is_file() and path.suffix.lower() == ".zip":
            try:
                path = character._extract(path, Path(temporary))
            except character.CharacterError as error:
                raise MotionError(str(error)) from error
        if path.is_file():
            return [_store(inspect(path, clip), path, name)], []
        if not path.is_dir():
            raise MotionError(f"파일 또는 폴더 없음: {path}")
        files = _files(path)
        if not files:
            raise MotionError("폴더에서 동작 파일(.vrma, .fbx, .glb)을 찾지 못함")
        added, skipped = [], []
        for item in files:
            try:
                added.append(_store(inspect(item), item, name if len(files) == 1 else ""))
            except (MotionError, OSError) as error:
                skipped.append(f"{item.name}: {error}")
        if not added:
            raise MotionError("등록할 수 있는 동작 파일 없음. " + " / ".join(skipped[:3]))
        return added, skipped


def _store(motion: Motion, source: Path, name: str) -> Motion:
    library = library_dir()
    library.mkdir(parents=True, exist_ok=True)
    taken = {item.name for item in library.iterdir() if item.is_dir()}
    motion.name = name or (f"{source.stem} {motion.clip}" if motion.clip and len(motion.clips) > 1 else source.stem)
    motion.id = character._slug(motion.name, taken)
    folder = library / motion.id
    folder.mkdir()
    try:
        shutil.copy2(source, folder / source.name)
        (folder / "motion.json").write_text(json.dumps(motion.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return motion


def load(folder: Path) -> Motion | None:
    try:
        data = json.loads((folder / "motion.json").read_text(encoding="utf-8"))
        return Motion(**{key: data[key] for key in Motion.__dataclass_fields__ if key in data})
    except (OSError, ValueError, TypeError, KeyError):
        return None


def all_motions() -> list[Motion]:
    library = library_dir()
    if not library.is_dir():
        return []
    found = [load(folder) for folder in sorted(library.iterdir()) if folder.is_dir()]
    return [item for item in found if item is not None]


def get(motion_id: str | None) -> Motion | None:
    if not motion_id:
        return None
    for item in all_motions():
        if item.id == motion_id:
            return item
    return None


def remove(motion_id: str) -> Path | None:
    folder = library_dir() / motion_id
    if not motion_id or not (folder / "motion.json").is_file():
        return None
    shutil.rmtree(folder)
    saved = settings.load()
    if saved.get("idle_motion") == motion_id:
        saved.pop("idle_motion")
        settings.save(saved)
    return folder


def idle() -> Motion | None:
    """기본 동작(대기 중 반복). 없으면 None."""
    return get(settings.load().get("idle_motion"))


def set_idle(motion_id: str | None) -> Motion | None:
    """기본 동작 지정. None이나 빈 값이면 해제(캐릭터 화면의 기본 움직임)."""
    saved = settings.load()
    if not motion_id:
        saved.pop("idle_motion", None)
        settings.save(saved)
        return None
    found = get(motion_id)
    if found is None:
        raise MotionError(f"등록한 동작 없음: {motion_id}")
    settings.save({**saved, "idle_motion": found.id})
    return found


def file_path(motion: Motion, relative: str) -> Path | None:
    """캐릭터 화면이 요청한 동작 파일. 등록한 파일 이름과 다르거나 보관함 밖이면 None."""
    folder = (library_dir() / motion.id).resolve()
    if relative != motion.file:
        return None
    target = (folder / relative).resolve()
    return target if target.is_file() and target.is_relative_to(folder) else None


def overview() -> dict[str, Any]:
    """캐릭터 화면, 설정 화면이 받는 동작 목록(``/motion/list``)."""
    import urllib.parse

    current = idle()
    return {"idle": current.id if current else "",
            "motions": [{"id": item.id, "name": item.name, "kind": item.kind, "clip": item.clip, "duration": item.duration,
                         "url": f"/motion/files/{urllib.parse.quote(item.id)}/{urllib.parse.quote(item.file)}"} for item in all_motions()]}


# --------------------------------------------------------------------------- 실행 요청(캐릭터 화면으로)


class MotionState:
    """캐릭터 화면들이 받는 동작 실행 요청. 화면은 연결할 때 받는 현재 값(지난 요청)은 재생하지 않고 새 요청만 재생한다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[Any] = []
        self.current: dict[str, Any] = {"play": "", "stop": False, "seq": 0, "time": 0.0}

    def play(self, motion_id: str = "", *, stop: bool = False) -> dict[str, Any]:
        with self._lock:
            self.current = {"play": "" if stop else motion_id, "stop": stop, "seq": self.current["seq"] + 1, "time": round(time.time(), 3)}
            state, subscribers = dict(self.current), list(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(state)
            except Exception:  # 가득 찬 대기열(멈춘 화면)
                pass
        return state

    def subscribe(self, into: Any = None) -> tuple[Any, dict[str, Any]]:
        import queue

        subscriber = into if into is not None else queue.Queue(maxsize=50)
        with self._lock:
            self._subscribers.append(subscriber)
            return subscriber, dict(self.current)

    def unsubscribe(self, subscriber: Any) -> None:
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)


class MotionReactor:
    """오버레이 허브에 붙여 후원, 멤버십이 오면 동작 실행(debutkit 캐릭터 화면의 3D 캐릭터). 규칙은 VTube Studio 후원 반응과 같은 형식."""

    def __init__(self, reactions: list[Any], state: MotionState) -> None:
        self.reactions = reactions
        self.state = state
        self.played: list[str] = []

    def __call__(self, event: Any) -> None:
        from .vts import pick_reaction

        if getattr(event, "kind", "") not in ("donation", "member") or getattr(event, "platform", "") == "system":
            return
        reaction = pick_reaction(self.reactions, float(getattr(event, "amount", 0) or 0), str(getattr(event, "unit", "") or ""))
        if reaction is not None and get(reaction.hotkey) is not None:
            self.state.play(reaction.hotkey)
            self.played.append(reaction.hotkey)
