"""디스코드 연동 1단계(``/discord/control``): 합방 음성 위젯 꾸미기와 웹훅 알림.

- 음성 위젯: 디스코드 공식 StreamKit 음성 위젯(OBS 브라우저 소스, 이 PC의 디스코드 앱이 켜져 있어야 함)의 주소에 표시 값을 붙이고,
  방송 스타일(모서리, 테두리, 빛, 글꼴)에 맞춘 OBS 사용자 지정 CSS를 만든다. 참여자마다 디스코드 사용자 ID로 평소 그림과 말할 때 그림을 바꾼다.
  그림은 CSS 안에 data: 주소로 넣는다(브라우저의 내부 주소 접근 제한과 무관). debutkit은 디스코드에 접속하지 않음
- 웹훅: 디스코드 채널 설정의 웹훅 주소로 방송 시작(실제 플랫폼 채팅이 처음 오면), 방송 끝 요약(채팅, 후원, 구독 수), 직접 쓴 알림.
  ``@everyone`` 같은 호출은 막음. 웹훅 주소는 이 PC에 암호화 보관(secret.KeyBox), 방송 화면과 기록에는 남기지 않음
- 설정은 설정 폴더의 ``discord.json``, 그림은 ``discord-images`` 폴더
"""

from __future__ import annotations

import base64
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from .. import settings
from ..secret import KeyBox
from ..wall import decode_image
from . import feature, theme
from .events import DEMO_USER

DATA = "discord.json"
FOLDER = "discord-images"
KEYS = "discord-keys.json"
MAX_PEOPLE = 8
MAX_PICTURE = 400 * 1024  # CSS 안에 넣으므로 작게(OBS 사용자 지정 CSS 칸)
_STREAMKIT = re.compile(r"^https://streamkit\.discord\.com/overlay/voice/(\d{5,25})/(\d{5,25})(?:\?.*)?$")
_WEBHOOK = re.compile(r"^https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d{5,25}/[A-Za-z0-9_\-]{20,100}$")
_USER_ID = re.compile(r"^\d{15,22}$")
LAYOUTS = {"column": "세로로 쌓기", "row": "가로로 나란히"}
DEFAULTS: dict[str, Any] = {
    "widget": "", "layout": "column", "size": 72, "names": True, "speaking_only": False, "style": True,
    "people": [], "start": True, "end": True, "start_text": "{name} 방송 시작! {url}", "end_text": "{name} 방송 끝. 함께해 주셔서 고맙습니다",
    "channel_name": "", "channel_url": "",
}
PLATFORMS = ("chzzk", "soop", "twitch", "youtube")


class DiscordError(feature.FeatureError):
    pass


def keys() -> KeyBox:
    return KeyBox(settings.data_path(KEYS), b"debutkit-discord", "debutkit-discord")


def check_widget(url: Any) -> str:
    text = str(url or "").strip()
    if text and not _STREAMKIT.match(text):
        raise DiscordError("음성 위젯 주소는 StreamKit의 https://streamkit.discord.com/overlay/voice/서버/채널 주소")
    return text.split("?")[0]


def load() -> dict[str, Any]:
    saved = settings.load_data(DATA)
    config = {**DEFAULTS, **{key: value for key, value in saved.items() if key in DEFAULTS}}
    config["layout"] = config["layout"] if config["layout"] in LAYOUTS else "column"
    try:
        config["size"] = max(32, min(160, int(config["size"])))
    except (TypeError, ValueError):
        config["size"] = DEFAULTS["size"]
    people = []
    for person in saved.get("people") or []:
        if isinstance(person, dict) and _USER_ID.match(str(person.get("id", ""))):
            people.append({"id": str(person["id"]), "name": str(person.get("name") or "")[:20],
                           "idle": _picture_id(person.get("idle")), "talk": _picture_id(person.get("talk"))})
    config["people"] = people[:MAX_PEOPLE]
    for key in ("names", "speaking_only", "style", "start", "end"):
        config[key] = bool(config[key])
    return config


def _picture_id(value: Any) -> str:
    text = str(value or "")
    return text if re.fullmatch(r"[0-9a-f]{24}\.(png|gif|webp|jpg)", text) else ""


def save(config: dict[str, Any]) -> None:
    settings.save_data(DATA, {key: config[key] for key in DEFAULTS})


def picture_data(name: str) -> str:
    """CSS 안에 넣을 data: 주소."""
    if not name:
        return ""
    try:
        raw = (settings.data_path(FOLDER) / name).read_bytes()
    except OSError:
        return ""
    kind = {"png": "image/png", "gif": "image/gif", "webp": "image/webp", "jpg": "image/jpeg"}[name.rsplit(".", 1)[1]]
    return f"data:{kind};base64,{base64.b64encode(raw).decode('ascii')}"


def widget_url(config: dict[str, Any]) -> str:
    """StreamKit 주소에 표시 값. 말하는 사람만 보이기는 주소 값이 OBS에서 무시되는 일이 있어 CSS로 한다."""
    if not config["widget"]:
        return ""
    return config["widget"] + "?icon=true&online=true&logo=white&text_color=%23ffffff&text_size=14&bg_opacity=0&bg_shadow_size=0&invite_code=&limit_speaking=false&small_avatars=false&hide_names=false"


def css(config: dict[str, Any], tokens: dict[str, str] | None = None) -> str:
    """OBS 브라우저 소스의 사용자 지정 CSS. 디스코드가 클래스 이름 뒤 글자를 바꿔도 맞도록 부분 일치 선택자와 옛 이름을 함께."""
    tokens = tokens or theme.tokens()
    size = config["size"]
    avatar = '[class*="Voice_avatar"], img.avatar, .voice-state img'
    speaking = '[class*="Voice_avatarSpeaking"], img.avatar.speaking, .voice-state .speaking'
    name = '[class*="Voice_name"], .voice-state .name, .voice-state .user'
    state = '[class*="Voice_voiceState_"], [class*="Voice_voiceState__"], li.voice-state'
    states = '[class*="Voice_voiceStates"], ul.voice-states'
    lines = [
        "/* debutkit 디스코드 음성 위젯 꾸미기(OBS 브라우저 소스의 사용자 지정 CSS). 다시 만들려면 debutkit 디스코드 화면 */",
        "body { background-color: rgba(0, 0, 0, 0) !important; margin: 0; overflow: hidden; }",
        f"{states} {{ display: flex !important; flex-direction: {'row' if config['layout'] == 'row' else 'column'}; gap: 10px; padding: 8px !important; }}",
        f"{state} {{ display: flex !important; align-items: center; gap: 10px; height: auto !important; margin: 0 !important; }}",
        f"{avatar} {{ width: {size}px !important; height: {size}px !important; border-radius: 50% !important; object-fit: cover;"
        " transition: transform 0.15s ease, filter 0.2s ease, border-color 0.2s; border: 3px solid transparent !important; }",
        f"{speaking} {{ border-color: {tokens['primary']} !important; transform: translateY(-4px) scale(1.05); }}",
    ]
    if config["speaking_only"]:  # OBS(Chromium 103)에 :has가 없어 그림과 그 뒤 이름 칸을 흐리게, 말하는 그림과 그 뒤만 밝게
        user = '[class*="Voice_user"], .voice-state .user'
        lines.append(f"{avatar}, {user} {{ opacity: 0.3; transition: opacity 0.2s; }}")
        lines.append('[class*="Voice_avatarSpeaking"], [class*="Voice_avatarSpeaking"] ~ *, .speaking, .speaking ~ * { opacity: 1 !important; }')
    if not config["names"]:
        lines.append(f"{name} {{ display: none !important; }}")
    elif config["style"]:
        radius = tokens.get("radius", "10px")
        lines.append(f"{name} {{ background: {tokens['surface']} !important; color: {tokens['on-surface']} !important; border: {tokens['line-width']} "
                     f"{tokens['line-style']} {tokens['line']} !important; border-radius: {radius} !important; padding: 4px 10px !important;"
                     f" font-family: {tokens['display']} !important; font-size: 18px !important; text-shadow: {tokens['glow']} !important;"
                     f" box-shadow: {tokens['shadow']} !important; }}")
    for person in config["people"]:
        idle, talk = picture_data(person["idle"]), picture_data(person["talk"])
        selector = f'img[src*="/avatars/{person["id"]}/"]'
        if idle:
            lines.append(f"{selector} {{ content: url({idle}); border-radius: 0 !important; object-fit: contain; border: 0 !important; }}")
        if talk:
            lines.append(f'{selector}[class*="Speaking"], {selector}.speaking {{ content: url({talk}); }}')
        elif idle:
            lines.append(f'{selector}[class*="Speaking"], {selector}.speaking {{ filter: drop-shadow(0 0 8px {tokens["primary"]}); }}')
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ 웹훅


def check_webhook(url: Any) -> str:
    text = str(url or "").strip()
    if not _WEBHOOK.match(text):
        raise DiscordError("웹훅 주소는 디스코드 채널 설정, 연동, 웹후크에서 복사한 https://discord.com/api/webhooks/... 주소")
    return text


def post_webhook(url: str, content: str, *, opener: Callable[..., Any] | None = None) -> None:
    """메시지 하나. 호출(@everyone, @here, 역할, 사람)은 막는다. 429면 알려 준 시간만큼 한 번 기다렸다 다시."""
    body = json.dumps({"content": content[:1900], "username": "debutkit", "allowed_mentions": {"parse": []}}).encode("utf-8")
    opener = opener or urllib.request.urlopen
    for attempt in range(2):
        request = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json", "User-Agent": "debutkit"})
        try:
            with opener(request, timeout=10) as response:
                response.read()
            return
        except urllib.error.HTTPError as error:
            if error.code == 429 and attempt == 0:
                try:
                    wait = float(json.loads(error.read().decode("utf-8") or "{}").get("retry_after", 1))
                except ValueError:
                    wait = 1.0
                time.sleep(min(5.0, max(0.5, wait)))
                continue
            if error.code in (401, 404):
                raise DiscordError("웹훅이 지워졌거나 주소가 틀림: 디스코드에서 웹훅을 다시 만들어 붙여 넣기") from None
            raise DiscordError(f"디스코드 응답 오류 {error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise DiscordError(f"디스코드에 연결하지 못함: {getattr(error, 'reason', error)}") from None


def fill(template: str, config: dict[str, Any], **extra: str) -> str:
    values = {"name": config["channel_name"] or "방송", "url": config["channel_url"], **extra}
    return re.sub(r"\{(name|url|summary)\}", lambda found: values.get(found.group(1), ""), template).strip()


class Webhook:
    """방송 시작과 끝 알림. 실제 플랫폼 채팅이나 후원이 처음 오면 시작, 오버레이를 멈추면 끝(그 사이 수를 요약)."""

    def __init__(self, *, poster: Callable[[str, str], None] | None = None) -> None:
        self.poster = poster or post_webhook
        self.started = False
        self.counts = {"chat": 0, "donation": 0, "member": 0}
        self.won = 0.0
        self.error = ""

    def url(self) -> str:
        return keys().load("webhook") or ""

    def _send(self, text: str) -> None:
        url = self.url()
        if not url or not text:
            return
        try:
            self.poster(url, text)
            self.error = ""
        except DiscordError as error:
            self.error = str(error)

    def tap(self, event: Any) -> None:
        if event.platform not in PLATFORMS or getattr(event, "user", "") == DEMO_USER or event.kind not in self.counts:
            return
        self.counts[event.kind] += 1
        if event.kind == "donation":
            self.won += event.amount * (100 if event.unit == "별풍선" else 1 if event.unit == "원" else 0)
        if not self.started:
            self.started = True
            config = load()
            if config["start"]:
                threading.Thread(target=self._send, args=(fill(config["start_text"], config),), daemon=True).start()

    def summary(self) -> str:
        parts = [f"채팅 {self.counts['chat']:,}개", f"후원 {self.counts['donation']:,}번"]
        if self.won:
            parts.append(f"약 {round(self.won):,}원(별풍선 1개 100원)")
        if self.counts["member"]:
            parts.append(f"구독 {self.counts['member']:,}번")
        return ", ".join(parts)

    def stop(self) -> None:
        config = load()
        if self.started and config["end"]:
            self._send(f"{fill(config['end_text'], config)}\n{self.summary()}")


def make_feature(context: feature.Context, *, poster: Callable[[str, str], None] | None = None) -> feature.Feature:
    hook = Webhook(poster=poster)

    def info(_: Any = None) -> dict[str, Any]:
        config = load()
        return {**config, "layouts": LAYOUTS, "obs_url": widget_url(config), "css": css(config),
                "webhook_saved": bool(hook.url()), "webhook_error": hook.error, "started": hook.started, "summary": hook.summary()}

    def update(data: dict[str, Any]) -> dict[str, Any]:
        config = load()
        if "widget" in data:
            config["widget"] = check_widget(data["widget"])
        if "layout" in data:
            if data["layout"] not in LAYOUTS:
                raise DiscordError("배치는 세로로 쌓기, 가로로 나란히 중 하나")
            config["layout"] = data["layout"]
        if "size" in data:
            size = data["size"]
            if isinstance(size, bool) or not isinstance(size, (int, float)) or not 32 <= size <= 160:
                raise DiscordError("그림 크기는 32에서 160 사이")
            config["size"] = int(size)
        for key in ("names", "speaking_only", "style", "start", "end"):
            if key in data:
                config[key] = bool(data[key])
        for key, limit in (("start_text", 300), ("end_text", 300), ("channel_name", 40), ("channel_url", 300)):
            if key in data:
                text = str(data[key] or "").strip()
                if len(text) > limit:
                    raise DiscordError(f"{limit}자 이내")
                if key == "channel_url" and text and not text.startswith("https://"):
                    raise DiscordError("방송 주소는 https:// 로 시작")
                config[key] = text
        save(config)
        return info()

    def person(data: dict[str, Any]) -> dict[str, Any]:
        """참여자 추가와 바꾸기: {"id", "name", "idle": data URL, "talk": data URL}. 그림은 400 KB 이하."""
        config = load()
        user_id = str(data.get("id") or "").strip()
        if not _USER_ID.match(user_id):
            raise DiscordError("디스코드 사용자 ID는 숫자 15~22자리(디스코드 설정의 고급에서 개발자 모드를 켜고 이름을 오른쪽 클릭, 사용자 ID 복사)")
        entry = next((item for item in config["people"] if item["id"] == user_id), None)
        if entry is None:
            if len(config["people"]) >= MAX_PEOPLE:
                raise DiscordError(f"참여자는 {MAX_PEOPLE}명까지")
            entry = {"id": user_id, "name": "", "idle": "", "talk": ""}
            config["people"].append(entry)
        entry["name"] = str(data.get("name") or entry["name"]).strip()[:20]
        folder = settings.data_path(FOLDER)
        for slot in ("idle", "talk"):
            if data.get(slot):
                try:
                    raw, ext = decode_image(data[slot])
                except feature.FeatureError as error:
                    raise DiscordError(str(error)) from None
                if len(raw) > MAX_PICTURE:
                    raise DiscordError("참여자 그림은 400 KB 이하(OBS 사용자 지정 CSS에 넣기 때문, 512x512 이하 PNG나 WebP 권장)")
                folder.mkdir(parents=True, exist_ok=True)
                if entry[slot]:
                    (folder / entry[slot]).unlink(missing_ok=True)
                entry[slot] = f"{secrets.token_hex(12)}.{ext}"
                (folder / entry[slot]).write_bytes(raw)
        save(config)
        return info()

    def remove(data: dict[str, Any]) -> dict[str, Any]:
        config = load()
        user_id = str(data.get("id") or "")
        for item in [item for item in config["people"] if item["id"] == user_id]:
            for slot in ("idle", "talk"):
                if item[slot]:
                    (settings.data_path(FOLDER) / item[slot]).unlink(missing_ok=True)
        config["people"] = [item for item in config["people"] if item["id"] != user_id]
        save(config)
        return info()

    def webhook(data: dict[str, Any]) -> dict[str, Any]:
        box = keys()
        if data.get("clear"):
            box.clear("webhook")
        else:
            box.save("webhook", check_webhook(data.get("url")))
        return info()

    def send(data: dict[str, Any]) -> dict[str, Any]:
        url = hook.url()
        if not url:
            raise DiscordError("웹훅 주소를 먼저 저장")
        text = str(data.get("text") or "").strip() or "debutkit 시험 알림: 이 채널로 방송 알림을 보냅니다"
        post_webhook(url, text[:1900]) if poster is None else poster(url, text[:1900])
        return {"ok": True}

    def css_text(_: Any) -> feature.Raw:
        return feature.Raw(css(load()).encode("utf-8"), "text/css; charset=utf-8")

    return feature.Feature(
        name="discord", static={"/discord/control": "discord-control.html"},
        get={"/discord/config": info, "/discord/widget.css": css_text},
        post={"/discord/config": update, "/discord/person": person, "/discord/person/remove": remove, "/discord/webhook": webhook,
              "/discord/send": send},
        taps=[hook.tap], stop=hook.stop, body_limit={"/discord/person": 2 * MAX_PICTURE + 8192})
