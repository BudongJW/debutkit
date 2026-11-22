"""오버레이 서버: OBS 브라우저 소스가 여는 이 PC 안의 작은 웹 서버.

- ``/``        설정 화면: OBS에 붙일 주소, 미리보기, 테스트 메시지 버튼
- ``/chat``    통합 채팅창 (주소 뒤 ``?theme=bubble&max=12&font=22`` 로 모양 조절)
- ``/alerts``  후원, 구독 알림
- ``/events``  화면들이 받는 사건 흐름 (Server-Sent Events)
- ``/character`` 캐릭터 화면(PNGTuber, VRM). ``?id=캐릭터`` 로 지정, 없으면 방송에 사용할 캐릭터
- ``/voice``   캐릭터 화면이 받는 말하기 상태 (Server-Sent Events)
- ``POST /test`` 설정 화면의 테스트 메시지, ``POST /voice/test`` 말하기 시험

127.0.0.1에만 열리고, 다른 웹사이트가 이 서버에 요청을 끼워 넣지 못하도록 Host와
Origin을 확인한다. 받은 채팅은 저장하지 않고 최근 몇십 개만 메모리에 둔다.
"""

from __future__ import annotations

import json
import queue
import re
import threading
import time
import urllib.parse
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any, Callable, Iterable

from .events import OverlayEvent, system_event
from .voice import VoiceState

STATIC = {"/": "index.html", "/chat": "chat.html", "/alerts": "alerts.html", "/overlay.css": "overlay.css", "/overlay.js": "overlay.js",
          "/favicon.svg": "favicon.svg", "/character": "character.html", "/character.js": "character.js"}
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml",
         ".png": "image/png", ".jpg": "image/jpeg", ".json": "application/json", ".vrm": "model/gltf-binary", ".txt": "text/plain; charset=utf-8"}
_SAFE_PATH = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$")


def _vendor(path: str) -> bytes | None:
    """``/vendor/`` 아래 함께 배포한 라이브러리(three.js, three-vrm)."""
    relative = path.removeprefix("/vendor/")
    if not _SAFE_PATH.match(relative) or ".." in relative.split("/"):
        return None
    target = resources.files("debutkit.overlay").joinpath("static", "vendor", *relative.split("/"))
    return target.read_bytes() if target.is_file() else None


def character_info(character: Any) -> dict[str, Any]:
    base = f"/character/files/{urllib.parse.quote(character.id)}/"
    return {"id": character.id, "name": character.name, "kind": character.kind, "renders": character.renders_in_overlay,
            "files": {role: base + name for role, name in character.files.items()}, "thumbnail": base + character.thumbnail if character.thumbnail else ""}


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


def make_handler(hub: Hub, port_of: Callable[[], int], *, keepalive: float = 15.0, voice: VoiceState | None = None) -> type[BaseHTTPRequestHandler]:
    voice = voice or VoiceState()

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

        def _send(self, status: int, body: bytes, content_type: str = "text/plain; charset=utf-8") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
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
                return self._voice()
            if path == "/status":
                return self._send(HTTPStatus.OK, json.dumps({"listeners": hub.listeners}).encode(), "application/json")
            if path == "/character/info":
                return self._character_info(urllib.parse.parse_qs(query).get("id", [""])[0])
            if path.startswith("/character/files/"):
                return self._character_file(path.removeprefix("/character/files/"))
            if path.startswith("/vendor/"):
                body = _vendor(path)
                if body is None:
                    return self._send(HTTPStatus.NOT_FOUND, b"not found")
                return self._send(HTTPStatus.OK, body, TYPES.get("." + path.rsplit(".", 1)[-1], "application/octet-stream"))
            name = STATIC.get(path)
            if name is None:
                return self._send(HTTPStatus.NOT_FOUND, b"not found")
            self._send(HTTPStatus.OK, _static(name), TYPES["." + name.rsplit(".", 1)[1]])

        def do_POST(self) -> None:  # noqa: N802
            if not self._local():
                return self._send(HTTPStatus.FORBIDDEN, b"forbidden")
            path = self.path.split("?", 1)[0]
            if path not in ("/test", "/voice/test"):
                return self._send(HTTPStatus.NOT_FOUND, b"not found")
            length = min(int(self.headers.get("Content-Length") or 0), 4096)
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                data = {}
            if path == "/voice/test":
                voice.test(bool(data.get("talking", True)))
                return self._send(HTTPStatus.OK, b"ok")
            kind = "donation" if data.get("kind") == "donation" else "chat"
            role = "owner" if data.get("role") == "owner" else ""  # 스트리머 표시 명령(!clip) 시험용
            event = OverlayEvent("demo", kind, "테스트", (("text", str(data.get("text") or "테스트 메시지입니다")[:200]),),
                                 amount=1000.0 if kind == "donation" else 0.0, unit="원" if kind == "donation" else "", role=role)
            hub.publish(event)
            self._send(HTTPStatus.OK, b"ok")

        def _events(self) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            subscriber, backlog = hub.subscribe()
            try:
                for event in backlog:
                    self._write_event(event, replay=True)
                while True:
                    try:
                        event = subscriber.get(timeout=keepalive)
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        continue
                    self._write_event(event)
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

            character_id, _, relative = urllib.parse.unquote(rest).partition("/")
            found = character.get(character_id)
            target = character.file_path(found, relative) if found and _SAFE_PATH.match(relative) else None
            if target is None:
                return self._send(HTTPStatus.NOT_FOUND, b"not found")
            self._send(HTTPStatus.OK, target.read_bytes(), TYPES.get(target.suffix.lower(), "application/octet-stream"))

        def _voice(self) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            subscriber, current = voice.subscribe()
            try:
                self.wfile.write(b"data: " + json.dumps(current).encode() + b"\n\n")
                self.wfile.flush()
                while True:
                    try:
                        state = subscriber.get(timeout=keepalive)
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        continue
                    self.wfile.write(b"data: " + json.dumps(state, ensure_ascii=False).encode() + b"\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            finally:
                voice.unsubscribe(subscriber)

        def _write_event(self, event: OverlayEvent, *, replay: bool = False) -> None:
            data = event.to_dict()
            data["replay"] = replay
            self.wfile.write(b"data: " + json.dumps(data, ensure_ascii=False).encode("utf-8") + b"\n\n")
            self.wfile.flush()

    return Handler


class OverlayServer:
    """서버와 채팅 수신 스레드들. ``start`` 후 ``url`` 로 접속, ``stop`` 으로 정리."""

    def __init__(self, sources: Iterable[tuple[str, Callable[[], Any]]] = (), *, port: int = 8790, poll: float = 0.2, retry: float = 10.0) -> None:
        self.hub = Hub()
        self.voice = VoiceState()
        self._sources = list(sources)
        self._poll = poll
        self._retry = retry
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._attached: list[Any] = []
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(self.hub, lambda: self.port, voice=self.voice))
        self.httpd.daemon_threads = True

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
        return self

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
