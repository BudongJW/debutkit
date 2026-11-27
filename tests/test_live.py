"""방송 화면의 공유 연결(live.js, live-worker.js)과 /live의 events 항목."""

import http.client
import json
from pathlib import Path

import pytest

from debutkit.overlay.events import OverlayEvent
from debutkit.overlay.server import OverlayServer

STATIC = Path(__file__).resolve().parent.parent / "src" / "debutkit" / "overlay" / "static"
#: OBS 브라우저 소스로 쓰는 방송 화면: 모두 공유 연결 하나로 받는다(브라우저의 같은 주소 동시 연결 6개 제한)
OVERLAYS = {"chat.html": "overlay.js", "alerts.html": "overlay.js", "character.html": "character.js", "draw.html": "draw.js", "pick.html": "pick.js",
            "wall.html": "wall.js", "race.html": "race.js", "camera-view.html": "camera-view.js"}


@pytest.mark.parametrize("page, script", OVERLAYS.items())
def test_overlays_share_one_connection(page, script):
    html = (STATIC / page).read_text(encoding="utf-8")
    assert '<script src="/live.js"></script>' in html and html.index("/live.js") < html.index(f"/{script}")
    code = (STATIC / script).read_text(encoding="utf-8")
    assert "debutkitLive.subscribe" in code
    if script != "overlay.js":  # overlay.js는 live.js가 없을 때만 /events 에 직접 연결
        assert "new EventSource(" not in code


def test_program_and_stage_use_the_same_overlays():
    program = (STATIC / "program.html").read_text(encoding="utf-8")
    stage = (STATIC / "stage.html").read_text(encoding="utf-8")
    for path in ("/wall", "/pick", "/race", "/wall/goal", "/wall/rank", "/chat", "/alerts", "/draw", "/character"):
        assert f'"{path}"' in program and f'"{path}"' in stage, path


def read_event(stream):
    name = stream.fp.readline().decode().strip().removeprefix("event: ")
    data = json.loads(stream.fp.readline().decode().removeprefix("data: "))
    stream.fp.readline()
    return name, data


def test_events_feed_sends_history_then_new_events():
    server = OverlayServer([], port=0).start()
    try:
        server.hub.publish(OverlayEvent("chzzk", "chat", "치즈냥", (("text", "안녕"),)))
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        conn.request("GET", "/live?feeds=events,theme")
        stream = conn.getresponse()
        first = dict([read_event(stream), read_event(stream)])
        assert [event["name"] for event in first["events"]["history"]] == ["치즈냥"] and first["events"]["history"][0]["replay"] is True
        assert first["theme"]["primary"] == "#ff4f8b"
        server.hub.publish(OverlayEvent("soop", "donation", "숲속토끼", (), amount=10.0, unit="별풍선"))
        name, data = read_event(stream)
        assert name == "events" and data["name"] == "숲속토끼" and data["replay"] is False and data["unit"] == "별풍선"
        stream.close()
        conn.close()
        for path, kind in (("/live.js", "javascript"), ("/live-worker.js", "javascript"), ("/theme.css", "css"), ("/ui.css", "css")):
            conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
            conn.request("GET", path)
            response = conn.getresponse()
            assert response.status == 200 and kind in response.getheader("Content-Type"), path
            conn.close()
    finally:
        server.stop()
