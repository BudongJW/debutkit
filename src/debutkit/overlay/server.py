"""오버레이 서버: OBS 브라우저 소스가 여는 이 PC 안의 작은 웹 서버.

- ``/``        설정 화면: OBS에 붙일 주소, 미리보기, 테스트 메시지 버튼
- ``/chat``    통합 채팅창 (주소 뒤 ``?theme=bubble&max=12&font=22`` 로 모양 조절)
- ``/alerts``  후원·구독 알림
- ``/events``  화면들이 받는 사건 흐름 (Server-Sent Events)
- ``POST /test`` 설정 화면의 테스트 메시지

127.0.0.1에만 열리고, 다른 웹사이트가 이 서버에 요청을 끼워 넣지 못하도록 Host와
Origin을 확인한다. 받은 채팅은 저장하지 않고 최근 몇십 개만 메모리에 둔다.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Any, Callable, Iterable

from .events import OverlayEvent, system_event

STATIC = {"/": "index.html", "/chat": "chat.html", "/alerts": "alerts.html", "/overlay.css": "overlay.css", "/overlay.js": "overlay.js"}
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}


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


def make_handler(hub: Hub, port_of: Callable[[], int], *, keepalive: float = 15.0) -> type[BaseHTTPRequestHandler]:
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
            path = self.path.split("?", 1)[0]
            if path == "/events":
                return self._events()
            if path == "/status":
                return self._send(HTTPStatus.OK, json.dumps({"listeners": hub.listeners}).encode(), "application/json")
            name = STATIC.get(path)
            if name is None:
                return self._send(HTTPStatus.NOT_FOUND, b"not found")
            self._send(HTTPStatus.OK, _static(name), TYPES["." + name.rsplit(".", 1)[1]])

        def do_POST(self) -> None:  # noqa: N802
            if not self._local():
                return self._send(HTTPStatus.FORBIDDEN, b"forbidden")
            if self.path.split("?", 1)[0] != "/test":
                return self._send(HTTPStatus.NOT_FOUND, b"not found")
            length = min(int(self.headers.get("Content-Length") or 0), 4096)
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                data = {}
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
        self._sources = list(sources)
        self._poll = poll
        self._retry = retry
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._attached: list[Any] = []
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(self.hub, lambda: self.port))
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
                self.hub.publish(system_event(f"{label} 끊김: {error}. {self._retry:.0f}초 뒤 다시 연결"))
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
        self._stop.set()
        for part in self._attached:
            try:
                part.stop()
            except Exception:
                pass
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
