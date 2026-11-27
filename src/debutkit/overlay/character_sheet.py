"""캐릭터 그림 만들기(``/character/sheet``): 등록한 VRM을 이 PC 브라우저에서 그려 정면, 3/4, 얼굴, 표정 7종 시트와 PNGTuber 4상태를 만든다.

- 그리기는 브라우저(three.js, three-vrm, 함께 배포). 모델 파일은 이 PC 밖으로 보내지 않는다
- ``/character/sheet/list`` 그릴 수 있는 캐릭터(VRM), ``POST /character/pngtuber`` (``{"source": id, "name": "", "images": {"idle": "data:image/png;base64,..", ...}}``)
  받은 PNG를 확인해 PNGTuber 캐릭터로 등록(원본의 작성자와 사용 조건을 그대로 옮김, character.add_rendered)
- ``/character/sheet/check?id=`` 모델 점검(표정, 텍스처 무게, character.vrm_check), ``POST /character/lighten`` (``{"id": id}``)
  텍스처를 1024px 이하로 줄인 가벼운 사본을 새 캐릭터로 등록(character.lighten, Pillow 필요)
- ``/character/poses`` 내 자세 목록, ``POST /character/poses`` (``{"name", "parts", "tweaks", "file"}``) 이름으로 저장(같은 이름은 바꿈),
  ``POST /character/poses/remove`` (``{"name"}``). 설정 폴더의 poses.json(최대 50개, 뼈 회전 값만)
"""

from __future__ import annotations

import base64
import binascii
import math
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from .. import character, settings
from . import feature

MAX_IMAGE = 8 * 1024 * 1024  # 상태 하나의 PNG(1024x1024 RGBA는 보통 1~3MB)
_PREFIX = "data:image/png;base64,"
POSES = "poses.json"
MAX_POSES = 50
MAX_POSE_NAME = 30
_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")  # 부위, 자세, 뼈 이름(VRM 영어 이름)


def listing(_: Any = None) -> dict[str, Any]:
    return {"characters": [{"id": item.id, "name": item.name, "kind": item.kind, "active": item.id == character.active().id}
                           for item in character.all_characters() if item.kind == "vrm"]}


def _vrm(character_id: str) -> tuple[character.Character, Path]:
    item = character.get(character_id)
    if item is None or item.kind != "vrm":
        raise feature.FeatureError("VRM 캐릭터를 고름")
    model = character.file_path(item, item.files.get("model", ""))
    if model is None:
        raise feature.FeatureError("모델 파일을 찾지 못함", 404)
    return item, model


def check(query: feature.Query) -> dict[str, Any]:
    """모델 점검(표정, 텍스처 무게)과 가벼운 사본을 만들 수 있는지."""
    _, model = _vrm((query.get("id") or [""])[0])
    try:
        gltf, binary = character.read_glb(model)
    except character.CharacterError as error:
        raise feature.FeatureError(str(error)) from None
    result = character.vrm_check(gltf, binary)
    result.update(size=model.stat().st_size, modification=character.modification_allowed(gltf), light=character.LIGHT_TEXTURE)
    return result


def lighten(data: dict[str, Any]) -> dict[str, Any]:
    """가벼운 사본 만들기(텍스처 1024px 이하, 새 캐릭터로 등록. 원본은 그대로)."""
    item, _ = _vrm(str(data.get("id") or ""))
    try:
        made, report = character.lighten(item.id)
    except character.CharacterError as error:
        raise feature.FeatureError(str(error)) from None
    return {"id": made.id, "name": made.name, "before": report["before"], "after": report["after"], "images": len(report["images"])}


def save(data: dict[str, Any]) -> dict[str, Any]:
    source = character.get(str(data.get("source") or ""))
    if source is None or source.kind != "vrm":
        raise feature.FeatureError("그림을 만들 VRM 캐릭터를 고름")
    images = data.get("images")
    if not isinstance(images, dict) or not images.get("idle") or not images.get("talk"):
        raise feature.FeatureError("입 다문 그림(idle)과 입 벌린 그림(talk)이 필요")
    name = " ".join(str(data.get("name") or "").split())[:40]
    with tempfile.TemporaryDirectory() as folder:
        paths: dict[str, Path] = {}
        for state in character.PNG_STATES:
            value = images.get(state)
            if not value:
                continue
            if not isinstance(value, str) or not value.startswith(_PREFIX):
                raise feature.FeatureError("PNG 그림만 받음")
            try:
                raw = base64.b64decode(value[len(_PREFIX):], validate=True)
            except (binascii.Error, ValueError):
                raise feature.FeatureError("그림 자료가 올바르지 않음") from None
            if len(raw) > MAX_IMAGE:
                raise feature.FeatureError("그림 하나는 8MB 이하")
            paths[state] = Path(folder) / f"{state}.png"
            paths[state].write_bytes(raw)
        try:
            made = character.add_rendered(source, paths, name=name)
        except character.CharacterError as error:
            raise feature.FeatureError(str(error)) from None
    return {"id": made.id, "name": made.name, "warnings": made.warnings}


def _numbers(value: Any, count: int, limit: float) -> list[float]:
    if not isinstance(value, list) or len(value) != count:
        raise feature.FeatureError("자세 값이 올바르지 않음")
    numbers = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) or abs(item) > limit:
            raise feature.FeatureError("자세 값이 올바르지 않음")
        numbers.append(round(float(item), 5))
    return numbers


def _part_key(value: Any) -> str:
    if not isinstance(value, str) or not _KEY.match(value):
        raise feature.FeatureError("자세 값이 올바르지 않음")
    return value


def _table(value: Any, check: Any, most: int) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict) or len(value) > most or not all(isinstance(key, str) and _KEY.match(key) for key in value):
        raise feature.FeatureError("자세 값이 올바르지 않음")
    return {key: check(item) for key, item in value.items()}


def _pose_name(data: dict[str, Any]) -> str:
    name = " ".join(str(data.get("name") or "").split())
    if not name:
        raise feature.FeatureError("자세 이름을 입력")
    if len(name) > MAX_POSE_NAME:
        raise feature.FeatureError(f"자세 이름은 {MAX_POSE_NAME}자 이하")
    return name


def _saved_poses() -> list[dict[str, Any]]:
    poses = settings.load_data(POSES).get("poses")
    return [item for item in poses if isinstance(item, dict) and isinstance(item.get("name"), str)] if isinstance(poses, list) else []


def poses(_: Any = None) -> dict[str, Any]:
    """저장한 자세 목록(최근 저장 순)."""
    return {"poses": _saved_poses(), "max": MAX_POSES}


def save_pose(data: dict[str, Any]) -> dict[str, Any]:
    """지금 자세 저장: 부위별 선택, 관절 돌리기(라디안), 자세 파일에서 받은 뼈 회전(사원수). 같은 이름은 바꿈."""
    name = _pose_name(data)
    pose = {
        "name": name,
        "parts": _table(data.get("parts"), _part_key, 10),
        "tweaks": _table(data.get("tweaks"), lambda item: _numbers(item, 3, math.pi), 60),
        "file": _table(data.get("file"), lambda item: _numbers(item, 4, 1.001), 80) or None,
        "saved": time.strftime("%Y-%m-%d %H:%M"),
    }
    others = [item for item in _saved_poses() if item["name"] != name]
    if len(others) >= MAX_POSES:
        raise feature.FeatureError(f"자세는 {MAX_POSES}개까지 저장(안 쓰는 자세를 지움)")
    settings.save_data(POSES, {"poses": [pose, *others]})
    return {"saved": name, "count": len(others) + 1}


def remove_pose(data: dict[str, Any]) -> dict[str, Any]:
    name = _pose_name(data)
    saved = _saved_poses()
    left = [item for item in saved if item["name"] != name]
    if len(left) == len(saved):
        raise feature.FeatureError("저장한 자세에 없음", 404)
    settings.save_data(POSES, {"poses": left})
    return {"removed": name, "count": len(left)}


def make_feature(context: feature.Context) -> feature.Feature:
    return feature.Feature(name="character-sheet", static={"/character/sheet": "character-sheet.html", "/character/sheet.js": "character-sheet.js"},
                           get={"/character/sheet/list": listing, "/character/sheet/check": check, "/character/poses": poses},
                           post={"/character/pngtuber": save, "/character/lighten": lighten,
                                 "/character/poses": save_pose, "/character/poses/remove": remove_pose},
                           body_limit={"/character/pngtuber": 4 * MAX_IMAGE * 4 // 3 + 65536, "/character/poses": 65536})
