"""오버레이 서버: OBS 브라우저 소스가 여는 이 PC 안의 작은 웹 서버.

- ``/``        설정 화면: OBS에 붙일 주소, 미리보기, 테스트 메시지 버튼
- ``/chat``    통합 채팅창 (주소 뒤 ``?theme=bubble&max=12&font=22`` 로 모양 조절)
- ``/alerts``  후원, 구독 알림
- ``/events``  화면들이 받는 사건 흐름 (Server-Sent Events)
- ``/character`` 캐릭터 화면(PNGTuber, VRM, GLB, FBX). ``?id=캐릭터`` 로 지정, 없으면 방송에 사용할 캐릭터
- ``/live``    캐릭터 화면, 설정 화면이 받는 말하기 상태, 얼굴 추적 값, 동작 실행 요청 (Server-Sent Events 하나, ``/voice`` 와 ``/tracking`` 은 각각)
- ``/motion/list`` 등록한 동작(VRMA, FBX, GLB)과 기본 동작. ``POST /motion`` 으로 동작 실행(``{"id": 동작}``, 멈춤은 ``{"stop": true}``)
- ``/draw``     후원 추첨 연출(평소 투명). ``/draw/control`` 조작 화면(설정, 시험 추첨, 최근 결과. OBS 독으로도 사용)
  ``/draw/config``, ``/draw/history`` 조회, ``POST /draw/config`` 저장, ``POST /draw/test`` 시험 추첨, ``POST /draw/clear`` 최근 결과 비우기.
  ``/draw/script`` 대본 창(큰 글씨), ``/draw/log`` 기록 창(별도 창이나 OBS 독)
- ``/raffle``   시청자 참여 추첨 상태와 명단. ``POST /raffle/start``, ``/raffle/stop``, ``/raffle/clear``, ``/raffle/add``, ``/raffle/remove``,
  ``/raffle/draw`` (``{"count": 3, "mode": "pick"}`` 또는 ``{"mode": "order"}``)
- ``/live?feeds=voice,tracking,motion,draw,raffle`` 처럼 받을 항목을 고를 수 있다(기본은 draw, raffle 제외)
- 스트리머, 매니저 채팅 명령(commands.py): ``!동작``, ``!단축키``, ``!모집``, ``!마감``, ``!추첨``, ``!순서``
- ``/tracker`` 얼굴 추적 화면(일반 브라우저에서 열고 카메라 허용). ``POST /tracking`` 으로 값을 보낸다
- ``/phone`` 휴대폰 얼굴 추적 설정 화면(phone.py, iFacialMocap과 VTube Studio 아이폰 앱). ``/phone/status`` 상태,
  ``POST /phone/start`` (``{"app": "ifacialmocap", "ip": "192.168.0.12"}``), ``/phone/stop``, ``/phone/options``, ``/phone/calibrate``.
  휴대폰 값을 받는 중에는 웹캠 추적 화면의 값을 쓰지 않는다
- ``/camera`` 휴대폰 카메라 영상 연결 정보(camera.py: PC 주소, 포트, 암호, Larix 가져오기 주소), ``/camera/qr.svg?address=`` QR 코드,
  ``/camera/status`` OBS 소스 상태. ``POST /camera/obs`` OBS 소스 만들기, ``POST /camera/config`` 포트, 지연 여유, 새 암호.
  OBS 작업은 오버레이를 시작한 명령줄이나 설정 마법사가 알려 준 OBS 연결 정보(``obs_target``)를 사용
- ``/camera/view`` debutkit 휴대폰 앱의 카메라 영상(WebRTC) 수신 화면(OBS 브라우저 소스, camcall.py). ``/live?feeds=camera`` 연결 제안,
  ``POST /camera/answer`` 응답, ``/camera/call`` 통화 상태. ``POST /camera/obs`` 에 ``{"kind": "app"}`` 이면 이 화면의 브라우저 소스
- ``/remote/admin`` 휴대폰 조작 화면(remote.py) 관리: 켜기, 끄기, QR(``/remote/admin/qr.svg?id=``), 승인, 삭제.
  휴대폰 조작 화면 자체는 이 서버가 아닌 별도 창구(내부 네트워크 주소, 기본 8792번)에서 연다
- ``/program`` 송출 화면(OBS 없이 바로 방송, broadcast.py): 캐릭터, 채팅, 알림, 추첨, 휴대폰 카메라(앱)를 한 화면에. ``POST /program/size`` 창 안 화면 크기
- ``/broadcast`` 방송 상태, ``/broadcast/control`` 방송 조작 화면, ``/broadcast/devices`` 소리 장치와 인코더.
  ``POST /broadcast/config``, ``/broadcast/key`` (``{"key": 키}`` 또는 ``{"clear": true}``), ``/broadcast/window``, ``/broadcast/start``, ``/broadcast/stop``
- ``/logo`` 방송 로고 만들기 화면(logo.py), ``/logo/status`` 상태(AI Horde 백그라운드 작업 포함), ``/logo/icons`` 아이콘 목록,
  ``/logo/symbol.svg?id=`` 또는 ``?icon=&style=&colors=&primary=&accent=`` 또는 ``?template=&primary=&accent=`` (``&finish=`` 마감) 심볼 미리보기.
  ``POST /logo/key`` (``{"provider", "key"}`` 또는 ``{"provider", "clear": true}``), ``/logo/generate`` AI 심볼 생성(사용자 키는 요금 발생,
  AI Horde는 바로 작업 상태를 돌려주고 백그라운드로 기다림), ``/logo/cancel`` 백그라운드 작업 취소, ``/logo/make`` 로고 SVG,
  ``/logo/record`` 저장한 로고 기록(심볼 출처와 라이선스)
- ``POST /test`` 설정 화면의 테스트 메시지, ``POST /voice/test`` 말하기 시험
- 그 밖의 방송 연출 기능(뽑기판, 후원 벽, 참여 레이스 등)은 feature.py의 ``Feature`` 로 등록한 주소(``default_features``)

127.0.0.1에만 열리고, 다른 웹사이트가 이 서버에 요청을 끼워 넣지 못하도록 Host와
Origin을 확인한다. 받은 채팅은 저장하지 않고 최근 몇십 개만 메모리에 둔다.
휴대폰 얼굴 추적의 수신 창구(UDP)는 사용자가 켠 경우에만, 휴대폰과 연결된 네트워크 주소 하나에 열고 지정한 휴대폰의 값만 받는다.
"""

from __future__ import annotations

import json
import queue
import re
import shutil
import socket
import sys
import threading
import time
import urllib.parse
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any, Callable, Iterable

from .. import broadcast as broadcasts
from .. import camera as cameras
from .. import commands, logo_icons
from .. import draw as drawing
from .. import logo as logos
from .. import motion as motions
from .. import raffle as raffles
from . import camcall
from . import feature as features_
from . import phone as phones
from . import remote as remotes
from .events import OverlayEvent, system_event
from .tracking import TrackingState, clean
from .voice import VoiceState

STATIC = {"/": "index.html", "/chat": "chat.html", "/alerts": "alerts.html", "/overlay.css": "overlay.css", "/overlay.js": "overlay.js",
          "/favicon.svg": "favicon.svg", "/character": "character.html", "/character.js": "character.js", "/tracker": "tracker.html", "/tracker.js": "tracker.js",
          "/draw": "draw.html", "/draw.js": "draw.js", "/draw-props.js": "draw-props.js", "/draw.css": "draw.css", "/draw/control": "draw-control.html",
          "/draw/script": "draw-script.html", "/draw/log": "draw-log.html", "/phone": "phone.html",
          "/camera/view": "camera-view.html", "/camera-view.js": "camera-view.js", "/program": "program.html", "/broadcast/control": "broadcast.html", "/logo": "logo.html"}
#: 외부에서 받은 SVG를 직접 열 때도 스크립트, 외부 연결이 동작하지 않게(logo.py에서 이미 정리)
SVG_POLICY = "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:"
#: /live 로 받을 수 있는 항목(등록한 기능의 항목 추가). feeds를 지정하지 않으면 DEFAULT_FEEDS.
#: events 는 /events 와 같은 채팅, 후원 사건(처음 값은 최근 사건 목록). 화면들이 공유 연결(live-worker.js) 하나로 모든 항목을 받게 한다
LIVE_FEEDS = ("voice", "tracking", "motion", "draw", "raffle", "camera", "events")
DEFAULT_FEEDS = ("voice", "tracking", "motion")
#: 요청 본문 최대 크기(추첨 설정은 상품표가 길 수 있음)
BODY_LIMIT = {"/draw/config": 32768, "/camera/answer": 32768}
#: 이 서버가 직접 처리하는 POST 주소(등록한 기능의 주소는 Feature.post)
POST_PATHS = ("/test", "/voice/test", "/tracking", "/motion", "/draw/config", "/draw/test", "/draw/clear", "/raffle/start", "/raffle/stop",
              "/raffle/clear", "/raffle/add", "/raffle/remove", "/raffle/draw", "/phone/start", "/phone/stop", "/phone/options",
              "/phone/calibrate", "/camera/obs", "/camera/config", "/remote/admin/start",
              "/remote/admin/stop", "/remote/admin/pair", "/remote/admin/approve", "/remote/admin/remove", "/camera/answer",
              "/camera/ended", "/program/size", "/broadcast/config", "/broadcast/key", "/broadcast/window", "/broadcast/start",
              "/broadcast/stop", "/logo/key", "/logo/generate", "/logo/cancel", "/logo/make", "/logo/record")
#: 얼굴 추적 화면은 이 서버 밖으로 접속하지 못하게 한다(함께 배포한 MediaPipe의 사용 기록 전송 차단, 카메라 영상 외부 전송 방지)
TRACKER_POLICY = ("default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self'; img-src 'self' blob: data:; "
                  "media-src 'self' blob: mediastream:; style-src 'self' 'unsafe-inline'; worker-src 'self' blob:; frame-ancestors 'none'")
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml",
         ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".json": "application/json",
         ".vrm": "model/gltf-binary", ".glb": "model/gltf-binary", ".vrma": "model/gltf-binary", ".fbx": "application/octet-stream", ".txt": "text/plain; charset=utf-8",
         ".mjs": "text/javascript; charset=utf-8", ".wasm": "application/wasm", ".task": "application/octet-stream", ".woff2": "font/woff2"}
_SAFE_PATH = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$")


def _vendor(path: str) -> bytes | None:
    """``/vendor/`` 아래 함께 배포한 라이브러리(three.js, three-vrm)."""
    relative = path.removeprefix("/vendor/")
    if not _SAFE_PATH.match(relative) or ".." in relative.split("/"):
        return None
    target = resources.files("debutkit.overlay").joinpath("static", "vendor", *relative.split("/"))
    return target.read_bytes() if target.is_file() else None


def character_info(character: Any) -> dict[str, Any]:
    """캐릭터 화면이 받는 정보. ID와 파일 이름은 주소에 쓸 수 있게 바꾼다(한글, 공백, # 등)."""
    base = f"/character/files/{urllib.parse.quote(character.id)}/"
    return {"id": character.id, "name": character.name, "kind": character.kind, "renders": character.renders_in_overlay,
            "files": {role: base + urllib.parse.quote(name) for role, name in character.files.items()},
            "thumbnail": base + urllib.parse.quote(character.thumbnail) if character.thumbnail else ""}


class Hub:
    """사건을 모든 화면(구독자)에게 나눠 준다. 새로 열린 화면은 최근 사건부터 받는다."""

    def __init__(self, history: int = 30) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[queue.Queue[OverlayEvent]] = []
        self.history: deque[OverlayEvent] = deque(maxlen=history)
        #: 화면 말고도 사건을 받을 함수들 (자동 클립 등). 오래 걸리면 안 된다
        self.taps: list[Callable[[OverlayEvent], None]] = []

    def publish(self, event: OverlayEvent) -> None:
        with self._lock:
            self.history.append(event)
            for subscriber in self._subscribers:
                try:
                    subscriber.put_nowait(event)
                except queue.Full:  # 멈춘 화면 때문에 서버가 막히지 않도록 버린다
                    pass
        for tap in list(self.taps):
            try:
                tap(event)
            except Exception:
                pass

    def subscribe(self) -> tuple[queue.Queue[OverlayEvent], list[OverlayEvent]]:
        subscriber: queue.Queue[OverlayEvent] = queue.Queue(maxsize=500)
        with self._lock:
            self._subscribers.append(subscriber)
            return subscriber, list(self.history)

    def unsubscribe(self, subscriber: queue.Queue[OverlayEvent]) -> None:
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)

    @property
    def listeners(self) -> int:
        with self._lock:
            return len(self._subscribers)


def _static(name: str) -> bytes:
    return resources.files("debutkit.overlay").joinpath("static", name).read_bytes()


def make_handler(hub: Hub, port_of: Callable[[], int], *, keepalive: float = 15.0, voice: VoiceState | None = None,
                 tracking: TrackingState | None = None, motion: motions.MotionState | None = None, draw: drawing.DrawState | None = None,
                 raffle: raffles.Raffle | None = None, phone: phones.PhoneTracker | None = None,
                 obs_target: Callable[[], tuple[str, int, str | None] | None] | None = None, remote: remotes.RemoteControl | None = None,
                 call: camcall.CameraCall | None = None, program: broadcasts.ProgramState | None = None,
                 broadcaster: broadcasts.Broadcaster | None = None, studio: logos.LogoStudio | None = None,
                 stopping: threading.Event | None = None, features: Iterable[features_.Feature] = ()) -> type[BaseHTTPRequestHandler]:
    """``stopping`` 이 설정되면 열린 사건 흐름을 모두 끝낸다(화면은 새 서버에 다시 연결).

    ``features`` 는 등록할 방송 연출 기능(feature.py). 주소나 실시간 항목 이름이 겹치면 ValueError.
    """
    voice = voice or VoiceState()
    tracking = tracking or TrackingState()
    motion = motion or motions.MotionState()
    draw = draw or drawing.DrawState()
    raffle = raffle or raffles.Raffle()
    phone = phone or phones.PhoneTracker(tracking)
    obs_target = obs_target or (lambda: None)
    call = call or (remote.call if remote is not None else camcall.CameraCall())
    remote = remote or remotes.RemoteControl(raffle, motion, draw, call=call)
    program = program or (broadcaster.program if broadcaster is not None else broadcasts.ProgramState())
    broadcaster = broadcaster or broadcasts.Broadcaster(program, port_of)
    studio_box: list[logos.LogoStudio | None] = [studio]  # 로고 화면을 처음 쓸 때 만든다(저장한 생성 기록 읽기)

    def logo_studio() -> logos.LogoStudio:
        if studio_box[0] is None:
            studio_box[0] = logos.LogoStudio()
        return studio_box[0]

    states: dict[str, Any] = {"voice": voice, "tracking": tracking, "motion": motion, "draw": draw, "raffle": raffle, "camera": call,
                              "events": _HubFeed(hub)}
    feature_static: dict[str, str] = {}
    feature_get: dict[str, Callable[[Any], Any]] = {}
    feature_post: dict[str, Callable[[Any], Any]] = {}
    body_limit: dict[str, int] = dict(BODY_LIMIT)
    for part in features:
        for table, values, taken in ((feature_static, part.static, STATIC), (feature_get, part.get, STATIC), (feature_post, part.post, POST_PATHS)):
            for path, value in values.items():
                if path in taken or (table is feature_post and path in feature_post) or (table is not feature_post and (path in feature_get or path in feature_static)):
                    raise ValueError(f"주소가 겹침: {path} ({part.name})")
                table[path] = value
        for name, state in part.feeds.items():
            if name in states:
                raise ValueError(f"실시간 항목 이름이 겹침: {name} ({part.name})")
            states[name] = state
        body_limit.update(part.body_limit)
    live_feeds = tuple(states)
    stopping = stopping or threading.Event()
    step = min(0.5, keepalive)

    class Handler(BaseHTTPRequestHandler):
        server_version = "debutkit-overlay"

        def log_message(self, format: str, *args: Any) -> None:  # 조용히
            pass

        def _local(self) -> bool:
            port = port_of()
            allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if self.headers.get("Host", "") not in allowed:  # DNS 리바인딩 차단
                return False
            origin = self.headers.get("Origin")
            return origin is None or origin in {f"http://{host}" for host in allowed}

        def _send(self, status: int, body: bytes, content_type: str = "text/plain; charset=utf-8", policy: str = "") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            if policy:
                self.send_header("Content-Security-Policy", policy)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if not self._local():
                return self._send(HTTPStatus.FORBIDDEN, b"forbidden")
            path, _, query = self.path.partition("?")
            if path == "/events":
                return self._events()
            if path == "/voice":
                return self._stream(voice)
            if path == "/tracking":
                return self._stream(tracking)
            if path == "/live":
                wanted = urllib.parse.parse_qs(query).get("feeds", [""])[0].split(",")
                return self._feeds({name: states[name] for name in live_feeds if name in wanted} or {name: states[name] for name in DEFAULT_FEEDS})
            if path == "/status":
                return self._send(HTTPStatus.OK, json.dumps({"listeners": hub.listeners}).encode(), "application/json")
            if path in feature_get:
                return self._feature(feature_get[path], urllib.parse.parse_qs(query))
            if path == "/character/humanoid.json":  # GLB, FBX의 뼈와 표정 이름 표(humanoid.py)
                from .. import humanoid

                return self._send(HTTPStatus.OK, json.dumps(humanoid.table(), ensure_ascii=False).encode(), "application/json")
            if path == "/character/info":
                return self._character_info(urllib.parse.parse_qs(query).get("id", [""])[0])
            if path.startswith("/character/files/"):
                return self._character_file(path.removeprefix("/character/files/"))
            if path == "/draw/config":
                return self._json(drawing.load_config().to_dict())
            if path == "/draw/history":
                return self._json({"results": draw.recent()})
            if path == "/raffle":
                return self._json(raffle.status())
            if path == "/phone/status":
                return self._json(phone.status())
            if path == "/camera":
                return self._json({**cameras.connection_info(), "obs": obs_target() is not None})
            if path == "/camera/qr.svg":
                address = urllib.parse.parse_qs(query).get("address", [""])[0]
                if address not in cameras.lan_addresses():  # 이 PC의 주소로 만든 연결 정보만 QR로
                    return self._send(HTTPStatus.NOT_FOUND, b"unknown address")
                body = cameras.qr_svg(cameras.larix_link(address, cameras.load_config())).encode()
                return self._send(HTTPStatus.OK, body, TYPES[".svg"])
            if path == "/camera/status":
                return self._camera_obs(lambda client: cameras.media_state(client))
            if path == "/remote/admin":
                return self._json(remote.status())
            if path == "/camera/call":
                return self._json(call.status())
            if path == "/broadcast":
                return self._json(broadcaster.status())
            if path == "/broadcast/devices":  # 처음에는 시험 인코딩으로 몇 초 걸림
                return self._json(broadcaster.devices())
            if path == "/logo/status":
                return self._json(logo_studio().status())
            if path == "/logo/icons":
                return self._json(logo_icons.catalog())
            if path == "/logo/symbol.svg":
                return self._logo_symbol(urllib.parse.parse_qs(query))
            if path == "/remote/admin/qr.svg":
                try:
                    url = remote.pair_url(urllib.parse.parse_qs(query).get("id", [""])[0])
                except remotes.RemoteError:
                    return self._send(HTTPStatus.NOT_FOUND, b"expired")
                return self._send(HTTPStatus.OK, cameras.qr_svg(url).encode(), TYPES[".svg"])
            if path == "/motion/list":
                return self._send(HTTPStatus.OK, json.dumps(motions.overview(), ensure_ascii=False).encode(), "application/json")
            if path.startswith("/motion/files/"):
                return self._motion_file(path.removeprefix("/motion/files/"))
            if path.startswith("/vendor/"):
                body = _vendor(path)
                if body is None:
                    return self._send(HTTPStatus.NOT_FOUND, b"not found")
                return self._send(HTTPStatus.OK, body, TYPES.get("." + path.rsplit(".", 1)[-1], "application/octet-stream"))
            name = STATIC.get(path) or feature_static.get(path)
            if name is None:
                return self._send(HTTPStatus.NOT_FOUND, b"not found")
            self._send(HTTPStatus.OK, _static(name), TYPES["." + name.rsplit(".", 1)[1]], TRACKER_POLICY if path.startswith("/tracker") else "")

        def do_POST(self) -> None:  # noqa: N802
            # 응답 전에 요청 본문을 먼저 읽는다(읽지 않고 닫으면 Windows에서 연결이 끊겨 거부 응답이 전달되지 않음)
            path = self.path.split("?", 1)[0]
            try:
                length = min(int(self.headers.get("Content-Length") or 0), body_limit.get(path, 4096))
            except ValueError:
                return self._send(HTTPStatus.BAD_REQUEST, b"bad length")
            body = self.rfile.read(length) if length > 0 else b""
            if not self._local():
                return self._send(HTTPStatus.FORBIDDEN, b"forbidden")
            if path not in POST_PATHS and path not in feature_post:
                return self._send(HTTPStatus.NOT_FOUND, b"not found")
            try:
                raw = json.loads(body or b"{}")
            except ValueError:
                raw = {}
            data = raw if isinstance(raw, dict) else {}
            if path in feature_post:
                return self._feature(feature_post[path], data)
            if path == "/voice/test":
                voice.test(bool(data.get("talking", True)))
                return self._send(HTTPStatus.OK, b"ok")
            if path.startswith("/draw/"):
                return self._draw_post(path, raw, data)
            if path.startswith("/raffle/"):
                return self._raffle_post(path, data)
            if path.startswith("/phone/"):
                return self._phone_post(path, data)
            if path == "/camera/obs":
                chosen = data.get("scenes")
                names = [str(name) for name in chosen] if isinstance(chosen, list) else []
                if data.get("kind") == "app":  # debutkit 휴대폰 앱 영상(WebRTC) 수신 화면
                    return self._camera_obs(lambda client: {**cameras.add_app_to_obs(client, port_of(), names), **call.status()})
                return self._camera_obs(lambda client: {**cameras.add_to_obs(client, cameras.load_config(), names), **cameras.media_state(client)})
            if path == "/camera/ended":  # 수신 화면: 연결이 오래 끊김
                return self._json({"stopped": call.stop(str(data.get("id") or ""))})
            if path == "/camera/answer":
                try:
                    accepted = call.answer(str(data.get("id") or ""), data.get("sdp"), [remote.address, *cameras.lan_addresses()])
                except camcall.CallError as error:
                    return self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
                if not accepted:
                    return self._json({"error": "이미 다른 화면이 연결했거나 끝난 통화"}, HTTPStatus.CONFLICT)
                return self._json({"accepted": True})
            if path == "/camera/config":
                return self._camera_config(data)
            if path == "/program/size":
                return self._json({"ok": program.update(data)})
            if path.startswith("/broadcast/"):
                return self._broadcast_post(path, data)
            if path.startswith("/logo/"):
                return self._logo_post(path, data)
            if path.startswith("/remote/admin/"):
                return self._remote_admin(path, data)
            if path == "/motion":
                if data.get("stop"):
                    motion.play(stop=True)
                    return self._send(HTTPStatus.OK, b"ok")
                found = motions.get(str(data.get("id") or ""))
                if found is None:
                    return self._send(HTTPStatus.NOT_FOUND, json.dumps({"error": "등록한 동작 없음"}, ensure_ascii=False).encode(), "application/json")
                motion.play(found.id)
                return self._send(HTTPStatus.OK, json.dumps({"play": found.id, "name": found.name}, ensure_ascii=False).encode(), "application/json")
            if path == "/tracking":
                values = clean(raw)
                if values is None:
                    return self._send(HTTPStatus.BAD_REQUEST, b"bad tracking data")
                if phone.receiving() or remote.receiving():  # 휴대폰 추적(앱 포함)이 우선
                    return self._send(HTTPStatus.OK, b"phone")
                tracking.publish({**values, "source": "webcam"})
                return self._send(HTTPStatus.OK, b"ok")
            kind = "donation" if data.get("kind") == "donation" else "chat"
            role = "owner" if data.get("role") == "owner" else ""  # 스트리머 표시 명령(!clip) 시험용
            event = OverlayEvent("demo", kind, "테스트", (("text", str(data.get("text") or "테스트 메시지입니다")[:200]),),
                                 amount=1000.0 if kind == "donation" else 0.0, unit="원" if kind == "donation" else "", role=role)
            hub.publish(event)
            self._send(HTTPStatus.OK, b"ok")

        def _json(self, value: Any, status: int = HTTPStatus.OK) -> None:
            self._send(status, json.dumps(value, ensure_ascii=False).encode(), "application/json")

        def _feature(self, handler: Callable[[Any], Any], argument: Any) -> None:
            """등록한 기능의 조회, 조작. 잘못된 요청은 기능이 정한 상태(기본 400)와 한국어 안내, 저장 실패는 500."""
            try:
                value = handler(argument)
            except features_.FeatureError as error:
                return self._json({"error": str(error)}, error.status)
            except OSError as error:
                return self._json({"error": f"저장 실패: {error}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            if isinstance(value, features_.Raw):
                return self._send(HTTPStatus.OK, value.body, value.content_type, value.policy)
            return self._json(value)

        def _draw_post(self, path: str, raw: Any, data: dict[str, Any]) -> None:
            """추첨 설정 저장, 시험 추첨(저장한 설정, 사용 꺼짐이어도 실행), 최근 결과 비우기."""
            if path == "/draw/clear":
                draw.clear()
                return self._json({"ok": True})
            if path == "/draw/config":
                try:
                    config = drawing.save_config(drawing.from_request(raw))
                except drawing.DrawError as error:
                    return self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
                except OSError as error:
                    return self._json({"error": f"설정 저장 실패: {error}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
                return self._json(config.to_dict())
            config = drawing.load_config()
            amount = data.get("amount", 1000)
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not 0 <= amount <= drawing.MAX_WON:
                return self._json({"error": "시험 금액은 0 이상의 숫자(원)"}, HTTPStatus.BAD_REQUEST)
            count = drawing.draws_for(config, "donation", float(amount), "원")
            if not count:
                if config.exact:
                    hint = "규칙 금액(" + ", ".join(f"{rule.min_won:,}원" for rule in reversed(config.rules)) + ") 중 하나로 시험"
                else:
                    hint = f"{config.rules[-1].min_won:,}원 이상으로 시험"
                return self._json({"error": f"추첨 규칙에 맞지 않는 금액: {hint}"}, HTTPStatus.BAD_REQUEST)
            return self._json(draw.run(config, name="시험", platform="demo", kind="donation", amount=float(amount), unit="원", count=count, test=True))

        def _raffle_post(self, path: str, data: dict[str, Any]) -> None:
            """참여 추첨 조작. 잘못된 요청은 400과 한국어 안내."""
            try:
                if path == "/raffle/start":
                    return self._json(raffle.start(data.get("keyword"), data.get("title"), data.get("donation_min", "keep")))
                if path == "/raffle/stop":
                    return self._json(raffle.stop())
                if path == "/raffle/clear":
                    return self._json(raffle.clear())
                if path == "/raffle/add":
                    if not raffle.add(str(data.get("name") or ""), "manual", "manual"):
                        raise raffles.RaffleError("추가하지 못함: 이름이 비었거나 이미 참가했거나 명단이 가득 참")
                    return self._json(raffle.status())
                if path == "/raffle/remove":
                    raffle.remove(str(data.get("key") or ""))
                    return self._json(raffle.status())
                return self._json(raffle.draw(data.get("count", 1), str(data.get("mode") or "pick")))
            except raffles.RaffleError as error:
                return self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            except OSError as error:
                return self._json({"error": f"설정 저장 실패: {error}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def _phone_post(self, path: str, data: dict[str, Any]) -> None:
            """휴대폰 얼굴 추적 시작, 멈춤, 선택 변경, 정면 맞추기. 잘못된 요청은 400과 한국어 안내."""

            def flag(name: str) -> bool | None:
                return data[name] if isinstance(data.get(name), bool) else None

            try:
                if path == "/phone/start":
                    return self._json(phone.start(data.get("app"), data.get("ip"), flag("mirror"), flag("flip_pitch")))
                if path == "/phone/stop":
                    return self._json(phone.stop())
                if path == "/phone/options":
                    return self._json(phone.options(flag("mirror"), flag("flip_pitch")))
                return self._json(phone.calibrate(reset=data.get("reset") is True))
            except phones.PhoneError as error:
                return self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            except OSError as error:
                return self._json({"error": f"설정 저장 실패: {error}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def _camera_obs(self, work: Callable[[Any], dict[str, Any]]) -> None:
            """OBS에 연결해 휴대폰 카메라 소스 작업. OBS 연결 정보가 없거나 실패하면 400, 502와 한국어 안내."""
            target = obs_target()
            if target is None:
                return self._json({"error": "OBS 연결 정보 없음: 설정 마법사나 debutkit overlay로 오버레이를 시작하거나 debutkit camera setup 사용"},
                                  HTTPStatus.BAD_REQUEST)
            try:
                with cameras.connect(*target) as client:
                    return self._json(work(client))
            except cameras.CameraError as error:
                return self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            except Exception as error:  # OBS 꺼짐, 비밀번호 오류 등
                return self._json({"error": cameras.obs_failure(error)}, HTTPStatus.BAD_GATEWAY)

        def _remote_admin(self, path: str, data: dict[str, Any]) -> None:
            """휴대폰 조작 화면 켜기, 끄기, 새 QR, 승인, 삭제. 잘못된 요청은 400과 한국어 안내."""
            try:
                if path == "/remote/admin/start":
                    return self._json(remote.start(data.get("address"), data.get("port")))
                if path == "/remote/admin/stop":
                    remote.stop()
                    return self._json(remote.status())
                if path == "/remote/admin/pair":
                    return self._json(remote.pair())
                if path == "/remote/admin/approve":
                    return self._json(remote.approve(str(data.get("id") or "")))
                return self._json(remote.remove(str(data.get("id") or "")))
            except remotes.RemoteError as error:
                return self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            except OSError as error:
                return self._json({"error": f"설정 저장 실패: {error}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def _logo_post(self, path: str, data: dict[str, Any]) -> None:
            """로고 만들기: API 키 저장과 삭제, AI 심볼 생성(오래 걸림, AI Horde는 백그라운드), 작업 취소, 로고 SVG, 로고 기록.
            잘못된 요청은 400과 한국어 안내."""
            try:
                studio = logo_studio()
                if path == "/logo/key":
                    return self._json(studio.set_key(data.get("provider"), None if data.get("clear") is True else data.get("key")))
                if path == "/logo/generate":
                    request = (data.get("provider"), data.get("quality"), data.get("description"), data.get("style"), data.get("colors"),
                               data.get("address"))
                    if data.get("provider") in logos.BACKGROUND_PROVIDERS:
                        return self._json({"job": studio.start(*request)})
                    return self._json({"symbol": studio.generate(*request)})
                if path == "/logo/cancel":
                    return self._json(studio.cancel())
                if path == "/logo/record":
                    return self._json({"record": studio.record(data)})
                return self._json({"svg": studio.make(data)})
            except logos.LogoError as error:
                return self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            except OSError as error:
                return self._json({"error": f"저장 실패: {error}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def _logo_symbol(self, query: dict[str, list[str]]) -> None:
            """심볼 미리보기 SVG(그림으로만 표시, 스크립트 차단)."""
            def value(name: str, default: str = "") -> str:
                return query.get(name, [default])[0]

            try:
                if value("id") and logo_studio().symbol(value("id")) is None:
                    return self._send(HTTPStatus.NOT_FOUND, b"not found")
                body = logo_studio().preview({name: values[0] for name, values in query.items() if values})
            except logos.LogoError:
                return self._send(HTTPStatus.BAD_REQUEST, b"bad symbol")
            self._send(HTTPStatus.OK, body.encode("utf-8"), TYPES[".svg"], SVG_POLICY)

        def _broadcast_post(self, path: str, data: dict[str, Any]) -> None:
            """OBS 없이 방송: 설정, 스트림 키, 송출 화면 창, 시작, 멈춤. 잘못된 요청은 400과 한국어 안내."""
            try:
                if path == "/broadcast/config":
                    return self._json(broadcaster.update_config(data))
                if path == "/broadcast/key":
                    return self._json(broadcaster.set_key(None if data.get("clear") is True else data.get("key"), data.get("platform")))
                if path == "/broadcast/window":
                    return self._json(broadcaster.open_window())
                if path == "/broadcast/start":
                    return self._json(broadcaster.start())
                return self._json(broadcaster.stop(close_window=data.get("close") is True))
            except broadcasts.BroadcastError as error:
                return self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            except OSError as error:
                return self._json({"error": f"저장 실패: {error}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def _camera_config(self, data: dict[str, Any]) -> None:
            """포트, 지연 여유, 새 암호 저장. OBS에 소스가 있으면 그 설정도 바꾼다(연결 정보가 있을 때)."""
            try:
                config = cameras.update_config(data.get("port"), data.get("latency"), data.get("new_passphrase") is True)
            except cameras.CameraError as error:
                return self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            except OSError as error:
                return self._json({"error": f"설정 저장 실패: {error}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            answer: dict[str, Any] = {**cameras.connection_info(config), "obs": obs_target() is not None}
            target = obs_target()
            if target is not None:
                try:
                    with cameras.connect(*target) as client:
                        if cameras.media_state(client)["exists"]:
                            client.request("SetInputSettings", {"inputName": cameras.SOURCE_NAME, "inputSettings": cameras.source_settings(config),
                                                                "overlay": True})
                            answer["obs_updated"] = True
                except Exception as error:
                    answer["obs_error"] = cameras.obs_failure(error)
            return self._json(answer)

        def _open_stream(self) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def _follow(self, subscriber: queue.Queue[Any], write: Callable[[Any], None]) -> None:
            """서버가 멈출 때까지 새 값을 보낸다. 조용하면 ``keepalive`` 초마다 ping(끊긴 연결 확인)."""
            quiet = 0.0
            while not stopping.is_set():
                try:
                    item = subscriber.get(timeout=step)
                except queue.Empty:
                    quiet += step
                    if quiet >= keepalive:
                        quiet = 0.0
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                    continue
                quiet = 0.0
                write(item)

        def _events(self) -> None:
            self._open_stream()
            subscriber, backlog = hub.subscribe()
            try:
                for event in backlog:
                    self._write_event(event, replay=True)
                self._follow(subscriber, self._write_event)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            finally:
                hub.unsubscribe(subscriber)

        def _character_info(self, character_id: str) -> None:
            from .. import character

            found = character.get(character_id) if character_id else character.active()
            if found is None:
                return self._send(HTTPStatus.NOT_FOUND, json.dumps({"error": "캐릭터 없음"}, ensure_ascii=False).encode(), "application/json")
            self._send(HTTPStatus.OK, json.dumps(character_info(found), ensure_ascii=False).encode(), "application/json")

        def _character_file(self, rest: str) -> None:
            from .. import character

            # 파일 이름은 character.json에 등록한 이름과 정확히 같아야 하고 캐릭터 폴더 안이어야 한다(character.file_path)
            character_id, _, relative = urllib.parse.unquote(rest).partition("/")
            found = character.get(character_id)
            self._file(character.file_path(found, relative) if found and "\\" not in relative else None)

        def _motion_file(self, rest: str) -> None:
            motion_id, _, relative = urllib.parse.unquote(rest).partition("/")
            found = motions.get(motion_id)
            self._file(motions.file_path(found, relative) if found and "\\" not in relative else None)

        def _file(self, target: Any) -> None:
            if target is None:
                return self._send(HTTPStatus.NOT_FOUND, b"not found")
            self.send_response(HTTPStatus.OK)  # VRM은 수백 MB일 수 있어 나눠 보낸다
            self.send_header("Content-Type", TYPES.get(target.suffix.lower(), "application/octet-stream"))
            self.send_header("Content-Length", str(target.stat().st_size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            try:
                with target.open("rb") as source:
                    shutil.copyfileobj(source, self.wfile, 1024 * 1024)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def _stream(self, state: Any) -> None:
            """말하기 상태 또는 추적 값 하나의 Server-Sent Events. 연결하면 현재 값부터 보낸다."""
            self._feeds({"": state})

        def _feeds(self, feeds: dict[str, Any]) -> None:
            """상태들의 새 값을 연결 하나로. 이름이 있으면 ``event:`` 줄을 붙인다.

            ``/live`` 는 말하기 상태(voice), 추적 값(tracking), 동작 실행 요청(motion), 추첨 결과(draw) 중 고른 항목을 보낸다.
            브라우저는 같은 주소에 동시 연결을 6개까지만 열기 때문에(OBS 브라우저 소스끼리도 공유) 화면 하나가 연결을 여러 개 쓰지 않도록 한다.
            """
            self._open_stream()
            merged: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue(maxsize=320)
            joined: dict[str, Any] = {}

            def write(item: tuple[str, dict[str, Any]]) -> None:
                name, data = item
                head = f"event: {name}\n".encode() if name else b""
                self.wfile.write(head + b"data: " + json.dumps(data, ensure_ascii=False).encode() + b"\n\n")
                self.wfile.flush()

            try:
                for name, feed in feeds.items():
                    joined[name], current = feed.subscribe(_Tagged(merged, name))
                    write((name, current))
                self._follow(merged, write)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            finally:
                for name, subscriber in joined.items():
                    feeds[name].unsubscribe(subscriber)

        def _write_event(self, event: OverlayEvent, *, replay: bool = False) -> None:
            data = event.to_dict()
            data["replay"] = replay
            self.wfile.write(b"data: " + json.dumps(data, ensure_ascii=False).encode("utf-8") + b"\n\n")
            self.wfile.flush()

    return Handler


class _HubFeed:
    """허브의 사건(채팅, 후원, 구독, 안내)을 /live 의 events 항목으로. 처음 값은 최근 사건 목록(``replay`` 표시), 그 뒤로는 사건 하나씩."""

    def __init__(self, hub: Hub) -> None:
        self.hub = hub

    def subscribe(self, into: Any) -> tuple[Any, dict[str, Any]]:
        tap = _EventTap(into)
        with self.hub._lock:
            self.hub._subscribers.append(tap)  # type: ignore[arg-type]
            history = list(self.hub.history)
        return tap, {"history": [{**event.to_dict(), "replay": True} for event in history]}

    def unsubscribe(self, tap: Any) -> None:
        self.hub.unsubscribe(tap)


class _EventTap:
    def __init__(self, into: Any) -> None:
        self.into = into

    def put_nowait(self, event: OverlayEvent) -> None:
        self.into.put_nowait({**event.to_dict(), "replay": False})


class _Tagged:
    """여러 상태의 새 값을 대기열 하나로 모은다: 값마다 이름을 붙여 ``(이름, 값)`` 으로 넣는다."""

    def __init__(self, target: queue.Queue[tuple[str, dict[str, Any]]], name: str) -> None:
        self.target, self.name = target, name

    def put_nowait(self, item: dict[str, Any]) -> None:
        self.target.put_nowait((self.name, item))


class _PhoneStopper:
    """서버를 멈출 때 휴대폰 수신도 멈춘다(저장한 사용 여부는 그대로: 다음 실행에도 시작)."""

    def __init__(self, phone: phones.PhoneTracker) -> None:
        self.phone = phone

    def stop(self) -> None:
        self.phone.stop(save=False)


class _RemoteStopper:
    """서버를 멈출 때 휴대폰 조작 화면도 닫는다(저장한 사용 여부는 그대로)."""

    def __init__(self, remote: remotes.RemoteControl) -> None:
        self.remote = remote

    def stop(self) -> None:
        self.remote.stop(save=False)


class _FeatureStopper:
    """서버를 멈출 때 등록한 기능의 정리 함수를 부른다."""

    def __init__(self, stop: Callable[[], None]) -> None:
        self._stop = stop

    def stop(self) -> None:
        self._stop()


class _BroadcastStopper:
    """서버를 멈출 때 송출도 끝내고 송출 화면 창을 닫는다(창의 페이지가 이 서버를 쓰므로)."""

    def __init__(self, broadcaster: broadcasts.Broadcaster) -> None:
        self.broadcaster = broadcaster

    def stop(self) -> None:
        self.broadcaster.stop(close_window=True)


class _HttpServer(ThreadingHTTPServer):
    """Windows에서는 같은 포트를 다른 프로그램(다른 debutkit 포함)이 함께 열지 못하게 한다.

    기본값(SO_REUSEADDR)으로는 Windows가 두 번째 서버도 같은 포트에 열어 주고, OBS가 어느 쪽에 연결될지 알 수 없다.
    """

    daemon_threads = True

    def server_bind(self) -> None:
        if sys.platform == "win32":
            self.allow_reuse_address = False
            self.socket.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_EXCLUSIVEADDRUSE", -5), 1)
        super().server_bind()


class OverlayServer:
    """서버와 채팅 수신 스레드들. ``start`` 후 ``url`` 로 접속, ``stop`` 으로 정리."""

    def __init__(self, sources: Iterable[tuple[str, Callable[[], Any]]] = (), *, port: int = 8790, poll: float = 0.2, retry: float = 10.0,
                 chat_commands: bool | None = None) -> None:
        """``chat_commands`` 가 None이면 저장 설정(기본 켬)을 사건마다 확인."""
        self.hub = Hub()
        self.voice = VoiceState()
        self.tracking = TrackingState()
        self.motion = motions.MotionState()
        self.draw = drawing.DrawState()
        self.hub.taps.append(drawing.DrawReactor(self.draw))  # 후원 추첨(저장 설정에서 사용을 켠 경우만)
        self.raffle = raffles.Raffle()
        self.hub.taps.append(raffles.RaffleReactor(self.raffle))  # 참여 추첨 모집 중 참가 명령, 후원 참가
        self.commands = commands.ChatCommands(motion_state=self.motion, raffle_state=self.raffle, enabled=chat_commands,
                                              notify=lambda text: self.hub.publish(system_event(text)))
        self.hub.taps.append(self.commands)  # 스트리머, 매니저 채팅 명령
        self.phone = phones.PhoneTracker(self.tracking)  # 휴대폰 얼굴 추적(켠 경우만 수신 창구를 연다)
        self.obs_target: tuple[str, int, str | None] | None = None  # OBS 연결 정보(휴대폰 카메라 소스 만들기). 명령줄, 설정 마법사가 지정
        self.camera_call = camcall.CameraCall()  # 휴대폰 앱의 카메라 영상(WebRTC) 연결 중계
        self.remote = remotes.RemoteControl(self.raffle, self.motion, self.draw, notify=lambda text: self.hub.publish(system_event(text)),
                                            tracking=self.tracking, phone=self.phone, call=self.camera_call)
        self.program = broadcasts.ProgramState()  # 송출 화면 창 크기(OBS 없이 바로 방송)
        self.broadcast = broadcasts.Broadcaster(self.program, lambda: self.port, notify=lambda text: self.hub.publish(system_event(text)))
        self.logo = logos.LogoStudio()  # 방송 로고 만들기(API 키, 생성 기록)
        #: 방송 연출 기능(feature.py의 default_features: 뽑기판, 후원 벽, 참여 레이스 등)
        self.features = features_.default_features(features_.Context(notify=lambda text: self.hub.publish(system_event(text)),
                                                                     publish=self.hub.publish, raffle=self.raffle,
                                                                     draw=self.draw, tracking=self.tracking, port_of=lambda: self.port,
                                                                     obs=lambda: self.obs_target))
        for part in self.features:
            self.hub.taps.extend(part.taps)
        self._sources = list(sources)
        self._poll = poll
        self._retry = retry
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._attached: list[Any] = []
        self.httpd = _HttpServer(("127.0.0.1", port), make_handler(self.hub, lambda: self.port, voice=self.voice, tracking=self.tracking,
                                                                   motion=self.motion, draw=self.draw, raffle=self.raffle, phone=self.phone,
                                                                   obs_target=lambda: self.obs_target, remote=self.remote, call=self.camera_call,
                                                                   program=self.program, broadcaster=self.broadcast, studio=self.logo,
                                                                   stopping=self._stop, features=self.features))
        self._attached.append(self.commands)  # 단축키 실행 스레드 정리
        self._attached.append(_PhoneStopper(self.phone))
        self._attached.append(_RemoteStopper(self.remote))
        self._attached.append(_BroadcastStopper(self.broadcast))
        self._attached.append(self.logo)  # 로고 만들기의 AI Horde 대기 취소
        self._attached.extend(_FeatureStopper(part.stop) for part in self.features if part.stop is not None)

    @property
    def port(self) -> int:
        return int(self.httpd.server_address[1])

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _pump(self, label: str, factory: Callable[[], Any]) -> None:
        """수신기 하나를 계속 읽는다. 끊기면 ``retry`` 초 뒤 새로 만든다."""
        while not self._stop.is_set():
            try:
                source = factory()
            except Exception as error:  # 잘못된 주소, stream2clip 없음 ...
                self.hub.publish(system_event(f"{label}: {error}"))
                return
            self.hub.publish(system_event(f"{label} 연결 시도"))
            try:
                while not self._stop.is_set() and not getattr(source, "ended", False):
                    for event in source.read():
                        if isinstance(event, OverlayEvent):
                            self.hub.publish(event)
                    self._stop.wait(self._poll)
            except Exception as error:
                self.hub.publish(system_event(f"{label} 연결 끊김: {error}. {self._retry:.0f}초 후 재연결"))
            finally:
                try:
                    source.close()
                except Exception:
                    pass
            self._stop.wait(self._retry)

    def start(self) -> "OverlayServer":
        serve = threading.Thread(target=self.httpd.serve_forever, name="overlay-http", daemon=True)
        serve.start()
        self._threads.append(serve)
        for label, factory in self._sources:
            pump = threading.Thread(target=self._pump, args=(label, factory), name=f"overlay-{label}", daemon=True)
            pump.start()
            self._threads.append(pump)
        self.start_phone()
        self.remote.start_saved()
        return self

    def start_phone(self, options: dict[str, Any] | None = None) -> bool:
        """저장 설정에서 켠 휴대폰 얼굴 추적을 시작(실패는 오버레이 상태 메시지로). ``options`` 로 이번 실행만 지정(저장 안 함)."""
        chosen = options if options is not None else phones.saved_options()
        if not chosen.get("enabled") or not chosen.get("ip"):
            return False
        try:
            self.phone.start(chosen.get("app"), chosen.get("ip"), chosen.get("mirror"), chosen.get("flip_pitch"), save=options is None)
        except phones.PhoneError as error:
            self.hub.publish(system_event(f"휴대폰 얼굴 추적: {error}"))
            return False
        app = phones.APPS[self.phone.app].split("(")[0]
        self.hub.publish(system_event(f"휴대폰 얼굴 추적: {app}, 휴대폰 {self.phone.ip}에 송신 요청"))
        return True

    def attach(self, part: Any) -> Any:
        """서버와 함께 멈출 부품(자동 클립 등). ``stop()`` 을 가진 객체."""
        self._attached.append(part)
        return part

    def stop(self) -> None:
        """멈추고 포트를 닫는다. ``start`` 전에 불러도 된다(시작 전 ``shutdown`` 은 영원히 기다리므로 건너뜀)."""
        self._stop.set()
        for part in self._attached:
            try:
                part.stop()
            except Exception:
                pass
        if self._threads:
            self.httpd.shutdown()
        self.httpd.server_close()

    def serve_until_interrupted(self) -> None:
        self.start()
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
