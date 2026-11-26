"""커뮤니티와 방송 연동(``/community/control`` 조작 화면, ``/community`` 방송 화면).

- 채팅 ``!인증 숫자``: 커뮤니티 가입과 계정 연결(채팅의 플랫폼 계정 번호로). ``!출석``: 커뮤니티 포인트(연결한 사람만, 하루 한 번)
- 방송 중 표시: 실제 플랫폼 채팅이나 후원이 처음 오면 커뮤니티에 방송 중, 오버레이를 멈추면 방송 끝
- 방송에 띄우기: 스트리머, 매니저가 커뮤니티에서 고른 글과 팬아트를 ``/community`` 화면에 차례로
- 참여 추첨: 모집을 시작하면 커뮤니티에도 참가 단추, 커뮤니티 참가자를 명단에 더함
- 커뮤니티와 주고받는 일은 별도 스레드가 한다(채팅 처리를 막지 않음). 실패는 조작 화면에 안내만
"""

from __future__ import annotations

import queue
import re
import threading
import time
from typing import Any, Callable

from .. import community as store
from ..community import setup as community_setup
from ..community.client import CommunityError
from . import feature
from .events import DEMO_USER

VERIFY = re.compile(r"^!인증\s*(\d{6})\s*$")
ATTEND = re.compile(r"^!출석\s*$")
PLATFORMS = ("chzzk", "soop", "twitch", "youtube")


class CommunityLink:
    def __init__(self, context: feature.Context, *, make_client: Callable[[], Any] | None = None, interval: float = 8.0,
                 start: bool = True) -> None:
        self.context = context
        self.make_client = make_client or (lambda: store.connect())
        self.interval = interval
        self.channel = feature.Channel({"seq": 0})
        self.jobs: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue(maxsize=300)
        self.status: dict[str, Any] = {"state": None, "error": "", "checked": 0.0, "live": False, "raffle_open": False, "verified": 0, "attended": 0}
        self._stop = threading.Event()
        self._live_sent = False
        self._raffle_since = 0.0
        self._last_state = 0.0
        self._seq = 0
        self._config: tuple[float, dict[str, Any]] = (0.0, {})
        self._thread = threading.Thread(target=self._run, name="debutkit-community", daemon=True)
        if start:
            self._thread.start()

    # ------------------------------------------------------------------ 채팅
    def tap(self, event: Any) -> None:
        # 시험 채팅(demo, 방송 화면 미리보기의 시험 채팅)도 인증과 출석은 받는다(방송 없이 미리 해 보기). 방송 중 표시는 실제 플랫폼만
        if event.kind not in ("chat", "donation") or event.platform not in (*PLATFORMS, "demo"):
            return
        config = self.config()
        if not config["url"]:
            return
        if event.platform != "demo" and getattr(event, "user", "") != DEMO_USER and not self._live_sent and config["auto"]["live"]:
            self._live_sent = True
            self._put("live", {"live": True})
        text = event.text.strip()
        payload = {"platform": event.platform, "user": getattr(event, "user", ""), "name": event.name, "role": event.role}
        found = VERIFY.match(text)
        if found and config["auto"]["verify"]:
            self._put("verify", {**payload, "code": found.group(1)})
        elif ATTEND.match(text) and config["auto"]["attend"]:
            self._put("attend", payload)

    def config(self) -> dict[str, Any]:
        """채팅마다 파일을 읽지 않도록 5초 동안 기억."""
        stamp, config = self._config
        if time.monotonic() - stamp > 5 or not config:
            config = store.load()
            self._config = (time.monotonic(), config)
        return config

    def _put(self, kind: str, data: dict[str, Any]) -> None:
        try:
            self.jobs.put_nowait((kind, data))
        except queue.Full:
            pass

    # ------------------------------------------------------------------ 주고받기
    def _run(self) -> None:
        last_poll = 0.0
        while not self._stop.is_set():
            try:
                kind, data = self.jobs.get(timeout=0.5)
            except queue.Empty:
                kind, data = "", {}
            due = time.monotonic() - last_poll >= self.interval
            if not kind and not due:
                continue
            try:
                api = self.make_client()
                if api is not None and kind:
                    self._job(api, kind, data)
                if due:
                    last_poll = time.monotonic()
                    if api is not None:
                        self.poll(api)
            except CommunityError as error:
                self.status["error"] = str(error)
            except Exception as error:  # 연동 실패가 오버레이를 멈추지 않게
                self.status["error"] = f"커뮤니티 연동 오류: {error}"

    def _job(self, api: Any, kind: str, data: dict[str, Any]) -> None:
        if kind == "live":
            config = store.load()
            api.live(bool(data.get("live")), str(data.get("title") or ""), str(data.get("url") or config["live_url"]))
            self.status["live"] = bool(data.get("live"))
        elif kind in ("verify", "attend"):
            answer = api.chat(kind, data["platform"], data["user"], data["name"], data.get("role", ""), data.get("code", ""))
            if answer.get("ok"):
                self.status["verified" if kind == "verify" else "attended"] += 1
                if kind == "attend" and answer.get("given"):
                    self._show({"kind": "attend", "title": f"{answer.get('name') or data['name']} 출석", "body": f"+{answer['given']}점, 모두 {answer.get('points', 0)}점",
                                "author": "", "image": "", "board": "attend"})

    def poll(self, api: Any) -> None:
        """방송에 띄울 글, 참여 추첨 맞추기, 밀린 설정 보내기, 상태(1분마다)."""
        config = store.load()
        if config["sync"]:
            community_setup.sync_settings(config)
        if config["auto"]["stage"]:
            for item in api.stage():
                self._show({**item, "kind": "post"})
        raffle = getattr(self.context, "raffle", None)
        if raffle is not None and config["auto"]["raffle"]:
            current = raffle.status()
            if current["open"] != self.status["raffle_open"]:
                api.raffle(bool(current["open"]), str(current.get("title") or ""))
                self.status["raffle_open"] = bool(current["open"])
                self._raffle_since = time.time() * 1000 - 1000 if current["open"] else 0.0
            if current["open"]:
                for entry in api.raffle_entries(self._raffle_since):
                    raffle.add(str(entry.get("name") or ""), "community", "community")
                    self._raffle_since = max(self._raffle_since, float(entry.get("at") or 0))
        if time.monotonic() - self._last_state >= 60 or self.status["state"] is None:
            self._last_state = time.monotonic()
            self.status["state"] = api.state()
            self.status["checked"] = time.time()
        self.status["error"] = ""

    def _show(self, item: dict[str, Any]) -> None:
        self._seq += 1
        self.channel.publish({"seq": self._seq, "item": item, "seconds": store.load()["stage_seconds"]}, keep=False)

    def stop(self) -> None:
        if self._live_sent:
            try:
                api = self.make_client()
                if api is not None:
                    api.timeout = 3
                    api.live(False)
            except Exception:
                pass
        self._stop.set()


def public_config(link: CommunityLink | None = None) -> dict[str, Any]:
    config = store.load()
    box = store.keys()
    saved = {"cloudflare": bool(box.load("cloudflare_token")), "admin": bool(box.load("admin_token")),
             "secrets": [key for key in store.PROVIDERS if box.load(f"{key}_secret")]}
    status = dict(link.status) if link else {}
    return {**config, "keys": saved, "status": status, "redirect_uris": community_setup.redirect_uris(config["url"]), "provider_names": store.PROVIDERS,
            "storage": box.mode}


def make_feature(context: feature.Context, *, link: CommunityLink | None = None) -> feature.Feature:
    link = link or CommunityLink(context)

    def need() -> Any:
        api = store.connect()
        if api is None:
            raise feature.FeatureError("커뮤니티를 먼저 올리기")
        return api

    def call(action: Callable[[Any], Any]) -> Any:
        try:
            return action(need())
        except CommunityError as error:
            raise feature.FeatureError(str(error)) from None

    def deploy(data: dict[str, Any]) -> dict[str, Any]:
        from ..community.cloudflare import CloudflareError

        try:
            done = community_setup.publish(str(data.get("script") or ""), cloudflare_token=str(data.get("cloudflare_token") or ""),
                                           account=str(data.get("account") or ""), name=str(data.get("name") or ""),
                                           owner_name=str(data.get("owner_name") or ""), providers=data.get("providers") if isinstance(data.get("providers"), dict) else None)
        except CloudflareError as error:
            raise feature.FeatureError(str(error)) from None
        return {**public_config(link), "note": done.get("note", "")}

    def options(data: dict[str, Any]) -> dict[str, Any]:
        config = store.load()
        if isinstance(data.get("auto"), dict):
            config["auto"] = {**config["auto"], **{key: bool(value) for key, value in data["auto"].items() if key in store.AUTO}}
        if "live_url" in data:
            url = str(data["live_url"] or "").strip()
            if url and not url.startswith("https://"):
                raise feature.FeatureError("방송 주소는 https:// 로 시작")
            config["live_url"] = url[:300]
        if "stage_seconds" in data:
            seconds = data["stage_seconds"]
            if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 4 <= seconds <= 60:
                raise feature.FeatureError("방송에 띄우는 시간은 4초에서 60초 사이")
            config["stage_seconds"] = int(seconds)
        if "name" in data:
            config["name"] = str(data["name"] or "").strip()[:40]
            config["sync"] = True
        store.save(config)
        texts = {key: str(data[key]) for key in ("about", "contact") if key in data}
        if texts and config["url"]:
            call(lambda api: api.settings(**texts))
        return public_config(link)

    def notice(data: dict[str, Any]) -> dict[str, Any]:
        board = data.get("board") if data.get("board") in ("notice", "clips") else "notice"
        return call(lambda api: api.post(str(data.get("title") or ""), str(data.get("body") or ""), board=board, link=str(data.get("link") or ""),
                                         pinned=bool(data.get("pinned"))))

    def schedule(data: dict[str, Any]) -> dict[str, Any]:
        items = data.get("items")
        if not isinstance(items, list):
            raise feature.FeatureError("일정은 목록")
        answer = call(lambda api: api.schedule(items))
        config = store.load()
        config["schedule"] = items
        store.save(config)
        return answer

    def live(data: dict[str, Any]) -> dict[str, Any]:
        config = store.load()
        answer = call(lambda api: api.live(bool(data.get("live")), str(data.get("title") or ""), config["live_url"]))
        link.status["live"] = bool(data.get("live"))
        return answer

    def owner_link(_: dict[str, Any]) -> dict[str, Any]:
        return {"url": call(lambda api: api.owner_link())}

    def refresh(_: dict[str, Any]) -> dict[str, Any]:
        def run(api: Any) -> dict[str, Any]:
            link.status["state"] = api.state()
            link.status["checked"] = time.time()
            link.status["error"] = ""
            return public_config(link)

        return call(run)

    def test_stage(data: dict[str, Any]) -> dict[str, Any]:
        link._show({"kind": "post", "board": "fanart", "title": str(data.get("title") or "시험 팬아트")[:80], "body": "커뮤니티에서 방송에 띄우기를 누른 글이 이렇게 나옵니다",
                    "author": "시험 시청자", "image": ""})
        return {"ok": True}

    def forget(_: dict[str, Any]) -> dict[str, Any]:
        """이 PC의 연결 정보만 지움(Cloudflare의 커뮤니티와 글은 그대로)."""
        box = store.keys()
        for name in ("cloudflare_token", "admin_token", "session_key", *[f"{key}_secret" for key in store.PROVIDERS]):
            box.clear(name)
        store.save(dict(store.DEFAULTS))
        return public_config(link)

    return feature.Feature(
        name="community", static={"/community": "community.html", "/community/control": "community-control.html"},
        get={"/community/config": lambda query: public_config(link)},
        post={"/community/deploy": deploy, "/community/options": options, "/community/notice": notice, "/community/schedule": schedule,
              "/community/live": live, "/community/owner-link": owner_link, "/community/refresh": refresh, "/community/test-stage": test_stage,
              "/community/forget": forget},
        feeds={"community": link.channel}, taps=[link.tap], stop=link.stop,
        body_limit={"/community/deploy": 16384, "/community/schedule": 32768, "/community/notice": 32768})
