"""팬 커뮤니티: 채팅의 시청자 번호, Cloudflare 올리기, 커뮤니티 API, 방송 연동, Worker 시험(Node)."""

import hashlib
import http.client
import io
import json
import shutil
import subprocess
import urllib.error
from pathlib import Path

import pytest

from debutkit import community
from debutkit.community import cloudflare, setup
from debutkit.community.client import Community, CommunityError
from debutkit.overlay import community as link_module
from debutkit.overlay import feature
from debutkit.overlay.events import DemoChat, OverlayEvent, chzzk_api_event, chzzk_event, soop_event, twitch_event
from debutkit.overlay.server import OverlayServer
from debutkit.overlay.youtube import youtube_event
from debutkit.raffle import Raffle
from debutkit.secret import KeyBox

ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- 채팅의 바뀌지 않는 시청자 번호


def test_chat_events_carry_stable_viewer_ids():
    chzzk = chzzk_event({"uid": "a" * 32, "profile": json.dumps({"nickname": "치즈냥"}), "msg": "!출석"})
    assert chzzk.user == "a" * 32 and chzzk.name == "치즈냥"
    assert chzzk_api_event("CHAT", {"senderChannelId": "b" * 32, "profile": {"nickname": "x"}, "content": "hi"}).user == "b" * 32
    assert chzzk_api_event("DONATION", {"donatorChannelId": "c1", "payAmount": "1000"}).user == "c1"
    packet = b"\x1b\t" + b"0005" + b"0" * 8 + "\x0c".join(["", "!출석", "soopid(2)", "", "", "", "숲닉"]).encode("utf-8")
    soop = soop_event(packet)
    assert soop.user == "soopid" and soop.name == "숲닉"
    twitch = twitch_event("@badges=;display-name=Haru;user-id=12345 :haru!haru@haru.tmi.twitch.tv PRIVMSG #ch :!출석")
    assert twitch.user == "12345"
    youtube = youtube_event({"snippet": {"type": "textMessageEvent", "displayMessage": "hi", "publishedAt": "2026-11-26T00:00:00Z"},
                             "authorDetails": {"displayName": "유튜버", "channelId": "UCxyz"}})
    assert youtube.user == "UCxyz"
    assert OverlayEvent("demo", "chat", "x").to_dict()["user"] == ""


# --------------------------------------------------------------------------- Cloudflare 올리기


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeCloudflare:
    """REST API 흉내: 받은 요청을 기록하고 경로별로 답한다."""

    def __init__(self, *, subdomain="dotori", existing=False, fail=None):
        self.calls = []
        self.subdomain = subdomain
        self.existing = existing
        self.fail = fail

    def __call__(self, request, timeout=0):
        method, url = request.get_method(), request.full_url
        path = url.replace(cloudflare.API, "")
        body = request.data or b""
        self.calls.append((method, path, body, request.headers))
        if self.fail and self.fail in path:
            payload = json.dumps({"success": False, "errors": [{"code": 10000, "message": "Authentication error"}]}).encode()
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, io.BytesIO(payload))
        result = None
        if path.startswith("/accounts?"):
            result = [{"id": "acc1", "name": "내 계정"}]
        elif "/d1/database?" in path:
            result = [{"name": "dotori-fans-db", "uuid": "db-old"}] if self.existing else []
        elif path.endswith("/d1/database") and method == "POST":
            result = {"uuid": "db-new"}
        elif "/query" in path:
            result = [{"success": True}]
        elif "/storage/kv/namespaces?" in path:
            result = [{"title": "dotori-fans-files", "id": "kv-old"}] if self.existing else []
        elif path.endswith("/storage/kv/namespaces"):
            result = {"id": "kv-new"}
        elif path.endswith("/workers/subdomain") and method == "GET":
            if not self.subdomain:
                payload = json.dumps({"success": False, "errors": [{"code": 10007, "message": "not found"}]}).encode()
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(payload))
            result = {"subdomain": self.subdomain}
        elif path.endswith("/workers/subdomain") and method == "PUT":
            result = {"subdomain": json.loads(body)["subdomain"]}
        else:
            result = {}
        return FakeResponse(json.dumps({"success": True, "result": result}).encode())


def test_deploy_creates_storage_uploads_worker_and_turns_on_the_address():
    fake = FakeCloudflare(subdomain="")
    cf = cloudflare.Cloudflare("t" * 40, opener=fake)
    done = cloudflare.deploy(cf, "Dotori-Fans", secrets_={"ADMIN_TOKEN_HASH": "h", "SESSION_KEY": "s", "DISCORD_CLIENT_ID": ""})
    assert done.url == "https://dotori-fans.dotori-fans.workers.dev" and (done.database, done.kv, done.account) == ("db-new", "kv-new", "acc1")
    paths = [(method, path.split("?")[0]) for method, path, _, _ in fake.calls]
    assert paths[0] == ("GET", "/accounts") and ("POST", "/accounts/acc1/d1/database") in paths
    queries = [json.loads(body)["sql"] for method, path, body, _ in fake.calls if path.endswith("/query")]
    assert len(queries) == len(cloudflare.schema_statements()) and all("CREATE" in sql for sql in queries)
    upload = next(call for call in fake.calls if call[0] == "PUT" and "/workers/scripts/dotori-fans" in call[1])
    content_type = upload[3]["Content-type"]
    assert content_type.startswith("multipart/form-data; boundary=")
    text = upload[2].decode("utf-8")
    metadata = json.loads(text.split("application/json\r\n\r\n", 1)[1].split("\r\n--", 1)[0])
    assert metadata["main_module"] == "worker.js" and metadata["compatibility_date"]
    bindings = {item["name"]: item for item in metadata["bindings"]}
    assert bindings["DB"] == {"type": "d1", "name": "DB", "id": "db-new"} and bindings["FILES"]["namespace_id"] == "kv-new"
    assert bindings["ADMIN_TOKEN_HASH"]["type"] == "secret_text" and "DISCORD_CLIENT_ID" not in bindings  # 빈 값은 넣지 않음
    assert 'filename="worker.js"' in text and "application/javascript+module" in text and "export default" in text
    assert ("PUT", "/accounts/acc1/workers/subdomain") in paths and paths[-1] == ("POST", "/accounts/acc1/workers/scripts/dotori-fans/subdomain")
    # 다시 올리면 있는 저장소를 그대로 씀
    again = FakeCloudflare(existing=True)
    redone = cloudflare.deploy(cloudflare.Cloudflare("t" * 40, opener=again), "dotori-fans", secrets_={})
    assert (redone.database, redone.kv, redone.url) == ("db-old", "kv-old", "https://dotori-fans.dotori.workers.dev")
    assert not any(method == "POST" and path.endswith("/d1/database") for method, path, _, _ in again.calls)


def test_deploy_errors_are_explained():
    with pytest.raises(cloudflare.CloudflareError, match="주소 이름은"):
        cloudflare.check_script("한글")
    with pytest.raises(cloudflare.CloudflareError, match="토큰이 비어"):
        cloudflare.Cloudflare("")
    cf = cloudflare.Cloudflare("t" * 40, opener=FakeCloudflare(fail="/d1/"))
    with pytest.raises(cloudflare.CloudflareError, match="권한 부족"):
        cloudflare.deploy(cf, "dotori-fans", secrets_={})
    assert all(not statement.startswith("--") for statement in cloudflare.schema_statements())


def memory_box(tmp_path):
    return KeyBox(tmp_path / "keys.json", b"t", "t", protect=lambda raw: raw[::-1], unprotect=lambda raw: raw[::-1])


def test_publish_keeps_tokens_secret_and_reuses_them(tmp_path, monkeypatch):
    box = memory_box(tmp_path)
    fakes = []

    def make(token):
        fakes.append(token)
        return cloudflare.Cloudflare(token, opener=FakeCloudflare())

    sent = []
    monkeypatch.setattr(Community, "settings", lambda self, **values: sent.append(values) or {"ok": True})
    done = setup.publish("dotori-fans", cloudflare_token="t" * 40, name="도토리네", owner_name="도토리", box=box, make_cloudflare=make,
                         providers={"discord": {"id": "123", "secret": "sec"}, "google": {"id": "g", "secret": ""}})
    assert done["url"] == "https://dotori-fans.dotori.workers.dev" and done["providers"] == ["discord"] and done["note"] == ""
    admin = box.load("admin_token")
    assert admin and box.load("cloudflare_token") == "t" * 40 and box.load("discord_secret") == "sec"
    saved = json.loads(community.settings.data_path(community.DATA).read_text(encoding="utf-8"))
    assert "t" * 40 not in json.dumps(saved) and admin not in json.dumps(saved) and saved["provider_ids"] == {"discord": "123"}
    assert sent[0]["providers"] == "discord" and sent[0]["name"] == "도토리네" and sent[0]["owner_name"] == "도토리" and "primary" in sent[0]["theme"]
    # 다시 올리기: 저장한 토큰과 로그인 키를 그대로, 같은 관리 토큰
    setup.publish("", box=box, make_cloudflare=make)
    assert fakes == ["t" * 40, "t" * 40] and box.load("admin_token") == admin and community.load()["providers"] == ["discord"]
    # 처음 올린 주소가 아직 열리지 않으면 다음에 다시 보냄
    monkeypatch.setattr(Community, "settings", lambda self, **values: (_ for _ in ()).throw(CommunityError("연결 안 됨")))
    assert "아직 연결되지 않음" in setup.publish("", box=box, make_cloudflare=make)["note"] and community.load()["sync"] is True
    with pytest.raises(cloudflare.CloudflareError, match="토큰 필요"):
        setup.publish("x-y-z", box=memory_box(tmp_path / "empty"), make_cloudflare=make)
    # Worker에는 관리 토큰 대신 SHA-256만 올라감
    fake = FakeCloudflare()
    setup.publish("", box=box, make_cloudflare=lambda token: cloudflare.Cloudflare(token, opener=fake))
    upload = next(body.decode("utf-8") for method, path, body, _ in fake.calls if method == "PUT" and "/workers/scripts/" in path)
    assert hashlib.sha256(admin.encode()).hexdigest() in upload and admin not in upload


# --------------------------------------------------------------------------- 커뮤니티 API


def test_client_sends_token_and_explains_errors():
    seen = []

    def opener(request, timeout=0):
        seen.append(request)
        if request.full_url.endswith("/api/state"):
            return FakeResponse(json.dumps({"name": "x", "users": 1}).encode())
        raise urllib.error.HTTPError(request.full_url, 401, "no", {}, io.BytesIO(b'{"error": "x"}'))

    api = Community("https://fans.example.workers.dev/", "tok", opener=opener)
    assert api.state()["users"] == 1 and seen[0].headers["Authorization"] == "Bearer tok"
    with pytest.raises(CommunityError, match="토큰이 맞지 않음"):
        api.post("공지")
    with pytest.raises(CommunityError, match="https"):
        Community("http://evil.example", "t")


# --------------------------------------------------------------------------- 방송 연동


class FakeApi:
    def __init__(self):
        self.calls = []
        self.stage_items = [{"post": 3, "board": "fanart", "title": "팬아트", "body": "", "author": "그림쟁이", "image": "https://x/img/a", "url": "https://x/p/3"}]
        self.entries = [{"id": 1, "name": "커뮤참가자", "at": 9_999_999_999_999}]
        self.timeout = 10

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if name == "chat":
                return {"ok": True, "given": 10, "points": 30, "name": "도토리"} if args[0] == "attend" else {"ok": True}
            if name == "stage":
                items, self.stage_items = self.stage_items, []
                return items
            if name == "raffle_entries":
                return self.entries
            if name == "state":
                return {"name": "x", "users": 2, "posts": 1, "reports": 0, "attended": 1}
            return {"ok": True}
        return call


def configure():
    config = community.load()
    config.update(url="https://fans.example.workers.dev")
    community.save(config)


def test_chat_commands_live_stage_and_raffle_sync():
    configure()
    api = FakeApi()
    raffle = Raffle()
    link = link_module.CommunityLink(feature.Context(notify=lambda text: None, raffle=raffle), make_client=lambda: api, start=False)
    link.tap(OverlayEvent("chzzk", "chat", "도토리", (("text", "!인증 123456"),), user="ch1", role="moderator"))
    link.tap(OverlayEvent("youtube", "chat", "유튜버", (("text", "!출석"),), user="UC1"))
    link.tap(OverlayEvent("chzzk", "chat", "그냥", (("text", "안녕 !출석"),), user="x"))
    jobs = []
    while not link.jobs.empty():
        jobs.append(link.jobs.get_nowait())
    assert [kind for kind, _ in jobs] == ["live", "verify", "attend"]
    # 시험 채팅은 인증, 출석만(방송 중 표시는 실제 플랫폼만)
    fresh = link_module.CommunityLink(feature.Context(notify=lambda text: None), make_client=lambda: api, start=False)
    fresh.tap(OverlayEvent("demo", "chat", "시험", (("text", "!출석"),)))
    fresh.tap(DemoChat(seed=1).make())  # 데모 채팅(플랫폼 이름만 진짜)도 방송 중으로 치지 않음
    assert [fresh.jobs.get_nowait()[0]] == ["attend"] and fresh.jobs.empty()
    assert jobs[1][1] == {"platform": "chzzk", "user": "ch1", "name": "도토리", "role": "moderator", "code": "123456"}
    subscriber, _ = link.channel.subscribe()
    for kind, data in jobs:
        link._job(api, kind, data)
    assert [name for name, _, _ in api.calls] == ["live", "chat", "chat"] and link.status["live"] is True
    shown = subscriber.get_nowait()
    assert shown["item"]["kind"] == "attend" and "+10점" in shown["item"]["body"]
    # 방송에 띄우기, 참여 추첨 맞추기
    raffle.start("!참가", "굿즈 추첨")
    link.poll(api)
    assert subscriber.get_nowait()["item"]["title"] == "팬아트"
    assert ("raffle", (True, "굿즈 추첨"), {}) in api.calls and [entry["name"] for entry in raffle.status()["entries"]] == ["커뮤참가자"]
    assert raffle.status()["entries"][0]["platform"] == "community"
    raffle.stop()
    link.poll(api)
    assert ("raffle", (False, "굿즈 추첨"), {}) in api.calls
    link.stop()
    assert api.calls[-1][0] == "live" and api.calls[-1][1] == (False,)


def test_auto_options_turn_parts_off():
    configure()
    config = community.load()
    config["auto"] = {**config["auto"], "verify": False, "live": False}
    community.save(config)
    link = link_module.CommunityLink(feature.Context(notify=lambda text: None), make_client=lambda: None, start=False)
    link.tap(OverlayEvent("chzzk", "chat", "a", (("text", "!인증 123456"),), user="1"))
    link.tap(OverlayEvent("chzzk", "chat", "a", (("text", "!출석"),), user="1"))
    assert [link.jobs.get_nowait()[0]] == ["attend"] and link.jobs.empty()


def request(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, data


def test_control_routes_before_deploy():
    server = OverlayServer([], port=0).start()
    try:
        status, body = request(server.port, "GET", "/community/config")
        config = json.loads(body)
        assert status == 200 and config["url"] == "" and config["keys"]["cloudflare"] is False and config["auto"]["verify"] is True
        status, body = request(server.port, "POST", "/community/notice", {"title": "x"})
        assert status == 400 and "먼저 올리기" in json.loads(body)["error"]
        status, body = request(server.port, "POST", "/community/options", {"stage_seconds": 99})
        assert status == 400 and "4초에서 60초" in json.loads(body)["error"]
        assert request(server.port, "POST", "/community/options", {"live_url": "https://chzzk.naver.com/live/x", "auto": {"raffle": False}})[0] == 200
        assert community.load()["live_url"] == "https://chzzk.naver.com/live/x" and community.load()["auto"]["raffle"] is False
        for path, marker in (("/community", b"debutkitLive.subscribe"), ("/community/control", b"/community/deploy")):
            status, body = request(server.port, "GET", path)
            assert status == 200 and marker in body, path
        assert b'"/community/control"' in request(server.port, "GET", "/ui.js")[1]
    finally:
        server.stop()


# --------------------------------------------------------------------------- Worker(Node)


def node_with_sqlite():
    node = shutil.which("node")
    if not node:
        return None
    version = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v").split(".")
    return node if (int(version[0]), int(version[1])) >= (22, 5) else None


@pytest.mark.skipif(node_with_sqlite() is None, reason="Node.js 22.5 이상 필요(내장 SQLite)")
def test_worker_with_node():
    result = subprocess.run([node_with_sqlite(), "--test", str(ROOT / "tests" / "community_worker.test.mjs")], capture_output=True, text=True,
                            encoding="utf-8", cwd=ROOT, timeout=180)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]
    assert "fail 0" in result.stdout
