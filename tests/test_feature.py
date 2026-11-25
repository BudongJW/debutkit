import http.client
import json

import pytest

from debutkit import settings
from debutkit.overlay import feature
from debutkit.overlay.events import OverlayEvent
from debutkit.overlay.server import Hub, OverlayServer, make_handler


def request(port, method, path, body=None, raw=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    payload = raw if raw is not None else json.dumps(body).encode() if body is not None else None
    conn.request(method, path, body=payload, headers={"Content-Type": "application/json", **(headers or {})})
    response = conn.getresponse()
    return response.status, response.getheader("Content-Type"), response.read()


def sample(seen):
    channel = feature.Channel({"seq": 0, "hello": True})

    def save(data):
        if data.get("bad"):
            raise feature.FeatureError("잘못된 값")
        if data.get("missing"):
            raise feature.FeatureError("없음", 404)
        if data.get("disk"):
            raise OSError("디스크 가득 참")
        channel.publish({"seq": 1, "value": data.get("value")})
        return {"saved": data.get("value")}

    return feature.Feature(
        name="sample",
        static={"/sample": "draw.html"},
        get={"/sample/state": lambda query: {"q": query.get("x", [""])[0]}, "/sample/image.svg": lambda query: feature.Raw(b"<svg/>", "image/svg+xml")},
        post={"/sample/save": save},
        feeds={"sample": channel},
        taps=[seen.append],
        body_limit={"/sample/save": 100_000},
        stop=lambda: seen.append("stopped"),
    )


@pytest.fixture
def server(monkeypatch):
    seen = []
    monkeypatch.setattr(feature, "default_features", lambda context: [sample(seen)])
    srv = OverlayServer([], port=0).start()
    yield srv, seen
    srv.stop()


def test_feature_routes_errors_feeds_taps_and_stop(server):
    srv, seen = server
    port = srv.port
    status, _, body = request(port, "GET", "/sample")
    assert status == 200 and b"/draw.js" in body
    assert json.loads(request(port, "GET", "/sample/state?x=%ED%95%9C")[2]) == {"q": "한"}
    assert request(port, "GET", "/sample/image.svg")[1] == "image/svg+xml"
    assert json.loads(request(port, "POST", "/sample/save", {"value": 3})[2]) == {"saved": 3}
    status, _, body = request(port, "POST", "/sample/save", {"bad": True})
    assert status == 400 and json.loads(body)["error"] == "잘못된 값"
    assert request(port, "POST", "/sample/save", {"missing": True})[0] == 404
    status, _, body = request(port, "POST", "/sample/save", {"disk": True})
    assert status == 500 and "디스크" in json.loads(body)["error"]
    big = {"value": "가" * 10000}  # 기본 한도(4096)보다 큰 본문도 기능이 정한 한도까지 받음
    assert json.loads(request(port, "POST", "/sample/save", big)[2]) == {"saved": "가" * 10000}
    assert request(port, "POST", "/sample/other", {})[0] == 404
    assert request(port, "GET", "/sample/state", headers={"Origin": "https://evil.example"})[0] == 403

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/live?feeds=sample")
    stream = conn.getresponse()
    assert stream.fp.readline().decode().strip() == "event: sample"
    assert json.loads(stream.fp.readline().decode().removeprefix("data: "))["value"] == "가" * 10000
    stream.close()
    conn.close()

    srv.hub.publish(OverlayEvent("soop", "donation", "시청자", (), amount=10.0, unit="별풍선"))
    assert seen and seen[-1].name == "시청자"
    srv.stop()
    assert seen[-1] == "stopped"


def test_duplicate_paths_and_feeds_are_refused():
    def part(name, **changes):
        return feature.Feature(name=name, **changes)

    with pytest.raises(ValueError, match="/draw"):
        make_handler(Hub(), lambda: 0, features=[part("a", static={"/draw": "x.html"})])
    with pytest.raises(ValueError, match="/raffle/start"):
        make_handler(Hub(), lambda: 0, features=[part("a", post={"/raffle/start": print})])
    with pytest.raises(ValueError, match="/x"):
        make_handler(Hub(), lambda: 0, features=[part("a", get={"/x": print}), part("b", static={"/x": "x.html"})])
    with pytest.raises(ValueError, match="draw"):
        make_handler(Hub(), lambda: 0, features=[part("a", feeds={"draw": feature.Channel()})])


def test_channel_keeps_last_value_and_drops_for_full_queues():
    channel = feature.Channel()
    stuck = __import__("queue").Queue(maxsize=1)
    channel.subscribe(stuck)
    channel.publish({"seq": 1})
    channel.publish({"seq": 2})  # 가득 찬 대기열은 건너뜀
    channel.publish({"seq": 3, "flash": True}, keep=False)
    _, current = channel.subscribe()
    assert current == {"seq": 2} and stuck.get_nowait() == {"seq": 1} and channel.listeners == 2


def test_feature_data_files(tmp_path):
    assert settings.load_data("pick.json") == {}
    path = settings.save_data("pick.json", {"cells": 9, "이름": "뽑기"})
    assert path.parent == settings.settings_path().parent and settings.load_data("pick.json") == {"cells": 9, "이름": "뽑기"}
    path.write_text("broken", encoding="utf-8")
    assert settings.load_data("pick.json") == {}
    for bad in ("", "../x.json", "a/b.json", ".hidden"):
        with pytest.raises(ValueError):
            settings.data_path(bad)
