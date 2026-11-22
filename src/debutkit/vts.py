"""VTube Studio 연동: 공개 API(WebSocket, 기본 ws://127.0.0.1:8001)로 모델 불러오기, 단축키 실행, 후원 반응.

- 처음 연결할 때 VTube Studio 화면에 debutkit 플러그인 허용 요청이 나타나고, 사용자가 허용하면 토큰을 받는다
- 토큰은 이 PC의 설정 폴더(``vts-token.json``)에만 보관하고 저장 설정 파일에는 넣지 않는다. ``debutkit vts logout`` 으로 삭제
- VTube Studio의 플러그인 API 사용 설정(설정의 API 사용 켜기)이 필요하다
- 규격: https://github.com/DenchiSoft/VTubeStudio (MIT)
"""

from __future__ import annotations

import base64
import json
import os
import queue
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import settings

DEFAULT_URL = "ws://127.0.0.1:8001"
PLUGIN = {"pluginName": "debutkit", "pluginDeveloper": "debutkit"}
ERRORS = {
    8: "VTube Studio 설정에서 플러그인 API 사용 필요",
    50: "VTube Studio에서 debutkit 연결을 허용하지 않음",
    53: "VTube Studio 화면의 허용 요청이 이미 열려 있음",
}


class VtsError(RuntimeError):
    """VTube Studio 연결, 요청 실패. 메시지는 한국어 안내."""


def token_path() -> Path:
    return settings.settings_path().parent / "vts-token.json"


def load_token(path: Path | None = None) -> str | None:
    try:
        token = json.loads((path or token_path()).read_text(encoding="utf-8")).get("token")
    except (OSError, ValueError, AttributeError):
        return None
    return token if isinstance(token, str) and token else None


def save_token(token: str, path: Path | None = None) -> Path:
    path = path or token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"token": token}), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def forget_token(path: Path | None = None) -> Path | None:
    path = path or token_path()
    if not path.is_file():
        return None
    path.unlink()
    return path


def icon() -> str:
    """허용 요청 창에 보일 128x128 아이콘(PNG, base64)."""
    return base64.b64encode((Path(__file__).resolve().parent / "overlay" / "static" / "vts-icon.png").read_bytes()).decode()


@dataclass(frozen=True)
class Model:
    id: str
    name: str
    loaded: bool


@dataclass(frozen=True)
class Hotkey:
    id: str
    name: str
    kind: str


def _connect(url: str, timeout: float) -> Any:
    try:
        import websocket  # websocket-client(채팅 연결 모듈과 함께 설치)
    except ImportError as error:
        raise VtsError('VTube Studio 연동에는 websocket-client 필요: pip install "debutkit[live]"') from error
    try:
        return websocket.create_connection(url, timeout=timeout)
    except Exception as error:
        raise VtsError(f"VTube Studio에 연결하지 못함({url}): VTube Studio 실행과 플러그인 API 사용 설정 확인") from error


class VtsClient:
    """VTube Studio 공개 API 연결 하나. ``with`` 로 쓰거나 ``close()`` 로 닫는다."""

    def __init__(self, url: str = DEFAULT_URL, *, timeout: float = 10.0, connect: Callable[[str, float], Any] = _connect) -> None:
        self.url = url
        self._ws = connect(url, timeout)

    def __enter__(self) -> "VtsClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass

    def request(self, kind: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = uuid.uuid4().hex[:16]
        message = {"apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0", "requestID": request_id, "messageType": f"{kind}Request"}
        if data is not None:
            message["data"] = data
        try:
            self._ws.send(json.dumps(message))
            while True:
                reply = json.loads(self._ws.recv())
                if reply.get("requestID") == request_id:
                    break
        except VtsError:
            raise
        except Exception as error:
            raise VtsError(f"VTube Studio 연결 끊김: {error}") from error
        body = reply.get("data") or {}
        if reply.get("messageType") == "APIError":
            code = body.get("errorID")
            raise VtsError(ERRORS.get(code, f"VTube Studio 오류 {code}: {body.get('message', '')}".strip()))
        return body

    def authenticate(self, token: str | None = None, *, request_new: bool = True, on_prompt: Callable[[], None] = lambda: None) -> str:
        """토큰으로 인증. 토큰이 없거나 거부되면(``request_new``) VTube Studio 화면에서 허용을 받아 새 토큰. 반환: 사용한 토큰."""
        if token:
            result = self.request("Authentication", {**PLUGIN, "authenticationToken": token})
            if result.get("authenticated"):
                return token
            if not request_new:
                raise VtsError("저장한 VTube Studio 토큰이 더 이상 유효하지 않음: debutkit vts login 으로 다시 연결")
        if not request_new:
            raise VtsError("VTube Studio 연결 전: debutkit vts login 또는 설정 마법사의 VTube Studio 연결")
        on_prompt()
        token = str(self.request("AuthenticationToken", {**PLUGIN, "pluginIcon": icon()}).get("authenticationToken") or "")
        if not token or not self.request("Authentication", {**PLUGIN, "authenticationToken": token}).get("authenticated"):
            raise VtsError("VTube Studio 인증 실패")
        return token

    def models(self) -> list[Model]:
        found = self.request("AvailableModels").get("availableModels") or []
        return [Model(str(item.get("modelID")), str(item.get("modelName")), bool(item.get("modelLoaded"))) for item in found]

    def load_model(self, model_id: str) -> None:
        self.request("ModelLoad", {"modelID": model_id})

    def hotkeys(self) -> list[Hotkey]:
        found = self.request("HotkeysInCurrentModel").get("availableHotkeys") or []
        return [Hotkey(str(item.get("hotkeyID")), str(item.get("name")), str(item.get("type"))) for item in found]

    def trigger(self, hotkey: str) -> None:
        """단축키 실행. 이름 또는 ID."""
        self.request("HotkeyTrigger", {"hotkeyID": hotkey})


def find_model(models: list[Model], query: str) -> Model:
    """이름(대소문자 무시) 또는 ID로 찾기. 이름 일부가 하나에만 맞으면 그 모델."""
    lowered = query.lower()
    exact = [model for model in models if model.id == query or model.name.lower() == lowered]
    partial = [model for model in models if lowered in model.name.lower()]
    found = exact or (partial if len(partial) == 1 else [])
    if not found:
        names = ", ".join(model.name for model in models) or "없음"
        raise VtsError(f"VTube Studio 모델 없음: {query}. 모델 목록: {names}. 새로 넣은 모델은 VTube Studio를 다시 시작해야 표시")
    return found[0]


def connect(url: str = DEFAULT_URL, *, request_new: bool = False, on_prompt: Callable[[], None] = lambda: None,
            client_factory: Callable[[str], VtsClient] | None = None) -> VtsClient:
    """인증까지 마친 연결. 새로 받은 토큰은 저장한다."""
    client = (client_factory or VtsClient)(url)
    try:
        saved = load_token()
        token = client.authenticate(saved, request_new=request_new, on_prompt=on_prompt)
        if token != saved:
            save_token(token)
    except Exception:
        client.close()
        raise
    return client


# --------------------------------------------------------------------------- 후원 반응

#: 원 단위 환산(최소 금액 비교용). 그 밖의 단위(Twitch bits, 외화)는 최소 금액 0인 규칙에만 반응
WON_PER_UNIT = {"원": 1.0, "별풍선": 100.0}


@dataclass(frozen=True)
class Reaction:
    hotkey: str
    min_won: int = 0


def parse_reactions(values: Any) -> list[Reaction]:
    """저장 설정의 ``["1000:하트", "0:박수"]`` 형식(최소 금액:단축키)."""
    found = []
    for item in values or []:
        if not isinstance(item, str) or ":" not in item:
            continue
        amount, _, hotkey = item.partition(":")
        if amount.strip().isdigit() and hotkey.strip():
            found.append(Reaction(hotkey.strip(), int(amount.strip())))
    return sorted(found, key=lambda reaction: reaction.min_won, reverse=True)


def pick_reaction(reactions: list[Reaction], amount: float, unit: str) -> Reaction | None:
    """후원 금액에 맞는 반응: 최소 금액이 가장 큰 규칙부터."""
    rate = WON_PER_UNIT.get(unit)
    won = amount * rate if rate is not None else None
    for reaction in reactions:
        if reaction.min_won == 0 or (won is not None and won >= reaction.min_won):
            return reaction
    return None


class VtsReactor:
    """오버레이 허브에 붙여 후원, 멤버십 사건이 오면 VTube Studio 단축키를 실행. 연결이 끊기면 다음 후원 때 다시 연결."""

    def __init__(self, reactions: list[Reaction], *, url: str = DEFAULT_URL, notify: Callable[[str], None] = lambda text: None,
                 connect_client: Callable[[], VtsClient] | None = None) -> None:
        self.reactions = reactions
        self.notify = notify
        self._connect = connect_client or (lambda: connect(url))
        self._queue: queue.Queue[Reaction | None] = queue.Queue(maxsize=50)
        self._thread: threading.Thread | None = None
        self.triggered: list[str] = []

    def __call__(self, event: Any) -> None:
        if getattr(event, "kind", "") not in ("donation", "member") or getattr(event, "platform", "") == "system":
            return
        reaction = pick_reaction(self.reactions, float(getattr(event, "amount", 0) or 0), str(getattr(event, "unit", "") or ""))
        if reaction is not None:
            try:
                self._queue.put_nowait(reaction)
            except queue.Full:
                pass

    def _run(self) -> None:
        client: VtsClient | None = None
        while True:
            reaction = self._queue.get()
            if reaction is None:
                break
            try:
                if client is None:
                    client = self._connect()
                client.trigger(reaction.hotkey)
                self.triggered.append(reaction.hotkey)
            except Exception as error:
                self.notify(f"VTube Studio 후원 반응 실패({reaction.hotkey}): {error}")
                if client is not None:
                    client.close()
                client = None
        if client is not None:
            client.close()

    def start(self) -> "VtsReactor":
        self._thread = threading.Thread(target=self._run, name="debutkit-vts", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._thread is not None:
            self._thread.join(timeout=3)
