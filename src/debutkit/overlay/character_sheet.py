"""캐릭터 그림 만들기(``/character/sheet``): 등록한 VRM을 이 PC 브라우저에서 그려 정면, 3/4, 얼굴, 표정 7종 시트와 PNGTuber 4상태를 만든다.

- 그리기는 브라우저(three.js, three-vrm, 함께 배포). 모델 파일은 이 PC 밖으로 보내지 않는다
- ``/character/sheet/list`` 그릴 수 있는 캐릭터(VRM), ``POST /character/pngtuber`` (``{"source": id, "name": "", "images": {"idle": "data:image/png;base64,..", ...}}``)
  받은 PNG를 확인해 PNGTuber 캐릭터로 등록(원본의 작성자와 사용 조건을 그대로 옮김, character.add_rendered)
"""

from __future__ import annotations

import base64
import binascii
import tempfile
from pathlib import Path
from typing import Any

from .. import character
from . import feature

MAX_IMAGE = 8 * 1024 * 1024  # 상태 하나의 PNG(1024x1024 RGBA는 보통 1~3MB)
_PREFIX = "data:image/png;base64,"


def listing(_: Any = None) -> dict[str, Any]:
    return {"characters": [{"id": item.id, "name": item.name, "kind": item.kind, "active": item.id == character.active().id}
                           for item in character.all_characters() if item.kind == "vrm"]}


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


def make_feature(context: feature.Context) -> feature.Feature:
    return feature.Feature(name="character-sheet", static={"/character/sheet": "character-sheet.html", "/character/sheet.js": "character-sheet.js"},
                           get={"/character/sheet/list": listing}, post={"/character/pngtuber": save},
                           body_limit={"/character/pngtuber": 4 * MAX_IMAGE * 4 // 3 + 65536})
