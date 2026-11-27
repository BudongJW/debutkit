"""스트리머의 Cloudflare 계정에 커뮤니티 올리기(REST API, 표준 라이브러리만. wrangler, Node 필요 없음).

필요한 API 토큰 권한(Cloudflare 대시보드의 API 토큰 만들기, "Cloudflare Workers 편집" 템플릿에 D1 편집 추가):
계정의 Workers 스크립트 편집, Workers KV 저장소 편집, D1 편집, 계정 설정 읽기.

올리는 순서: D1 데이터베이스(없으면 만듦), 구조(schema.sql, 이미 있으면 그대로), KV(그림), Worker(바인딩과 비밀값 포함),
workers.dev 주소 켜기. 같은 이름으로 다시 올리면 고치기(글과 회원은 그대로).
"""

from __future__ import annotations

import json
import re
import secrets
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

API = "https://api.cloudflare.com/client/v4"
WORKER = Path(__file__).resolve().parent / "worker"
COMPATIBILITY_DATE = "2025-09-01"
SCRIPT_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$")
#: Cloudflare 오류 번호 -> 한국어 안내
ERRORS = {
    9106: "Cloudflare API 토큰이 비어 있거나 형식이 틀림",
    9109: "Cloudflare API 토큰이 맞지 않거나 만료됨",
    10000: "Cloudflare API 토큰 권한 부족: Workers 스크립트 편집, Workers KV 편집, D1 편집, 계정 설정 읽기 권한 필요",
    10007: "workers.dev 하위 주소가 아직 없음",
    10036: "workers.dev 하위 주소 이름을 다른 사람이 이미 씀",
}


class CloudflareError(RuntimeError):
    pass


def check_script(name: str) -> str:
    text = str(name or "").strip().lower()
    if not SCRIPT_NAME.match(text):
        raise CloudflareError("커뮤니티 주소 이름은 영문 소문자, 숫자, -로 3~40자(예: dotori-fans)")
    return text


def schema_statements(text: str | None = None) -> list[str]:
    """schema.sql을 문장 하나씩(주석 줄 제외)."""
    text = text if text is not None else (WORKER / "schema.sql").read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if not line.strip().startswith("--")]
    return [statement.strip() for statement in "\n".join(lines).split(";") if statement.strip()]


class Cloudflare:
    def __init__(self, token: str, *, opener: Callable[..., Any] | None = None, timeout: float = 60.0) -> None:
        if not token or not re.fullmatch(r"[A-Za-z0-9_\-]{20,}", token.strip()):
            raise CloudflareError(ERRORS[9106])
        self.token = token.strip()
        self.opener = opener or urllib.request.urlopen
        self.timeout = timeout

    def call(self, method: str, path: str, body: Any = None, *, data: bytes | None = None, content_type: str = "application/json") -> Any:
        payload = data if data is not None else json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(API + path, data=payload, method=method,
                                         headers={"Authorization": f"Bearer {self.token}", "Content-Type": content_type, "User-Agent": "debutkit"})
        try:
            with self.opener(request, timeout=self.timeout) as response:
                answer = json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as error:
            try:
                answer = json.loads(error.read().decode("utf-8") or "{}")
            except ValueError:
                answer = {"errors": [{"code": error.code, "message": str(error.reason)}]}
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise CloudflareError(f"Cloudflare에 연결하지 못함: {getattr(error, 'reason', error)}") from None
        if not answer.get("success"):
            errors = answer.get("errors") or [{}]
            code = errors[0].get("code")
            raise CloudflareError(ERRORS.get(code) or f"Cloudflare 오류 {code}: {errors[0].get('message', '')}".strip())
        return answer.get("result")

    # ------------------------------------------------------------------ 계정과 저장소
    def accounts(self) -> list[dict[str, Any]]:
        return list(self.call("GET", "/accounts?per_page=50") or [])

    def account(self, wanted: str = "") -> str:
        found = self.accounts()
        if wanted:
            if not any(item.get("id") == wanted for item in found):
                raise CloudflareError("이 토큰으로 쓸 수 없는 Cloudflare 계정")
            return wanted
        if not found:
            raise CloudflareError("이 토큰으로 쓸 수 있는 Cloudflare 계정이 없음")
        if len(found) > 1:
            names = ", ".join(f"{item.get('name')}({item.get('id')})" for item in found)
            raise CloudflareError(f"계정이 여러 개: 계정 ID를 골라 입력({names})")
        return str(found[0]["id"])

    def database(self, account: str, name: str) -> str:
        for item in self.call("GET", f"/accounts/{account}/d1/database?name={name}&per_page=100") or []:
            if item.get("name") == name:
                return str(item["uuid"])
        return str(self.call("POST", f"/accounts/{account}/d1/database", {"name": name})["uuid"])

    def migrate(self, account: str, database: str) -> int:
        statements = schema_statements()
        for statement in statements:
            self.call("POST", f"/accounts/{account}/d1/database/{database}/query", {"sql": statement})
        return len(statements)

    def namespace(self, account: str, title: str) -> str:
        for item in self.call("GET", f"/accounts/{account}/storage/kv/namespaces?per_page=100") or []:
            if item.get("title") == title:
                return str(item["id"])
        return str(self.call("POST", f"/accounts/{account}/storage/kv/namespaces", {"title": title})["id"])

    def subdomain(self, account: str, wanted: str) -> str:
        """계정의 workers.dev 하위 주소. 없으면 ``wanted`` 로 만든다(계정마다 하나)."""
        try:
            found = (self.call("GET", f"/accounts/{account}/workers/subdomain") or {}).get("subdomain")
        except CloudflareError:
            found = ""
        if found:
            return str(found)
        return str(self.call("PUT", f"/accounts/{account}/workers/subdomain", {"subdomain": wanted})["subdomain"])

    # ------------------------------------------------------------------ Worker
    def upload(self, account: str, script: str, code: str, bindings: list[dict[str, Any]]) -> None:
        metadata = {"main_module": "worker.js", "compatibility_date": COMPATIBILITY_DATE, "bindings": bindings}
        body, content_type = multipart([("metadata", "", "application/json", json.dumps(metadata).encode("utf-8")),
                                        ("worker.js", "worker.js", "application/javascript+module", code.encode("utf-8"))])
        self.call("PUT", f"/accounts/{account}/workers/scripts/{script}", data=body, content_type=content_type)

    def enable_workers_dev(self, account: str, script: str) -> None:
        self.call("POST", f"/accounts/{account}/workers/scripts/{script}/subdomain", {"enabled": True, "previews_enabled": False})


def multipart(parts: list[tuple[str, str, str, bytes]]) -> tuple[bytes, str]:
    boundary = "debutkit-" + secrets.token_hex(12)
    chunks = []
    for name, filename, kind, content in parts:
        disposition = f'form-data; name="{name}"' + (f'; filename="{filename}"' if filename else "")
        chunks.append(f"--{boundary}\r\nContent-Disposition: {disposition}\r\nContent-Type: {kind}\r\n\r\n".encode("utf-8") + content + b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


@dataclass
class Deployed:
    url: str
    account: str
    script: str
    database: str
    kv: str
    subdomain: str


def deploy(cf: Cloudflare, script: str, *, account: str = "", secrets_: dict[str, str], subdomain_hint: str = "") -> Deployed:
    """커뮤니티 올리기 또는 고치기. ``secrets_`` 는 Worker 비밀값(ADMIN_TOKEN_HASH, SESSION_KEY, 선택 로그인 키)."""
    script = check_script(script)
    account = cf.account(account)
    database = cf.database(account, f"{script}-db")
    cf.migrate(account, database)
    kv = cf.namespace(account, f"{script}-files")
    bindings: list[dict[str, Any]] = [{"type": "d1", "name": "DB", "id": database}, {"type": "kv_namespace", "name": "FILES", "namespace_id": kv}]
    bindings += [{"type": "secret_text", "name": name, "text": value} for name, value in sorted(secrets_.items()) if value]
    cf.upload(account, script, (WORKER / "worker.js").read_text(encoding="utf-8"), bindings)
    subdomain = cf.subdomain(account, check_script(subdomain_hint or script))
    cf.enable_workers_dev(account, script)
    return Deployed(f"https://{script}.{subdomain}.workers.dev", account, script, database, kv, subdomain)
