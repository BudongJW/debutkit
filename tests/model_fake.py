"""시험용 일반 3D 모델: 뼈와 형태 변형이 있는 작은 사람 모양 GLB, 구조만 있는 FBX(바이너리, ASCII).

GLB는 three.js GLTFLoader로 실제 표시할 수 있는 형식(스킨, 역바인드 행렬, 형태 변형, targetNames)으로 만든다.
"""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path

#: VRM 뼈: (부모, 부모 기준 위치). T자 자세, 미터, +Z 정면(왼쪽이 +X)
SKELETON = {
    "hips": (None, (0, 1.0, 0)), "spine": ("hips", (0, 0.1, 0)), "chest": ("spine", (0, 0.15, 0)), "neck": ("chest", (0, 0.2, 0)),
    "head": ("neck", (0, 0.1, 0)), "jaw": ("head", (0, -0.02, 0.05)),
    "leftShoulder": ("chest", (0.05, 0.15, 0)), "leftUpperArm": ("leftShoulder", (0.1, 0, 0)), "leftLowerArm": ("leftUpperArm", (0.25, 0, 0)),
    "leftHand": ("leftLowerArm", (0.25, 0, 0)), "rightShoulder": ("chest", (-0.05, 0.15, 0)), "rightUpperArm": ("rightShoulder", (-0.1, 0, 0)),
    "rightLowerArm": ("rightUpperArm", (-0.25, 0, 0)), "rightHand": ("rightLowerArm", (-0.25, 0, 0)),
    "leftUpperLeg": ("hips", (0.1, -0.05, 0)), "leftLowerLeg": ("leftUpperLeg", (0, -0.45, 0)), "leftFoot": ("leftLowerLeg", (0, -0.45, 0)),
    "rightUpperLeg": ("hips", (-0.1, -0.05, 0)), "rightLowerLeg": ("rightUpperLeg", (0, -0.45, 0)), "rightFoot": ("rightLowerLeg", (0, -0.45, 0)),
}
MIXAMO = {"hips": "Hips", "spine": "Spine", "chest": "Spine1", "neck": "Neck", "head": "Head", "jaw": "Jaw",
          "leftShoulder": "LeftShoulder", "leftUpperArm": "LeftArm", "leftLowerArm": "LeftForeArm", "leftHand": "LeftHand",
          "rightShoulder": "RightShoulder", "rightUpperArm": "RightArm", "rightLowerArm": "RightForeArm", "rightHand": "RightHand",
          "leftUpperLeg": "LeftUpLeg", "leftLowerLeg": "LeftLeg", "leftFoot": "LeftFoot", "rightUpperLeg": "RightUpLeg", "rightLowerLeg": "RightLeg",
          "rightFoot": "RightFoot"}
NAMES = {
    "mixamo": {bone: "mixamorig:" + name for bone, name in MIXAMO.items()},
    "vroid": {bone: "J_Bip_" + ("L_" if bone.startswith("left") else "R_" if bone.startswith("right") else "C_") + bone.removeprefix("left").removeprefix("right")[:1].upper() + bone.removeprefix("left").removeprefix("right")[1:]
              for bone in SKELETON},
    "unreal": {"hips": "pelvis", "spine": "spine_01", "chest": "spine_02", "neck": "neck_01", "head": "head", "jaw": "jaw",
               "leftShoulder": "clavicle_l", "leftUpperArm": "upperarm_l", "leftLowerArm": "lowerarm_l", "leftHand": "hand_l",
               "rightShoulder": "clavicle_r", "rightUpperArm": "upperarm_r", "rightLowerArm": "lowerarm_r", "rightHand": "hand_r",
               "leftUpperLeg": "thigh_l", "leftLowerLeg": "calf_l", "leftFoot": "foot_l", "rightUpperLeg": "thigh_r", "rightLowerLeg": "calf_r",
               "rightFoot": "foot_r"},
    "rigify": {"hips": "DEF-spine", "spine": "DEF-spine.001", "chest": "DEF-spine.002", "neck": "DEF-spine.004", "head": "DEF-spine.006",
               "jaw": "DEF-jaw", "leftShoulder": "DEF-shoulder.L", "leftUpperArm": "DEF-upper_arm.L", "leftLowerArm": "DEF-forearm.L",
               "leftHand": "DEF-hand.L", "rightShoulder": "DEF-shoulder.R", "rightUpperArm": "DEF-upper_arm.R", "rightLowerArm": "DEF-forearm.R",
               "rightHand": "DEF-hand.R", "leftUpperLeg": "DEF-thigh.L", "leftLowerLeg": "DEF-shin.L", "leftFoot": "DEF-foot.L",
               "rightUpperLeg": "DEF-thigh.R", "rightLowerLeg": "DEF-shin.R", "rightFoot": "DEF-foot.R"},
    "mmd": {"hips": "下半身", "spine": "上半身", "chest": "上半身2", "neck": "首", "head": "頭", "jaw": "あご", "leftShoulder": "左肩",
            "leftUpperArm": "左腕", "leftLowerArm": "左ひじ", "leftHand": "左手首", "rightShoulder": "右肩", "rightUpperArm": "右腕",
            "rightLowerArm": "右ひじ", "rightHand": "右手首", "leftUpperLeg": "左足", "leftLowerLeg": "左ひざ", "leftFoot": "左足首",
            "rightUpperLeg": "右足", "rightLowerLeg": "右ひざ", "rightFoot": "右足首"},
}


def _world(bone: str) -> tuple[float, float, float]:
    parent, (x, y, z) = SKELETON[bone]
    if parent is None:
        return (x, y, z)
    px, py, pz = _world(parent)
    return (px + x, py + y, pz + z)


def _z_turn(angle: float) -> tuple[float, float, float, float]:
    """z축 회전 사원수(x, y, z, w)."""
    return (0.0, 0.0, math.sin(angle / 2), math.cos(angle / 2))


#: 시험 동작: 시간(초), 왼쪽 위팔 z축 회전(T자에서 내림), 엉덩이 높이 변화
MOTION_TIMES = (0.0, 1.0, 2.0)
MOTION_ARM = (0.0, -0.6, -1.2)
MOTION_BOB = (0.0, 0.05, 0.0)


def humanoid_glb(path: Path, *, names: str | dict[str, str] = "mixamo", morphs: tuple[str, ...] = (), skip: tuple[str, ...] = (),
                 skin: bool = True, scale: float = 1.0, back: bool = False, vrm: bool = False, clips: tuple[str, ...] = (),
                 mesh: bool = True) -> Path:
    """뼈마다 작은 상자가 붙은 사람 모양 GLB. ``morphs`` 는 머리 상자를 움직이는 형태 변형 이름. ``back`` 은 -Z를 보는 모델.

    ``clips`` 를 주면 이름마다 동작(왼쪽 위팔을 내리고 엉덩이가 오르내림, 2초)을 넣는다. ``mesh=False`` 는 뼈만 있는 동작 파일.
    """
    table = NAMES[names] if isinstance(names, str) else names
    bones = [bone for bone in SKELETON if bone not in skip]
    index = {bone: number for number, bone in enumerate(bones)}
    sign = -1 if back else 1
    nodes = []
    for bone in bones:
        parent, (x, y, z) = SKELETON[bone]
        node = {"name": table[bone], "translation": [x * scale * sign, y * scale, z * scale * sign]}
        children = [index[child] for child in bones if SKELETON[child][0] == bone]
        if children:
            node["children"] = children
        nodes.append(node)
    positions, joints, weights, indices = [], [], [], []
    corners = [(dx, dy, dz) for dx in (-1, 1) for dy in (-1, 1) for dz in (-1, 1)]
    faces = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1), (2, 3, 7), (2, 7, 6), (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3)]
    head_vertices = []
    for bone in bones:
        wx, wy, wz = _world(bone)
        base = len(positions)
        size = 0.06 if bone in ("head", "hips", "chest") else 0.03
        for dx, dy, dz in corners:
            positions.append((((wx + dx * size) * sign) * scale, (wy + dy * size) * scale, ((wz + dz * size) * sign) * scale))
            joints.append((index[bone], 0, 0, 0))
            weights.append((1.0, 0.0, 0.0, 0.0))
        if bone == "head":
            head_vertices = list(range(base, base + 8))
        indices += [base + corner for face in faces for corner in face]
    blob = bytearray()
    views, accessors = [], []

    def add(data: bytes, component: int, count: int, kind: str, target: int | None = None, extra: dict | None = None) -> int:
        while len(blob) % 4:
            blob.append(0)
        view = {"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)}
        if target:
            view["target"] = target
        views.append(view)
        blob.extend(data)
        accessors.append({"bufferView": len(views) - 1, "componentType": component, "count": count, "type": kind, **(extra or {})})
        return len(accessors) - 1

    def bounds(points: list[tuple[float, float, float]]) -> dict:
        return {"min": [min(point[axis] for point in points) for axis in range(3)], "max": [max(point[axis] for point in points) for axis in range(3)]}

    attributes = {"POSITION": add(b"".join(struct.pack("<3f", *point) for point in positions), 5126, len(positions), "VEC3", 34962, bounds(positions))}
    if skin:
        attributes["JOINTS_0"] = add(b"".join(struct.pack("<4H", *item) for item in joints), 5123, len(joints), "VEC4", 34962)
        attributes["WEIGHTS_0"] = add(b"".join(struct.pack("<4f", *item) for item in weights), 5126, len(weights), "VEC4", 34962)
    targets = []
    for number, _ in enumerate(morphs):
        deltas = [(0.0, -0.02 * (number + 1) * scale, 0.0) if vertex in head_vertices else (0.0, 0.0, 0.0) for vertex in range(len(positions))]
        targets.append({"POSITION": add(b"".join(struct.pack("<3f", *delta) for delta in deltas), 5126, len(deltas), "VEC3", 34962, bounds(deltas))})
    primitive = {"attributes": attributes, "indices": add(b"".join(struct.pack("<H", item) for item in indices), 5123, len(indices), "SCALAR", 34963)}
    if targets:
        primitive["targets"] = targets
    mesh = {"name": "Body", "primitives": [primitive]}
    if morphs:
        mesh["extras"] = {"targetNames": list(morphs)}
        mesh["weights"] = [0.0] * len(morphs)
    gltf = {"asset": {"version": "2.0", "generator": "debutkit test"}, "scene": 0, "nodes": nodes, **({"meshes": [mesh]} if mesh else {})}
    mesh_node = {"name": "Body", "mesh": 0}
    if skin and mesh:
        inverse = b"".join(struct.pack("<16f", 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -wx * sign * scale, -wy * scale, -wz * sign * scale, 1)
                           for wx, wy, wz in (_world(bone) for bone in bones))
        gltf["skins"] = [{"joints": list(range(len(bones))), "inverseBindMatrices": add(inverse, 5126, len(bones), "MAT4"), "skeleton": 0}]
        mesh_node["skin"] = 0
    if mesh:
        gltf["nodes"].append(mesh_node)
    gltf["scenes"] = [{"nodes": [index["hips"] if "hips" in index else 0] + ([len(gltf["nodes"]) - 1] if mesh else [])}]
    if clips:
        times = add(b"".join(struct.pack("<f", value) for value in MOTION_TIMES), 5126, 3, "SCALAR", None, {"min": [0.0], "max": [MOTION_TIMES[-1]]})
        turns = add(b"".join(struct.pack("<4f", *_z_turn(angle * sign)) for angle in MOTION_ARM), 5126, 3, "VEC4")
        hips_y = SKELETON["hips"][1][1]
        bobs = add(b"".join(struct.pack("<3f", 0.0, (hips_y + bob) * scale, 0.0) for bob in MOTION_BOB), 5126, 3, "VEC3")
        gltf["animations"] = [{"name": name, "samplers": [{"input": times, "output": turns}, {"input": times, "output": bobs}],
                               "channels": [{"sampler": 0, "target": {"node": index["leftUpperArm"], "path": "rotation"}},
                                            {"sampler": 1, "target": {"node": index["hips"], "path": "translation"}}]} for name in clips]
    if vrm:
        gltf["extensionsUsed"] = ["VRMC_vrm"]
        gltf["extensions"] = {"VRMC_vrm": {"specVersion": "1.0", "meta": {"name": "glb vrm", "authors": ["x"], "licenseUrl": "https://vrm.dev/licenses/1.0/"}}}
    while len(blob) % 4:
        blob.append(0)
    gltf["accessors"], gltf["bufferViews"], gltf["buffers"] = accessors, views, [{"byteLength": len(blob)}]
    text = json.dumps(gltf, ensure_ascii=False).encode("utf-8")
    text += b" " * (-len(text) % 4)
    chunks = struct.pack("<I4s", len(text), b"JSON") + text + struct.pack("<I4s", len(blob), b"BIN\x00") + bytes(blob)
    path.write_bytes(b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks)
    return path


def vrma(path: Path, *, expressions: tuple[str, ...] = (), hips: bool = True, animate: bool = True) -> Path:
    """VRMA(VRMC_vrm_animation 1.0): 사람 모양 뼈 노드(T자 자세)와 동작(왼쪽 위팔 내림, 엉덩이 오르내림, 2초)."""
    bones = [bone for bone in SKELETON if hips or bone != "hips"]
    glb = humanoid_glb(path, names={bone: bone.capitalize() for bone in SKELETON}, skip=() if hips else ("hips",), mesh=False, skin=False,
                       clips=("VRMA",) if animate and hips else ())
    data = glb.read_bytes()
    length = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20:20 + length])
    rest = data[20 + length:]
    extension = {"specVersion": "1.0", "humanoid": {"humanBones": {bone: {"node": number} for number, bone in enumerate(bones)}}}
    if expressions:
        start = len(gltf["nodes"])
        gltf["nodes"] += [{"name": name} for name in expressions]
        extension["expressions"] = {"preset": {name: {"node": start + number} for number, name in enumerate(expressions)}}
    gltf["extensionsUsed"] = ["VRMC_vrm_animation"]
    gltf["extensions"] = {"VRMC_vrm_animation": extension}
    text = json.dumps(gltf).encode("utf-8")
    text += b" " * (-len(text) % 4)
    chunks = struct.pack("<I4s", len(text), b"JSON") + text + rest
    path.write_bytes(b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks)
    return path


def _fbx_node(name: str, properties: list, children: list, offset: int, wide: bool) -> bytes:
    """FBX 바이너리 노드 하나(속성 S, L, R, I). ``offset`` 은 이 노드가 놓일 파일 위치."""
    body = b""
    for value in properties:
        if isinstance(value, str):
            raw = value.encode("utf-8")
            body += b"S" + struct.pack("<I", len(raw)) + raw
        elif isinstance(value, bytes):
            body += b"R" + struct.pack("<I", len(value)) + value
        else:
            body += b"L" + struct.pack("<q", value)
    head_size = 25 if wide else 13
    position = offset + head_size + len(name.encode()) + len(body)
    nested = b""
    for child in children:
        encoded = _fbx_node(*child, position + len(nested), wide)
        nested += encoded
    if children:
        nested += b"\x00" * head_size
    end = position + len(nested)
    fmt = "<QQQB" if wide else "<IIIB"
    return struct.pack(fmt, end, len(properties), len(body), len(name.encode())) + name.encode() + body + nested


def fbx_binary(path: Path, *, bones: list[str], morphs: list[str] = (), videos: list[tuple[str, bytes]] = (), version: int = 7400,
               stacks: list[tuple[str, float]] = (), animated: list[str] = (), layered: bool = False) -> Path:
    """구조만 있는 FBX 바이너리(Objects의 Model, Deformer, Video). 뼈는 LimbNode.

    ``stacks`` 는 동작(AnimationStack 이름, 길이 초), ``animated`` 는 동작이 움직이는 뼈(AnimationCurveNode와 Connections).
    ``layered`` 는 Mixamo처럼 동작마다 동작 층(AnimationLayer)을 두고 곡선은 마지막 동작에만 연결(앞 동작은 비어 있음).
    """
    wide = version >= 7500
    objects = [("Model", [index + 1, f"{name}\x00\x01Model", "LimbNode"], []) for index, name in enumerate(bones)]
    links = []
    for index, (name, seconds) in enumerate(stacks):
        properties = [("P", ["LocalStop", "KTime", "Time", "", round(seconds * 46_186_158_000)], [])]
        objects.append(("AnimationStack", [5000 + index, f"{name}\x00\x01AnimStack", ""], [("Properties70", [], properties)]))
        if layered:
            objects.append(("AnimationLayer", [7000 + index, "BaseLayer\x00\x01AnimLayer", ""], []))
            links.append(("C", ["OO", 7000 + index, 5000 + index], []))
    for index, name in enumerate(animated):
        objects.append(("AnimationCurveNode", [6000 + index, "R\x00\x01AnimCurveNode", ""], []))
        links.append(("C", ["OP", 6000 + index, bones.index(name) + 1, "Lcl Rotation"], []))
        if layered:
            links.append(("C", ["OO", 6000 + index, 7000 + len(stacks) - 1], []))
    objects += [("Deformer", [1000 + index, f"{name}\x00\x01SubDeformer", "BlendShapeChannel"], []) for index, name in enumerate(morphs)]
    objects.append(("Model", [999, "Body\x00\x01Model", "Mesh"], []))
    for index, (relative, content) in enumerate(videos):
        children = [("RelativeFilename", [relative], []), ("Filename", ["C:\\artist\\" + relative], [])]
        if content:
            children.append(("Content", [content], []))
        objects.append(("Video", [2000 + index, "tex\x00\x01Video", "Clip"], children))
    data = b"Kaydara FBX Binary  \x00\x1a\x00" + struct.pack("<I", version)
    for node in [("FBXHeaderExtension", [], [("FBXVersion", [version], [])]), ("Objects", [], objects), ("Connections", [], links)]:
        data += _fbx_node(*node, len(data), wide)
    data += b"\x00" * (25 if wide else 13)
    path.write_bytes(data)
    return path


def fbx_ascii(path: Path, *, bones: list[str], morphs: list[str] = (), textures: list[str] = (), stacks: list[tuple[str, float]] = (),
              animated: list[str] = ()) -> Path:
    lines = ["; FBX 7.4.0 project file", "FBXHeaderExtension:  {", "    FBXVersion: 7400", "}", "Objects:  {"]
    for index, name in enumerate(bones):
        lines += [f'    Model: {index + 1}, "Model::{name}", "LimbNode" {{', "    }"]
    for index, (name, seconds) in enumerate(stacks):
        lines += [f'    AnimationStack: {5000 + index}, "AnimStack::{name}", "" {{', "        Properties70:  {",
                  f'            P: "LocalStop", "KTime", "Time", "",{round(seconds * 46_186_158_000)}', "        }", "    }"]
    for index, _ in enumerate(animated):
        lines += [f'    AnimationCurveNode: {6000 + index}, "AnimCurveNode::R", "" {{', "    }"]
    for index, name in enumerate(morphs):
        lines += [f'    Deformer: {index + 100}, "SubDeformer::{name}", "BlendShapeChannel" {{', "    }"]
    for index, name in enumerate(textures):
        lines += [f'    Video: {index + 200}, "Video::tex", "Clip" {{', f'        RelativeFilename: "{name}"', "    }"]
    lines.append("}")
    if animated:
        lines.append("Connections:  {")
        lines += [f'    C: "OP",{6000 + index},{bones.index(name) + 1}, "Lcl Rotation"' for index, name in enumerate(animated)]
        lines.append("}")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
