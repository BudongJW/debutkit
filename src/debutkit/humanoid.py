"""일반 3D 모델(GLB, FBX)의 뼈와 표정 이름을 VRM 사람 모양 뼈, 표정 이름으로 대응.

- 캐릭터 등록(이 모듈)과 캐릭터 화면(브라우저, ``/character/humanoid.json``)이 같은 표를 쓴다
- 비교는 :func:`bone_key`, :func:`morph_keys` 결과로 한다. 브라우저의 같은 이름 함수(character.js)와 규칙이 같아야 한다
  (공백, ``_ - . : / [ ] \\ |`` 제거 후 소문자. three.js가 노드 이름에서 지우는 문자를 모두 포함)
- 지원하는 뼈 이름 방식: Mixamo, VRoid(VRM 원본 이름), Unreal, Blender(Rigify, 일반), MMD, Character Creator, 3ds Max Biped, VRM 뼈 이름
- VRM 1.0 필수 뼈 15개(https://github.com/vrm-c/vrm-specification/blob/master/specification/VRMC_vrm-1.0/humanoid.md)
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Iterable

REQUIRED = ("hips", "spine", "head", "leftUpperArm", "leftLowerArm", "leftHand", "rightUpperArm", "rightLowerArm", "rightHand",
            "leftUpperLeg", "leftLowerLeg", "leftFoot", "rightUpperLeg", "rightLowerLeg", "rightFoot")

BONE_NAMES = {"hips": "엉덩이", "spine": "척추", "chest": "가슴", "upperChest": "윗가슴", "neck": "목", "head": "머리", "jaw": "턱",
              "Shoulder": "어깨", "UpperArm": "위팔", "LowerArm": "아래팔", "Hand": "손", "UpperLeg": "허벅지", "LowerLeg": "종아리",
              "Foot": "발", "Toes": "발가락", "Eye": "눈"}

_CENTER = {
    "hips": ["Hips", "J_Bip_C_Hips", "pelvis", "DEF-spine", "CC_Base_Hip", "Bip001 Pelvis", "下半身"],
    "spine": ["Spine", "J_Bip_C_Spine", "spine_01", "DEF-spine.001", "CC_Base_Waist", "Bip001 Spine", "上半身"],
    "chest": ["Chest", "Spine1", "J_Bip_C_Chest", "spine_02", "DEF-spine.002", "CC_Base_Spine01", "Bip001 Spine1", "上半身2"],
    "upperChest": ["UpperChest", "Spine2", "J_Bip_C_UpperChest", "spine_03", "DEF-spine.003", "CC_Base_Spine02", "Bip001 Spine2", "上半身3"],
    "neck": ["Neck", "J_Bip_C_Neck", "neck_01", "DEF-spine.004", "CC_Base_NeckTwist01", "Bip001 Neck", "首"],
    "head": ["Head", "J_Bip_C_Head", "DEF-spine.006", "CC_Base_Head", "Bip001 Head", "頭"],
    "jaw": ["Jaw", "J_Bip_C_Jaw", "DEF-jaw", "CC_Base_JawRoot", "Bip001 Jaw", "あご"],
}
#: {Side}: Left/Right, {S}: L/R, {s}: l/r, {jp}: 左/右
_SIDED = {
    "Shoulder": ["{Side}Shoulder", "J_Bip_{S}_Shoulder", "clavicle_{s}", "DEF-shoulder.{S}", "Shoulder.{S}", "CC_Base_{S}_Clavicle",
                 "Bip001 {S} Clavicle", "{jp}肩"],
    "UpperArm": ["{Side}Arm", "{Side}UpperArm", "J_Bip_{S}_UpperArm", "upperarm_{s}", "DEF-upper_arm.{S}", "upper_arm.{S}",
                 "CC_Base_{S}_Upperarm", "Bip001 {S} UpperArm", "{jp}腕"],
    "LowerArm": ["{Side}ForeArm", "{Side}LowerArm", "J_Bip_{S}_LowerArm", "lowerarm_{s}", "DEF-forearm.{S}", "forearm.{S}",
                 "CC_Base_{S}_Forearm", "Bip001 {S} Forearm", "{jp}ひじ"],
    "Hand": ["{Side}Hand", "J_Bip_{S}_Hand", "hand_{s}", "DEF-hand.{S}", "Hand.{S}", "CC_Base_{S}_Hand", "Bip001 {S} Hand", "{jp}手首"],
    "UpperLeg": ["{Side}UpLeg", "{Side}UpperLeg", "{Side}Thigh", "J_Bip_{S}_UpperLeg", "thigh_{s}", "DEF-thigh.{S}", "thigh.{S}",
                 "CC_Base_{S}_Thigh", "Bip001 {S} Thigh", "{jp}足"],
    "LowerLeg": ["{Side}Leg", "{Side}LowerLeg", "{Side}Calf", "{Side}Shin", "J_Bip_{S}_LowerLeg", "calf_{s}", "DEF-shin.{S}", "shin.{S}",
                 "CC_Base_{S}_Calf", "Bip001 {S} Calf", "{jp}ひざ"],
    "Foot": ["{Side}Foot", "J_Bip_{S}_Foot", "foot_{s}", "DEF-foot.{S}", "Foot.{S}", "CC_Base_{S}_Foot", "Bip001 {S} Foot", "{jp}足首"],
    "Toes": ["{Side}ToeBase", "{Side}Toes", "{Side}Toe", "J_Bip_{S}_ToeBase", "ball_{s}", "DEF-toe.{S}", "toe.{S}", "CC_Base_{S}_ToeBase",
             "Bip001 {S} Toe0", "{jp}つま先"],
    "Eye": ["{Side}Eye", "J_Adj_{S}_FaceEye", "eye_{s}", "DEF-eye.{S}", "Eye.{S}", "CC_Base_{S}_Eye", "{jp}目"],
}
_SIDES = {"left": {"Side": "Left", "S": "L", "s": "l", "jp": "左"}, "right": {"Side": "Right", "S": "R", "s": "r", "jp": "右"}}

#: 표정 이름(VRM 표정) -> 모델의 형태 변형(morph, blendshape) 이름 후보. VRoid, VRChat, Ready Player Me, MMD, 일반 이름
_EXPRESSIONS = {
    "aa": ["aa", "a", "v_aa", "viseme_aa", "Fcl_MTH_A", "mouth_a", "あ"],
    "ih": ["ih", "i", "v_ih", "viseme_I", "Fcl_MTH_I", "mouth_i", "い"],
    "ou": ["ou", "u", "v_ou", "viseme_U", "Fcl_MTH_U", "mouth_u", "う"],
    "ee": ["ee", "e", "v_e", "v_ee", "viseme_E", "Fcl_MTH_E", "mouth_e", "え"],
    "oh": ["oh", "o", "v_oh", "viseme_O", "Fcl_MTH_O", "mouth_o", "お"],
    "blink": ["blink", "Blink_Both", "Fcl_EYE_Close", "eyes_closed", "まばたき"],
    "blinkLeft": ["blinkLeft", "blink_l", "Blink_Left", "Fcl_EYE_Close_L"],
    "blinkRight": ["blinkRight", "blink_r", "Blink_Right", "Fcl_EYE_Close_R"],
    "happy": ["happy", "joy", "Fcl_ALL_Joy", "笑い"],
}
#: 입 모양, 눈 감기 표정이 없고 ARKit 52개 표정(퍼펙트 싱크)이 있는 모델의 대체 조합(경험적 값)
ARKIT = {
    "aa": {"jawOpen": 1.0},
    "ih": {"jawOpen": 0.25, "mouthSmileLeft": 0.4, "mouthSmileRight": 0.4},
    "ou": {"jawOpen": 0.2, "mouthPucker": 0.9},
    "ee": {"jawOpen": 0.2, "mouthStretchLeft": 0.6, "mouthStretchRight": 0.6},
    "oh": {"jawOpen": 0.45, "mouthFunnel": 0.8},
    "blink": {"eyeBlinkLeft": 1.0, "eyeBlinkRight": 1.0},
    "blinkLeft": {"eyeBlinkLeft": 1.0},
    "blinkRight": {"eyeBlinkRight": 1.0},
    "happy": {"mouthSmileLeft": 0.8, "mouthSmileRight": 0.8, "cheekSquintLeft": 0.4, "cheekSquintRight": 0.4},
}

_STRIP = re.compile(r"[\s_\-.:/\[\]\\|]+")


def normalize(name: str) -> str:
    return _STRIP.sub("", name).lower()


def bone_key(name: str) -> str:
    """뼈 이름 비교 값. Mixamo 앞머리(mixamorig, mixamorig1 등)는 뗀다(Ready Player Me와 이름이 같아짐)."""
    return re.sub(r"^mixamorig\d*", "", normalize(name))


def morph_keys(name: str) -> list[str]:
    """형태 변형 이름 비교 값: 전체, 마지막 마디(``Body.Fcl_MTH_A``, ``blendShape1.jawOpen`` 의 뒷부분)."""
    last = re.split(r"[.|:]", name)[-1]
    return list(dict.fromkeys([normalize(name), normalize(last)]))


@lru_cache(maxsize=1)
def bone_aliases() -> dict[str, str]:
    """비교 값 -> VRM 뼈 이름."""
    table: dict[str, str] = {}

    def add(alias: str, bone: str) -> None:
        key = bone_key(alias)
        if table.get(key, bone) != bone:
            raise ValueError(f"뼈 이름 표 충돌: {alias} ({table[key]}, {bone})")
        table[key] = bone

    for bone, aliases in _CENTER.items():
        add(bone, bone)
        for alias in aliases:
            add(alias, bone)
    for part, templates in _SIDED.items():
        for side, words in _SIDES.items():
            bone = side + part
            add(bone, bone)
            for template in templates:
                add(template.format(**words), bone)
    return table


@lru_cache(maxsize=1)
def expression_aliases() -> dict[str, str]:
    table: dict[str, str] = {}
    for expression, aliases in _EXPRESSIONS.items():
        for alias in aliases:
            key = normalize(alias)
            if table.get(key, expression) != expression:
                raise ValueError(f"표정 이름 표 충돌: {alias}")
            table[key] = expression
    return table


def match_bones(names: Iterable[str]) -> dict[str, str]:
    """VRM 뼈 이름 -> 모델의 뼈 이름. 같은 뼈에 여러 이름이 맞으면 먼저 나온 이름(뿌리에 가까운 뼈)."""
    aliases = bone_aliases()
    found: dict[str, str] = {}
    for name in names:
        bone = aliases.get(bone_key(name))
        if bone and bone not in found:
            found[bone] = name
    return found


def match_expressions(names: Iterable[str]) -> dict[str, dict[str, float]]:
    """VRM 표정 이름 -> {모델의 형태 변형 이름: 가중치}. 이름이 직접 맞지 않는 표정은 ARKit 조합으로 대체."""
    names = list(names)
    aliases = expression_aliases()
    found: dict[str, dict[str, float]] = {}
    for name in names:
        for key in morph_keys(name):
            expression = aliases.get(key)
            if expression and expression not in found:
                found[expression] = {name: 1.0}
                break
    arkit = {normalize(name): name for name in names}
    arkit.update({key: name for name in names for key in morph_keys(name)})
    for expression, parts in ARKIT.items():
        if expression in found:
            continue
        mapped = {arkit[normalize(part)]: weight for part, weight in parts.items() if normalize(part) in arkit}
        if mapped and normalize(next(iter(parts))) in arkit:  # 첫 항목(jawOpen, eyeBlink 등)이 있어야 대체
            found[expression] = mapped
    return found


def missing_bones(found: dict[str, str]) -> list[str]:
    return [bone for bone in REQUIRED if bone not in found]


def bone_label(bone: str) -> str:
    """한국어 뼈 이름(오류 안내용)."""
    for side, word in (("left", "왼쪽 "), ("right", "오른쪽 ")):
        if bone.startswith(side):
            return word + BONE_NAMES.get(bone[len(side):], bone)
    return BONE_NAMES.get(bone, bone)


def table() -> dict[str, Any]:
    """캐릭터 화면이 받는 표(``/character/humanoid.json``)."""
    return {"required": list(REQUIRED), "bones": bone_aliases(), "expressions": expression_aliases(), "arkit": ARKIT}
