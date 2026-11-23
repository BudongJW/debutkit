"""휴대폰 조작 화면: 같은 Wi-Fi의 휴대폰 브라우저로 시청자 참여 추첨, 3D 캐릭터 동작을 조작하고 후원 추첨 결과를 확인한다.

보안
- 기본 꺼짐. 켜면 이 PC의 내부 네트워크 주소 하나(선택)와 별도 포트(기본 8792)에만 연다. 127.0.0.1 서버(OBS 화면, 설정 화면)는 그대로
- 연결은 PC 화면의 QR 코드로만 시작. QR 주소의 # 뒤(브라우저가 서버로 보내지 않는 부분)에 기기 번호와 기기 비밀값이 있고, 비밀값은 네트워크로 오가지 않는다
- 휴대폰은 요청마다 비밀값으로 서명(HMAC-SHA256: 방식, 경로, 시각, 일회용 값, 본문 해시). 서버는 시각 차이 2분 이내, 일회용 값 재사용 거부,
  서명 실패가 잦은 주소 일시 차단
- 처음 연결한 휴대폰은 PC 화면에서 승인해야 사용(휴대폰과 PC에 같은 4자리 확인 번호). QR이 방송 화면에 노출되어도 승인 없이는 조작 불가
- QR은 5분 안에 쓰지 않으면 만료. 등록 기기는 최대 5대, PC 화면에서 삭제하면 즉시 차단. 기기 비밀값은 설정 폴더의 remote-devices.json에만 보관
- 내용 암호화는 하지 않는다(HTTP). 같은 Wi-Fi의 다른 기기가 조작 화면 내용(방송에 나오는 추첨 명단 등)을 볼 수는 있으나 조작은 할 수 없다
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any, Callable

from .. import camera, settings
from .. import motion as motions
from .. import raffle as raffles

DEFAULT_PORT = 8792
PAIR_SECONDS = 300  # QR 유효 시간
MAX_DEVICES = 5
SKEW = 120  # 휴대폰과 PC 시각 차이 허용(초)
FAIL_LIMIT = 10  # 이 횟수만큼 서명 실패하면(1분 안) 그 주소를 1분간 차단
BODY_LIMIT = 4096
PAGE_POLICY = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; "
               "frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
FILES = {"/remote": ("remote.html", "text/html; charset=utf-8"), "/remote.js": ("remote.js", "text/javascript; charset=utf-8"),
         "/remote-sign.js": ("remote-sign.js", "text/javascript; charset=utf-8"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}


class RemoteError(ValueError):
    """잘못된 휴대폰 조작 설정. 메시지는 한국어 안내."""


def canonical(method: str, path: str, stamp: str, nonce: str, body: bytes) -> bytes:
    """서명할 내용(remote-sign.js와 같아야 함)."""
    return f"{method.upper()}\n{path}\n{stamp}\n{nonce}\n{hashlib.sha256(body).hexdigest()}".encode()


def sign(secret: str, method: str, path: str, stamp: str, nonce: str, body: bytes = b"") -> str:
    return hmac.new(secret.encode(), canonical(method, path, stamp, nonce, body), hashlib.sha256).hexdigest()


def confirm_code(secret: str) -> str:
    """휴대폰과 PC에 함께 보이는 4자리 확인 번호(같은 기기인지 눈으로 확인)."""
    digest = hmac.new(secret.encode(), b"debutkit-confirm", hashlib.sha256).hexdigest()
    return str(int(digest[:8], 16) % 10000).zfill(4)


@dataclass
class Device:
    id: str
    secret: str
    name: str = "휴대폰"
    created: float = field(default_factory=time.time)
    approved: bool = False
    claimed: bool = False  # 휴대폰이 QR로 접속함(승인 대기)
    last_seen: float = 0.0

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "approved": self.approved, "claimed": self.claimed, "created": round(self.created),
                "last_seen": round(self.last_seen), "code": confirm_code(self.secret)}


def devices_path() -> Path:
    return settings.settings_path().parent / "remote-devices.json"


class DeviceStore:
    """등록 기기(승인된 기기는 파일, QR 대기 기기는 메모리), 서명 확인, 일회용 값, 실패 제한."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._devices: dict[str, Device] = {}
        self._nonces: dict[str, dict[str, float]] = {}
        self._fails: dict[str, list[float]] = {}
        self._blocked: dict[str, float] = {}
        for item in self._read():
            self._devices[item.id] = item

    @property
    def path(self) -> Path:
        return self._path or devices_path()

    def _read(self) -> list[Device]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [Device(**{key: item[key] for key in ("id", "secret", "name", "created", "approved", "last_seen") if key in item}, claimed=True)
                    for item in data.get("devices", []) if isinstance(item, dict) and item.get("approved") is True
                    and isinstance(item.get("id"), str) and isinstance(item.get("secret"), str) and len(item["secret"]) >= 32]
        except (OSError, ValueError, TypeError, AttributeError):
            return []

    def _save(self) -> None:
        approved = [asdict(item) for item in self._devices.values() if item.approved]
        for item in approved:
            item.pop("claimed", None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"devices": approved}, ensure_ascii=False, indent=2), encoding="utf-8")

    def _expire(self) -> None:
        now = time.time()
        for key in [key for key, item in self._devices.items() if not item.approved and now - item.created > PAIR_SECONDS]:
            del self._devices[key]

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            self._expire()
            return [item.public() for item in sorted(self._devices.values(), key=lambda item: item.created)]

    def pair(self) -> Device:
        """새 QR용 기기(승인 전, 5분 유효). 아직 쓰지 않은 QR은 새 QR로 바꾼다."""
        with self._lock:
            self._expire()
            for key in [key for key, item in self._devices.items() if not item.approved and not item.claimed]:
                del self._devices[key]
            if len(self._devices) >= MAX_DEVICES:
                raise RemoteError(f"등록 기기는 최대 {MAX_DEVICES}대: 쓰지 않는 기기를 삭제한 뒤 다시 시도")
            device = Device(secrets.token_hex(4), secrets.token_urlsafe(32))
            self._devices[device.id] = device
            return device

    def get(self, device_id: str) -> Device | None:
        with self._lock:
            self._expire()
            return self._devices.get(device_id)

    def approve(self, device_id: str) -> Device:
        with self._lock:
            device = self._devices.get(device_id)
            if device is None or not device.claimed:
                raise RemoteError("승인할 기기 없음: 휴대폰에서 QR을 먼저 열기")
            device.approved = True
            self._save()
            return device

    def remove(self, device_id: str) -> bool:
        with self._lock:
            device = self._devices.pop(device_id, None)
            self._nonces.pop(device_id, None)
            if device is not None and device.approved:
                self._save()
            return device is not None

    def blocked(self, address: str) -> bool:
        with self._lock:
            return self._blocked.get(address, 0) > time.time()

    def _fail(self, address: str) -> None:
        now = time.time()
        recent = [moment for moment in self._fails.get(address, []) if now - moment < 60] + [now]
        self._fails[address] = recent
        if len(recent) >= FAIL_LIMIT:
            self._blocked[address] = now + 60
            self._fails[address] = []

    def verify(self, method: str, path: str, headers: Any, body: bytes, address: str) -> tuple[Device | None, int, str]:
        """서명 확인. (기기, 0, "") 또는 (None, 상태 코드, 안내)."""
        device_id = str(headers.get("X-Debutkit-Device") or "")
        stamp = str(headers.get("X-Debutkit-Time") or "")
        nonce = str(headers.get("X-Debutkit-Nonce") or "")
        given = str(headers.get("X-Debutkit-Sign") or "")
        with self._lock:
            if self._blocked.get(address, 0) > time.time():
                return None, HTTPStatus.TOO_MANY_REQUESTS, "확인 실패가 잦아 잠시 차단됨: 1분 뒤 다시 시도"
            self._expire()
            device = self._devices.get(device_id)
            expected = sign(device.secret, method, path, stamp, nonce, body) if device else ""
            if device is None or not hmac.compare_digest(expected, given):
                self._fail(address)
                return None, HTTPStatus.UNAUTHORIZED, "등록되지 않은 기기: PC의 휴대폰 연결 화면에서 QR을 다시 찍기"
            try:
                moment = int(stamp) / 1000
            except ValueError:
                moment = 0.0
            if abs(time.time() - moment) > SKEW:
                return None, HTTPStatus.UNAUTHORIZED, "휴대폰과 PC의 시각이 2분 넘게 다름: 두 기기의 자동 시간 설정 확인"
            used = self._nonces.setdefault(device.id, {})
            for key in [key for key, when in used.items() if time.time() - when > SKEW * 2]:
                del used[key]
            if not 8 <= len(nonce) <= 64 or nonce in used:
                return None, HTTPStatus.UNAUTHORIZED, "같은 요청을 다시 보냄(거부)"
            used[nonce] = time.time()
            device.last_seen = time.time()
            return device, 0, ""

    def claim(self, device: Device, name: str) -> bool:
        """휴대폰이 QR로 처음 접속. 새로 접속했으면 True(승인 대기 알림)."""
        with self._lock:
            fresh = not device.claimed
            device.claimed = True
            if name:
                device.name = name[:30]
            return fresh


def check_address(address: Any) -> str:
    """이 PC의 내부 네트워크 주소 중 하나만 허용."""
    text = str(address or "").strip()
    if text not in camera.lan_addresses():
        raise RemoteError("이 PC의 내부 네트워크 주소(공유기 주소, 보통 192.168로 시작) 중 하나 선택")
    return text


def check_port(port: Any) -> int:
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise RemoteError(f"포트는 1024에서 65535 사이의 정수(기본 {DEFAULT_PORT})")
    return port


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self) -> None:
        if sys.platform == "win32":  # 다른 프로그램이 같은 포트를 함께 열지 못하게(서버 모듈과 같은 이유)
            import socket

            self.allow_reuse_address = False
            self.socket.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_EXCLUSIVEADDRUSE", -5), 1)
        super().server_bind()


class RemoteControl:
    """휴대폰 조작 화면 서버(별도 창구)와 기기 관리. 오버레이 서버의 추첨, 동작 상태를 함께 쓴다."""

    def __init__(self, raffle: raffles.Raffle, motion: motions.MotionState, draw: Any, *, notify: Callable[[str], Any] | None = None,
                 store: DeviceStore | None = None) -> None:
        self.raffle, self.motion, self.draw = raffle, motion, draw
        self.notify = notify or (lambda text: None)
        self.devices = store or DeviceStore()
        self.httpd: _Server | None = None
        self._thread: threading.Thread | None = None
        saved = settings.load()
        self.address = str(saved.get("remote_address") or "")
        self.port = saved.get("remote_port") if isinstance(saved.get("remote_port"), int) else DEFAULT_PORT
        self.enabled = saved.get("remote_enabled") is True
        self.error = ""

    # ------------------------------------------------------------------ 시작, 멈춤
    @property
    def running(self) -> bool:
        return self.httpd is not None

    @property
    def url(self) -> str:
        return f"http://{self.address}:{self.port}/remote" if self.address else ""

    def start(self, address: Any = None, port: Any = None, *, save: bool = True) -> dict[str, Any]:
        address = check_address(self.address if address is None else address)
        port = check_port(self.port if port is None else port)
        self.stop(save=False)
        try:
            httpd = _Server((address, port), _handler(self, address, port))
        except OSError as error:
            self.error = f"{address}:{port} 열기 실패({error}): 다른 포트 지정"
            raise RemoteError(self.error) from None
        self.httpd, self.address, self.port, self.error = httpd, address, int(httpd.server_address[1]), ""
        self._thread = threading.Thread(target=httpd.serve_forever, name="remote-control", daemon=True)
        self._thread.start()
        if save:
            self._save(True)
        return self.status()

    def stop(self, *, save: bool = True) -> dict[str, Any]:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd, self._thread = None, None
        if save:
            self._save(False)
        return self.status()

    def start_saved(self) -> bool:
        """오버레이 시작 때: 저장 설정에서 켠 경우만. 주소가 바뀌었으면(공유기 재연결 등) 안내만."""
        if not self.enabled:
            return False
        try:
            self.start(save=False)
        except RemoteError as error:
            self.notify(f"휴대폰 조작 화면: {error}")
            return False
        self.notify(f"휴대폰 조작 화면: {self.url} (등록한 휴대폰만 조작)")
        return True

    def _save(self, enabled: bool) -> None:
        self.enabled = enabled
        saved = settings.load()
        saved.update(remote_enabled=enabled, remote_port=self.port)
        if self.address:
            saved["remote_address"] = self.address
        settings.save(saved)

    # ------------------------------------------------------------------ 기기
    def status(self) -> dict[str, Any]:
        return {"running": self.running, "enabled": self.enabled, "address": self.address, "port": self.port, "url": self.url,
                "addresses": camera.lan_addresses(), "devices": self.devices.all(), "error": self.error, "max_devices": MAX_DEVICES,
                "pair_seconds": PAIR_SECONDS}

    def pair(self) -> dict[str, Any]:
        """새 기기 QR 주소(# 뒤에 기기 번호와 비밀값). 조작 화면이 켜져 있어야 한다."""
        if not self.running:
            raise RemoteError("휴대폰 조작 화면을 먼저 켜기")
        device = self.devices.pair()
        return {**device.public(), "url": f"{self.url}#d={device.id}&k={device.secret}", "expires": round(device.created + PAIR_SECONDS)}

    def pair_url(self, device_id: str) -> str:
        device = self.devices.get(device_id)
        if device is None or device.approved or not self.running:
            raise RemoteError("만료된 QR")
        return f"{self.url}#d={device.id}&k={device.secret}"

    def approve(self, device_id: str) -> dict[str, Any]:
        device = self.devices.approve(device_id)
        self.notify(f"휴대폰 조작 화면: {device.name} 승인")
        return self.status()

    def remove(self, device_id: str) -> dict[str, Any]:
        if not self.devices.remove(device_id):
            raise RemoteError("없는 기기")
        return self.status()

    # ------------------------------------------------------------------ 휴대폰 요청
    def snapshot(self) -> dict[str, Any]:
        """휴대폰 화면에 보여 줄 상태: 참여 추첨, 동작 목록, 최근 후원 추첨 결과(읽을 문장)."""
        draws = sorted(self.draw.recent(), key=lambda item: item.get("time", 0), reverse=True)[:5]
        overview = motions.overview()
        return {"raffle": self.raffle.status(), "motions": [{"id": item["id"], "name": item["name"]} for item in overview["motions"]],
                "idle": overview["idle"], "draws": [{"time": item.get("time"), "name": item.get("name"), "script": item.get("script", ""),
                                                     "test": bool(item.get("test"))} for item in draws]}

    def act(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        if path == "/remote/api/raffle/start":
            self.raffle.start()
        elif path == "/remote/api/raffle/stop":
            self.raffle.stop()
        elif path == "/remote/api/raffle/draw":
            count = data.get("count", 1)
            self.raffle.draw(count if isinstance(count, int) else 1, "order" if data.get("mode") == "order" else "pick")
        elif path == "/remote/api/motion":
            if data.get("stop") is True:
                self.motion.play(stop=True)
            else:
                found = motions.get(str(data.get("id") or ""))
                if found is None:
                    raise RemoteError("등록한 동작 없음")
                self.motion.play(found.id)
        else:
            raise RemoteError("모르는 요청")
        return self.snapshot()


def _handler(control: RemoteControl, address: str, port: int) -> type[BaseHTTPRequestHandler]:
    host = f"{address}:{port}"

    class Handler(BaseHTTPRequestHandler):
        server_version = "debutkit-remote"

        def log_message(self, format: str, *args: Any) -> None:  # 조용히
            pass

        def _send(self, status: int, body: bytes, content_type: str = "application/json", policy: str = "") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            if policy:
                self.send_header("Content-Security-Policy", policy)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, value: Any, status: int = HTTPStatus.OK) -> None:
            self._send(status, json.dumps(value, ensure_ascii=False).encode())

        def _allowed(self) -> bool:
            """이 창구 주소로 온 요청만(DNS 리바인딩, 다른 사이트의 요청 차단)."""
            origin = self.headers.get("Origin")
            return self.headers.get("Host", "") == host and (origin is None or origin == f"http://{host}")

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if not self._allowed():
                return self._send(HTTPStatus.FORBIDDEN, b'{"error": "forbidden"}')
            if path == "/remote/api/status":
                return self._api("GET", path, b"")
            found = FILES.get(path)
            if found is None:
                return self._send(HTTPStatus.NOT_FOUND, b'{"error": "not found"}')
            name, content_type = found
            body = resources.files("debutkit.overlay").joinpath("static", name).read_bytes()
            self._send(HTTPStatus.OK, body, content_type, PAGE_POLICY if path == "/remote" else "")

        def do_POST(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            try:
                length = min(int(self.headers.get("Content-Length") or 0), BODY_LIMIT)
            except ValueError:
                length = 0
            body = self.rfile.read(length) if length > 0 else b""
            if not self._allowed():
                return self._send(HTTPStatus.FORBIDDEN, b'{"error": "forbidden"}')
            if not path.startswith("/remote/api/"):
                return self._send(HTTPStatus.NOT_FOUND, b'{"error": "not found"}')
            self._api("POST", path, body)

        def _api(self, method: str, path: str, body: bytes) -> None:
            address_ = self.client_address[0]
            device, status, message = control.devices.verify(method, path, self.headers, body, address_)
            if device is None:
                return self._json({"error": message}, status)
            try:
                data = json.loads(body or b"{}")
            except ValueError:
                data = {}
            data = data if isinstance(data, dict) else {}
            if path == "/remote/api/hello" and method == "POST":
                if control.devices.claim(device, str(data.get("name") or "")) and not device.approved:
                    control.notify(f"휴대폰 조작 화면: 새 기기 승인 대기(확인 번호 {confirm_code(device.secret)}). PC의 휴대폰 연결 화면에서 승인")
                return self._json({"approved": device.approved, "code": confirm_code(device.secret), "name": device.name})
            if not device.approved:
                return self._json({"error": "PC의 휴대폰 연결 화면에서 이 기기를 승인한 뒤 사용", "approved": False,
                                   "code": confirm_code(device.secret)}, HTTPStatus.FORBIDDEN)
            if path == "/remote/api/status" and method == "GET":
                return self._json(control.snapshot())
            if method != "POST":
                return self._json({"error": "모르는 요청"}, HTTPStatus.NOT_FOUND)
            try:
                return self._json(control.act(path, data))
            except (RemoteError, raffles.RaffleError) as error:
                return self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

    return Handler
