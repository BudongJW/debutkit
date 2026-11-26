"""방송 이미지 만들기(``/decor``): 프사, 방송국과 채널 배너, 다시보기 썸네일을 이 PC 브라우저에서 그려 PNG, JPEG로 저장.

- 그리기는 브라우저 캔버스(방송 색, 함께 배포한 글꼴). 올린 그림은 브라우저 안에서만 쓰고 서버로 보내지 않는다
- ``/decor/characters``: 그림으로 쓸 수 있는 캐릭터(PNGTuber는 입 다문 그림, 3D는 미리보기 그림)
"""

from __future__ import annotations

import urllib.parse
from typing import Any

from .. import character
from . import feature

#: 만들 수 있는 그림: 키 -> (이름, 가로, 세로, 설명). 규격은 각 플랫폼 안내 기준(바뀌면 여기만 고침)
FORMATS = {
    "profile": ("프사", 1024, 1024, "원형으로 잘려도 보이게 가운데에 캐릭터"),
    "thumbnail": ("다시보기 썸네일", 1280, 720, "YouTube, 치지직, SOOP 다시보기 16:9"),
    "youtube": ("YouTube 채널 배너", 2560, 1440, "모든 기기에 보이는 가운데 1546x423 안에 글자와 캐릭터"),
    "twitch": ("Twitch 프로필 배너", 1200, 480, "채널 위쪽 배너"),
    "soop": ("SOOP 방송국 배너", 720, 150, "JPEG 200KB 이하로 저장"),
}


def _picture(item: character.Character) -> str:
    if item.kind == "png" and item.files.get("idle"):
        name = item.files["idle"]
    elif item.thumbnail:
        name = item.thumbnail
    else:
        return ""
    return f"/character/files/{urllib.parse.quote(item.id)}/{urllib.parse.quote(name)}"


def characters(_: Any = None) -> dict[str, Any]:
    """그림이 있는 캐릭터(기본 캐릭터 먼저). 방송에 쓰는 캐릭터 표시."""
    active = character.active().id
    found = []
    for item in character.all_characters():
        picture = _picture(item)
        if picture:
            found.append({"id": item.id, "name": item.name, "kind": item.kind, "picture": picture, "active": item.id == active})
    return {"characters": found, "formats": {key: {"name": name, "width": width, "height": height, "note": note}
                                             for key, (name, width, height, note) in FORMATS.items()}}


def make_feature(context: feature.Context) -> feature.Feature:
    return feature.Feature(name="decor", static={"/decor": "decor.html", "/decor.js": "decor.js"}, get={"/decor/characters": characters})
