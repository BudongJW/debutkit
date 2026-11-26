"""후원 알림 꾸미기(``/alerts/control``): 방송 스타일, 배치, 위치, 등장, 표시 시간, 크기, 문구, 효과음, 금액 구간별 그림과 강조.

- 설정은 설정 폴더의 ``alerts.json``, 올린 그림은 ``alert-images`` 폴더(이름은 debutkit이 정함, PNG, GIF, WebP, JPEG만, 8 MB 이하)
- ``/alerts/config`` 조회(방송 화면이 읽음), ``POST /alerts/config`` 바꿀 항목만, ``POST /alerts/image`` 그림 올리기(``{"name", "data"}``, base64),
  ``POST /alerts/image/remove`` (``{"id"}``), ``/alerts/image?id=`` 그림 파일. 바뀐 설정은 ``/live?feeds=alerts`` 로 방송 화면에 바로
- 금액 구간: 원 기준 최소 금액마다 그림, 강조 효과, 표시 시간, 효과음. 별풍선 1개 100원(VTube Studio 후원 반응과 같은 환산).
  원으로 바꿀 수 없는 단위(Twitch 비트, 외화, 애드벌룬)는 최소 금액 0 구간만
- 주소 뒤 ``?style=``, ``?layout=``, ``?position=``, ``?seconds=`` 는 이 설정보다 우선(알림 소스를 여러 개 다르게 둘 때)
"""

from __future__ import annotations

import re
import secrets
from typing import Any

from .. import settings
from ..wall import MAX_IMAGE, decode_image
from . import feature, theme

DATA = "alerts.json"
FOLDER = "alert-images"
STYLES = {"auto": "방송 스타일 따르기", **{key: name for key, (name, _) in theme.STYLES.items()}}
LAYOUTS = {"card": "카드", "banner": "가로 띠", "bubble": "말풍선", "big": "큰 글자(바탕 없음)", "side": "그림 옆 글자", "stack": "그림 위, 카드 아래"}
POSITIONS = {"top-left": "왼쪽 위", "top": "위 가운데", "top-right": "오른쪽 위", "left": "왼쪽", "center": "가운데", "right": "오른쪽",
             "bottom-left": "왼쪽 아래", "bottom": "아래 가운데", "bottom-right": "오른쪽 아래"}
ENTERS = {"auto": "방송 스타일 따르기", "stamp": "도장 찍기", "float": "말랑 떠오르기", "flicker": "깜빡 켜지기", "steps": "도트 계단",
          "fade": "서서히", "tape": "테이프 붙이기", "twinkle": "반짝 나타나기", "slide": "옆에서 밀려오기", "wipe": "쓱 지나가며 드러나기",
          "punch": "확 튀어나오기", "flip": "카드 뒤집기", "unveil": "빛나며 나타나기"}
SOUNDS = {"none": "없음", "chime": "차임", "coin": "동전", "fanfare": "팡파르", "pop": "퐁", "bell": "방울"}
EMPHASIS = {"none": "없음", "sparkle": "반짝이", "confetti": "종이 조각", "shake": "흔들림", "glow": "빛 번짐", "bigger": "크게"}
PLACEHOLDERS = ("{name}", "{amount}")
DEFAULTS: dict[str, Any] = {
    "style": "auto", "layout": "card", "position": "top", "enter": "auto", "seconds": 6, "scale": 100,
    "title": "{name} 님, {amount} 후원 감사합니다", "member_title": "{name} 님, 구독해 주셔서 감사합니다", "message": True, "platform": True,
    "sound": "chime", "volume": 70, "member_image": "", "tiers": [], "images": [],
}
SECONDS = (3, 30)
SCALE = (60, 160)
MAX_TIERS = 12
MAX_IMAGES = 30
MAX_TEMPLATE = 80
_ID = re.compile(r"^[0-9a-f]{24}$")


class AlertError(feature.FeatureError):
    pass


def _josa(word: str, with_final: str, without_final: str) -> str:
    """받침이 있으면 앞 조사(은, 이), 없으면 뒤 조사(는, 가)."""
    hangul = [ch for ch in word if "가" <= ch <= "힣"]
    final = bool(hangul) and (ord(hangul[-1]) - 0xAC00) % 28 != 0  # 마지막 한글 글자 기준(괄호, 기호는 건너뜀)
    return word + (with_final if final else without_final)


def _choice(value: Any, options: dict[str, str], label: str) -> str:
    if value not in options:
        raise AlertError(_josa(label, "은", "는") + " " + ", ".join(options) + " 중 하나")
    return str(value)


def _whole(value: Any, low: int, high: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value) or not low <= value <= high:
        raise AlertError(_josa(label, "은", "는") + f" {low}에서 {high} 사이의 정수")
    return int(value)


def check_template(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise AlertError(_josa(label, "이", "가") + " 비어 있음")
    if len(text) > MAX_TEMPLATE:
        raise AlertError(_josa(label, "은", "는") + f" {MAX_TEMPLATE}자 이내")
    unknown = [found for found in re.findall(r"\{[^{}]*\}", text) if found not in PLACEHOLDERS]
    if unknown:
        raise AlertError(f"{label}에 쓸 수 있는 자리는 {{name}}(이름), {{amount}}(금액): {unknown[0]}")
    return text


def _image_id(value: Any, images: list[dict[str, str]]) -> str:
    text = str(value or "")
    if text and not any(image["id"] == text for image in images):
        raise AlertError("없는 그림: 다시 올리기")
    return text


def check_tiers(value: Any, images: list[dict[str, str]]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise AlertError("금액 구간은 목록")
    if len(value) > MAX_TIERS:
        raise AlertError(f"금액 구간은 {MAX_TIERS}개까지")
    found: dict[int, dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, dict):
            raise AlertError("금액 구간 형식이 올바르지 않음")
        minimum = _whole(item.get("min", 0), 0, 100_000_000, "구간 최소 금액(원)")
        if minimum in found:
            raise AlertError(f"같은 금액의 구간이 2개: {minimum:,}원")
        seconds = item.get("seconds", 0) or 0
        found[minimum] = {"min": minimum, "image": _image_id(item.get("image"), images),
                          "emphasis": _choice(item.get("emphasis", "none"), EMPHASIS, "강조 효과"),
                          "seconds": 0 if not seconds else _whole(seconds, *SECONDS, "구간 표시 시간"),
                          "sound": "" if not item.get("sound") else _choice(item.get("sound"), SOUNDS, "구간 효과음")}
    return [found[key] for key in sorted(found, reverse=True)]


def load() -> dict[str, Any]:
    """저장한 설정. 손상된 항목은 기본값."""
    saved = settings.load_data(DATA)
    config = dict(DEFAULTS)
    images = [image for image in saved.get("images") or [] if isinstance(image, dict) and _ID.match(str(image.get("id", "")))
              and image.get("ext") in ("png", "gif", "webp", "jpg")][:MAX_IMAGES]
    config["images"] = [{"id": image["id"], "ext": image["ext"], "name": str(image.get("name") or "그림")[:40]} for image in images]
    try:
        config.update(update({}, {key: value for key, value in saved.items() if key not in ("images",)}, config["images"]))
    except AlertError:
        for key in DEFAULTS:  # 하나씩 살릴 수 있는 항목만
            if key in saved and key != "images":
                try:
                    config.update(update({}, {key: saved[key]}, config["images"]))
                except AlertError:
                    pass
    return config


def update(base: dict[str, Any], data: dict[str, Any], images: list[dict[str, str]]) -> dict[str, Any]:
    """받은 항목만 확인해 바꾼 값. 틀리면 AlertError(한국어 안내)."""
    found = dict(base)
    checks = {"style": lambda v: _choice(v, STYLES, "스타일"), "layout": lambda v: _choice(v, LAYOUTS, "배치"),
              "position": lambda v: _choice(v, POSITIONS, "위치"), "enter": lambda v: _choice(v, ENTERS, "등장"),
              "seconds": lambda v: _whole(v, *SECONDS, "표시 시간(초)"), "scale": lambda v: _whole(v, *SCALE, "크기(%)"),
              "title": lambda v: check_template(v, "후원 문구"), "member_title": lambda v: check_template(v, "구독 문구"),
              "message": bool, "platform": bool, "sound": lambda v: _choice(v, SOUNDS, "효과음"), "volume": lambda v: _whole(v, 0, 100, "소리 크기"),
              "member_image": lambda v: _image_id(v, images), "tiers": lambda v: check_tiers(v, images)}
    for key, check in checks.items():
        if key in data:
            found[key] = check(data[key])
    return found


def folder() -> Any:
    return settings.data_path(FOLDER)


def make_feature(context: feature.Context) -> feature.Feature:
    channel = feature.Channel({"seq": 0, **load()})

    def publish(config: dict[str, Any]) -> dict[str, Any]:
        settings.save_data(DATA, {key: config[key] for key in DEFAULTS})
        current = load()
        channel.publish({"seq": channel.current.get("seq", 0) + 1, **current})
        return current

    def info(_: Any = None) -> dict[str, Any]:
        return {**load(), "choices": {"styles": STYLES, "layouts": LAYOUTS, "positions": POSITIONS, "enters": ENTERS, "sounds": SOUNDS,
                                      "emphasis": EMPHASIS}}

    def save(data: dict[str, Any]) -> dict[str, Any]:
        current = load()
        publish(update(current, data, current["images"]))
        return info()

    def upload(data: dict[str, Any]) -> dict[str, Any]:
        current = load()
        if len(current["images"]) >= MAX_IMAGES:
            raise AlertError(f"그림은 {MAX_IMAGES}개까지: 쓰지 않는 그림을 지운 뒤 올리기")
        try:
            raw, ext = decode_image(data.get("data"))
        except feature.FeatureError as error:
            raise AlertError(str(error)) from None
        image_id = secrets.token_hex(12)
        target = folder()
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{image_id}.{ext}").write_bytes(raw)
        current["images"] = [*current["images"], {"id": image_id, "ext": ext, "name": str(data.get("name") or "그림").strip()[:40] or "그림"}]
        publish(current)
        return {**info(), "uploaded": image_id}

    def remove(data: dict[str, Any]) -> dict[str, Any]:
        current = load()
        image_id = str(data.get("id") or "")
        found = next((image for image in current["images"] if image["id"] == image_id), None)
        if found is None:
            raise AlertError("없는 그림", 404)
        current["images"] = [image for image in current["images"] if image["id"] != image_id]
        current["tiers"] = [{**tier, "image": "" if tier["image"] == image_id else tier["image"]} for tier in current["tiers"]]
        if current["member_image"] == image_id:
            current["member_image"] = ""
        try:
            (folder() / f"{image_id}.{found['ext']}").unlink()
        except OSError:
            pass
        publish(current)
        return info()

    def image(query: feature.Query) -> feature.Raw:
        image_id = query.get("id", [""])[0]
        found = next((item for item in load()["images"] if item["id"] == image_id), None)
        if found is None:
            raise AlertError("없는 그림", 404)
        try:
            body = (folder() / f"{image_id}.{found['ext']}").read_bytes()
        except OSError:
            raise AlertError("그림 파일이 없어짐", 404) from None
        kinds = {"png": "image/png", "gif": "image/gif", "webp": "image/webp", "jpg": "image/jpeg"}
        return feature.Raw(body, kinds[found["ext"]], "default-src 'none'; sandbox")

    return feature.Feature(name="alerts", static={"/alerts/control": "alerts-control.html"}, get={"/alerts/config": info, "/alerts/image": image},
                           post={"/alerts/config": save, "/alerts/image": upload, "/alerts/image/remove": remove}, feeds={"alerts": channel},
                           body_limit={"/alerts/config": 65536, "/alerts/image": MAX_IMAGE * 4 // 3 + 4096})
