"""방송 이미지 만들기(``/decor``): 프사(움짤 포함), 방송국과 채널 배너, 다시보기 썸네일, 시그니처 풍선 그림을 이 PC 브라우저에서 그려 저장.

- 그리기는 브라우저 캔버스(방송 색, 함께 배포한 글꼴). 올린 그림은 브라우저 안에서만 쓰고, 움짤 만들기와 후원 벽 시그니처 등록 때만
  그린 결과(PNG)를 이 PC 서버로 보낸다
- ``/decor/characters``: 그림으로 쓸 수 있는 캐릭터(PNGTuber는 입 다문 그림, 3D는 미리보기 그림)
- ``POST /decor/animate`` (``{"frames": ["data:image/png;base64,..", ...], "delay": 80, "transparent": false}``): 장면 그림들을 GIF 움짤로(Pillow 필요).
  transparent면 반쯤 넘게 투명한 곳을 GIF 투명색으로(시그니처 풍선 그림의 카드 바깥)
"""

from __future__ import annotations

import base64
import binascii
import io
import urllib.parse
from typing import Any

from .. import character
from . import feature

#: 움짤: 장면 수, 한 장 크기, 장면 사이 시간(밀리초) 한도
MAX_FRAMES = 30
MAX_FRAME_BYTES = 1024 * 1024
DELAY_RANGE = (40, 500)
_PNG = "data:image/png;base64,"

#: 만들 수 있는 그림: 키 -> (이름, 가로, 세로, 설명). 규격은 각 플랫폼 안내 기준(바뀌면 여기만 고침)
FORMATS = {
    "profile": ("프사", 1024, 1024, "원형으로 잘려도 보이게 가운데에 캐릭터"),
    "thumbnail": ("다시보기 썸네일", 1280, 720, "YouTube, 치지직, SOOP 다시보기 16:9"),
    "youtube": ("YouTube 채널 배너", 2560, 1440, "모든 기기에 보이는 가운데 1546x423 안에 글자와 캐릭터"),
    "twitch": ("Twitch 프로필 배너", 1200, 480, "채널 위쪽 배너"),
    "soop": ("SOOP 방송국 배너", 720, 150, "JPEG 200KB 이하로 저장"),
    "signature": ("시그니처 풍선 그림", 512, 512, "후원 벽의 시그니처 칸 그림. 금액, 이름, 캐릭터(바깥은 투명)"),
    "cheki": ("체키", 1080, 1350, "폴라로이드 사진: 가로 1080, 세로는 사진 비율에 따라. 아래 여백에 손글씨 문구"),
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


def animate(data: dict[str, Any]) -> dict[str, Any]:
    """브라우저가 그린 장면 PNG들을 GIF 움짤로(되풀이). ``transparent`` 면 알파 128 미만을 투명색(색표의 마지막 칸)으로."""
    try:
        from PIL import Image
    except ImportError:
        raise feature.FeatureError('움짤 만들기에는 Pillow 필요: pip install "debutkit[logo]"') from None
    frames = data.get("frames")
    if not isinstance(frames, list) or not 2 <= len(frames) <= MAX_FRAMES:
        raise feature.FeatureError(f"장면은 2에서 {MAX_FRAMES}장")
    delay = data.get("delay", 80)
    if isinstance(delay, bool) or not isinstance(delay, int) or not DELAY_RANGE[0] <= delay <= DELAY_RANGE[1]:
        raise feature.FeatureError(f"장면 사이 시간은 {DELAY_RANGE[0]}에서 {DELAY_RANGE[1]}밀리초")
    pictures = []
    for value in frames:
        if not isinstance(value, str) or not value.startswith(_PNG):
            raise feature.FeatureError("장면은 PNG 그림만")
        try:
            raw = base64.b64decode(value[len(_PNG):], validate=True)
        except (binascii.Error, ValueError):
            raise feature.FeatureError("장면 그림 자료가 올바르지 않음") from None
        if len(raw) > MAX_FRAME_BYTES or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise feature.FeatureError("장면 그림은 1MB 이하 PNG")
        with Image.open(io.BytesIO(raw)) as picture:
            if max(picture.size) > 1024:
                raise feature.FeatureError("장면 그림은 한 변 1024px 이하")
            pictures.append(picture.convert("RGBA"))
    transparent = data.get("transparent") is True
    if len({picture.size for picture in pictures}) > 1:
        raise feature.FeatureError("장면 그림의 크기가 모두 같아야 함")
    # 모든 장면을 이어 붙인 그림에서 색표 하나를 뽑아 모든 장면에 써서 색이 깜박이지 않게
    width, height = pictures[0].size
    combined = Image.new("RGB", (width, height * len(pictures)))
    for index, picture in enumerate(pictures):
        combined.paste(picture.convert("RGB"), (0, height * index))
    palette = combined.quantize(colors=255, method=Image.Quantize.MEDIANCUT)  # 0~254번, 255번은 투명색 자리
    out = io.BytesIO()
    quantized = []
    for picture in pictures:
        frame = picture.convert("RGB").quantize(palette=palette, dither=Image.Dither.FLOYDSTEINBERG)
        if transparent:
            frame.paste(255, mask=picture.getchannel("A").point(lambda alpha: 255 if alpha < 128 else 0))
        quantized.append(frame)
    first, *rest = quantized
    extra = {"transparency": 255, "disposal": 2} if transparent else {"disposal": 1}
    first.save(out, "GIF", save_all=True, append_images=rest, duration=delay, loop=0, optimize=False, **extra)
    return {"gif": "data:image/gif;base64," + base64.b64encode(out.getvalue()).decode(), "bytes": out.tell()}


def make_feature(context: feature.Context) -> feature.Feature:
    return feature.Feature(name="decor", static={"/decor": "decor.html", "/decor.js": "decor.js", "/decor-fx.js": "decor-fx.js"},
                           get={"/decor/characters": characters},
                           post={"/decor/animate": animate}, body_limit={"/decor/animate": MAX_FRAMES * MAX_FRAME_BYTES * 4 // 3 + 65536})
