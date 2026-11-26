"""올린 커뮤니티의 debutkit API(``/api/...``, Authorization: Bearer 토큰). 표준 라이브러리만."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable


class CommunityError(RuntimeError):
    pass


class Community:
    def __init__(self, url: str, token: str, *, opener: Callable[..., Any] | None = None, timeout: float = 10.0) -> None:
        if not url.startswith("https://") and not url.startswith("http://localhost") and not url.startswith("http://127.0.0.1"):
            raise CommunityError("커뮤니티 주소는 https:// 로 시작")
        self.url = url.rstrip("/")
        self.token = token
        self.opener = opener or urllib.request.urlopen
        self.timeout = timeout

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(body or {}).encode("utf-8") if method == "POST" else None
        request = urllib.request.Request(f"{self.url}/api/{path}", data=data, method=method,
                                         headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
                                                  "User-Agent": "debutkit-community"})
        try:
            with self.opener(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as error:
            try:
                message = json.loads(error.read().decode("utf-8") or "{}").get("error", "")
            except ValueError:
                message = ""
            if error.code == 401:
                message = "커뮤니티 토큰이 맞지 않음: 커뮤니티 화면에서 다시 올리기"
            raise CommunityError(message or f"커뮤니티 응답 오류 {error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise CommunityError(f"커뮤니티에 연결하지 못함: {getattr(error, 'reason', error)}") from None

    def state(self) -> dict[str, Any]:
        return self.request("GET", "state")

    def settings(self, **values: Any) -> dict[str, Any]:
        return self.request("POST", "settings", values)

    def owner_link(self) -> str:
        return str(self.request("POST", "owner-link").get("url", ""))

    def chat(self, command: str, platform: str, user: str, name: str, role: str = "", code: str = "") -> dict[str, Any]:
        return self.request("POST", "chat", {"command": command, "platform": platform, "user": user, "name": name, "role": role, "code": code})

    def post(self, title: str, body: str = "", *, board: str = "notice", link: str = "", pinned: bool = False) -> dict[str, Any]:
        return self.request("POST", "post", {"board": board, "title": title, "body": body, "link": link, "pinned": pinned})

    def schedule(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self.request("POST", "schedule", {"items": items})

    def live(self, live: bool, title: str = "", url: str = "") -> dict[str, Any]:
        return self.request("POST", "live", {"live": live, "title": title, "url": url})

    def raffle(self, open_: bool, title: str = "") -> dict[str, Any]:
        return self.request("POST", "raffle", {"open": open_, "title": title})

    def raffle_entries(self, since: float = 0) -> list[dict[str, Any]]:
        return list(self.request("POST", "raffle-entries", {"since": since}).get("entries") or [])

    def stage(self) -> list[dict[str, Any]]:
        return list(self.request("POST", "stage").get("items") or [])
