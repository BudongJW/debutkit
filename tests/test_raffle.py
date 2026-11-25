"""시청자 참여 추첨과 스트리머, 매니저 채팅 명령."""

import http.client
import json
import random

import pytest
from model_fake import vrma

from debutkit import cli, commands, motion, raffle, settings
from debutkit.overlay.events import OverlayEvent, system_event
from debutkit.overlay.server import OverlayServer


def chat(text, name="시청자", platform="chzzk", role=""):
    return OverlayEvent(platform, "chat", name, (("text", text),), role=role)


def test_start_validation_and_saved_options():
    box = raffle.Raffle(rng=random.Random(1))
    assert box.keyword == "!참가" and box.title == "시청자 추첨" and not box.open
    for keyword in ("참가", "!", "!참 가", "!" + "가" * 20):
        with pytest.raises(raffle.RaffleError, match="!로 시작"):
            box.start(keyword)
    with pytest.raises(raffle.RaffleError, match="20자 이내"):
        box.start("!참가", "가" * 21)
    with pytest.raises(raffle.RaffleError, match="0 이상의 정수"):
        box.start("!참가", "추첨", -5)
    status = box.start("!들어감", "  노래 순서  ", 1000)
    assert status["open"] and status["keyword"] == "!들어감" and status["title"] == "노래 순서" and status["donation_min"] == 1000
    saved = settings.load()
    assert (saved["raffle_command"], saved["raffle_title"], saved["raffle_donation_min"]) == ("!들어감", "노래 순서", 1000)
    again = raffle.Raffle()
    assert (again.keyword, again.title, again.donation_min) == ("!들어감", "노래 순서", 1000)
    box.start(donation_min=None)
    assert box.donation_min is None and "raffle_donation_min" not in settings.load() and box.keyword == "!들어감"
    assert raffle.saved_options({"raffle_command": "잘못", "raffle_title": " "})["keyword"] == "!참가"


def test_entries_draw_and_events():
    box = raffle.Raffle(rng=random.Random(3))
    subscriber, current = box.subscribe()
    assert current["type"] == "status" and current["open"] is False
    assert box.add("직접", "manual") is True  # 직접 추가는 모집 전에도 가능
    assert box.add("채팅", "chzzk", "chat") is False  # 모집 전 채팅 참가는 안 됨
    box.start()
    assert box.status()["count"] == 0  # 새 모집은 지난 명단 삭제
    for index in range(5):
        assert box.add(f"시청자{index}", "soop", "chat")
    assert box.add("시청자0", "soop", "chat") is False and box.add("시청자0", "twitch", "chat") is True and box.add(" ", "soop", "chat") is False
    events = []
    while not subscriber.empty():
        events.append(subscriber.get_nowait())
    assert events[-1]["joined"] == {"name": "시청자0", "platform": "twitch", "source": "chat"} and events[-1]["count"] == 6
    assert box.remove("soop:시청자1") and not box.remove("soop:없음")
    subscriber.get_nowait()  # 삭제 알림
    with pytest.raises(raffle.RaffleError, match="1에서 30"):
        box.draw(0)
    with pytest.raises(raffle.RaffleError, match="pick"):
        box.draw(1, "lottery")
    result = box.draw(3)
    assert result["type"] == "result" and result["mode"] == "pick" and result["total"] == 5 and len(result["winners"]) == 3
    assert len({winner["name"] + winner["platform"] for winner in result["winners"]}) == 3
    assert box.open is False and box.current["type"] == "status"  # 결과는 현재 값으로 남기지 않음(다시 연결해도 재생 안 됨)
    assert subscriber.get_nowait()["type"] == "status" and subscriber.get_nowait() == result
    order = box.draw(mode="order")
    assert order["mode"] == "order" and len(order["winners"]) == 5 and order["more"] == 0 and box.status()["last_result"] == order
    assert len(box.draw(30)["winners"]) == 5  # 참가자보다 많이 요청하면 전원
    box.clear()
    with pytest.raises(raffle.RaffleError, match="참가자가 없음"):
        box.draw(1)
    box.unsubscribe(subscriber)


def test_order_shows_up_to_30_and_entries_are_capped(monkeypatch):
    monkeypatch.setattr(raffle, "MAX_ENTRIES", 40)
    box = raffle.Raffle(rng=random.Random(5))
    box.start()
    for index in range(45):
        box.add(f"v{index}", "youtube", "chat")
    assert box.status()["count"] == 40
    order = box.draw(mode="order")
    assert len(order["winners"]) == 30 and order["more"] == 10


def test_reactor_matches_keyword_and_donations():
    box = raffle.Raffle(rng=random.Random(2))
    reactor = raffle.RaffleReactor(box)
    reactor(chat("!참가"))
    assert box.status()["count"] == 0  # 모집 전
    box.start("!참가", donation_min=1000)
    reactor(chat("!참가 저요", name="a"))
    reactor(chat("  !참가", name="b", platform="soop"))
    reactor(chat("참가", name="c"))
    reactor(chat("!참가하기", name="d"))
    reactor(OverlayEvent("soop", "donation", "e", (), amount=10.0, unit="별풍선"))  # 1,000원
    reactor(OverlayEvent("soop", "donation", "f", (), amount=9.0, unit="별풍선"))
    reactor(OverlayEvent("twitch", "donation", "g", (), amount=500.0, unit="bits"))  # 원 환산 불가
    reactor(system_event("!참가"))
    names = [(entry["name"], entry["source"]) for entry in box.status()["entries"]]
    assert names == [("a", "chat"), ("b", "chat"), ("e", "donation")]
    box.start("!JOIN", donation_min=0)
    reactor(chat("!join", name="h", platform="twitch"))
    reactor(OverlayEvent("twitch", "donation", "g", (), amount=500.0, unit="bits"))
    assert [entry["name"] for entry in box.status()["entries"]] == ["h", "g"]


def test_chat_commands_from_streamer_and_manager(tmp_path):
    added, _ = motion.add(vrma(tmp_path / "wave.vrma"), name="손 흔들기")
    played, notes = [], []
    state = type("State", (), {"play": lambda self, motion_id: played.append(motion_id)})()
    box = raffle.Raffle(rng=random.Random(4))
    triggered = []

    class FakeClient:
        def trigger(self, hotkey):
            triggered.append(hotkey)

        def close(self):
            pass

    worker = commands.HotkeyWorker(notes.append, connect=lambda: FakeClient())
    handler = commands.ChatCommands(motion_state=state, raffle_state=box, notify=notes.append, hotkeys=worker, has_token=lambda: True)
    handler(chat("!동작 손 흔들기"))  # 일반 시청자: 무시
    assert played == [] and notes == []
    handler(chat("!동작 흔들", role="moderator", name="매니저"))
    handler(chat(f"!동작 {added[0].id}", role="owner"))
    handler(chat("!동작 없는동작", role="owner"))
    assert played == [added[0].id, added[0].id] and "동작 손 흔들기 실행(매니저)" in notes[0] and "등록한 동작 없음" in notes[2]
    handler(chat("!단축키 Heart", role="owner"))
    worker.stop()
    assert triggered == ["Heart"] and any("Heart 실행" in line for line in notes)
    handler(chat("!단축키", role="owner"))
    assert "단축키 이름" in notes[-1]
    handler(chat("!모집", role="owner"))
    assert box.open and "채팅에 !참가" in notes[-1]
    for index in range(4):
        box.add(f"v{index}", "chzzk", "chat")
    handler(chat("!마감", role="moderator"))
    assert not box.open and "참가 4명" in notes[-1]
    handler(chat("!추첨 2", role="owner"))
    assert box.status()["last_result"]["mode"] == "pick" and len(box.status()["last_result"]["winners"]) == 2
    handler(chat("!순서", role="owner"))
    assert box.status()["last_result"]["mode"] == "order"
    handler(chat("!clip", role="owner"))  # 다른 명령은 처리하지 않음
    assert notes[-1].startswith("채팅 명령: 참가자 4명 순서")


def test_chat_commands_off_and_without_vts_token():
    notes = []
    box = raffle.Raffle()
    off = commands.ChatCommands(motion_state=None, raffle_state=box, notify=notes.append, enabled=False)
    off(chat("!모집", role="owner"))
    assert not box.open
    settings.save({"chat_commands": False})
    saved_off = commands.ChatCommands(motion_state=None, raffle_state=box, notify=notes.append)
    saved_off(chat("!모집", role="owner"))
    assert not box.open
    settings.save({"chat_commands": True})
    on = commands.ChatCommands(motion_state=None, raffle_state=box, notify=notes.append, has_token=lambda: False)
    on(chat("!단축키 Heart", role="owner"))
    assert "VTube Studio 연결 전" in notes[-1]
    on(chat("!추첨", role="owner"))
    assert "참가자가 없음" in notes[-1]


@pytest.fixture
def server():
    srv = OverlayServer([], port=0).start()
    yield srv
    srv.stop()


def request(srv, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    return response.status, json.loads(response.read() or b"{}")


def test_server_endpoints_live_feed_and_hub(server):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.request("GET", "/live?feeds=raffle")
    stream = conn.getresponse()

    def event():
        name = stream.fp.readline().decode().strip().removeprefix("event: ")
        data = json.loads(stream.fp.readline().decode().removeprefix("data: "))
        stream.fp.readline()
        return name, data

    name, data = event()
    assert name == "raffle" and data["type"] == "status" and data["open"] is False
    status, body = request(server, "POST", "/raffle/start", {"keyword": "!참가", "title": "노래 신청", "donation_min": None})
    assert status == 200 and body["open"] and body["title"] == "노래 신청"
    assert event()[1]["open"] is True
    server.hub.publish(chat("!참가", name="고양이집사", platform="soop"))
    name, data = event()
    assert data["joined"]["name"] == "고양이집사" and data["count"] == 1
    server.hub.publish(chat("!모집", name="매니저", role="moderator"))  # 채팅 명령도 같은 서버에서 처리(새 모집)
    assert event()[1]["count"] == 0
    for name_ in ("a", "b", "c"):
        assert request(server, "POST", "/raffle/add", {"name": name_})[0] == 200
    assert request(server, "POST", "/raffle/add", {"name": "a"})[0] == 400
    status, body = request(server, "GET", "/raffle")
    assert status == 200 and [entry["name"] for entry in body["entries"]] == ["a", "b", "c"] and body["modes"]["order"] == "순서 정하기"
    assert request(server, "POST", "/raffle/remove", {"key": "manual:b"})[1]["count"] == 2
    for _ in range(3):  # 직접 추가 3번, 삭제 1번의 상태 알림
        event()
    status, result = request(server, "POST", "/raffle/draw", {"count": 1, "mode": "pick"})
    assert status == 200 and result["winners"][0]["name"] in ("a", "c")
    name, data = event()
    while data["type"] != "result":
        name, data = event()
    assert data["seq"] == result["seq"]
    assert request(server, "POST", "/raffle/draw", {"count": "많이"})[0] == 400
    assert request(server, "POST", "/raffle/stop")[1]["open"] is False
    assert request(server, "POST", "/raffle/clear")[1]["count"] == 0
    stream.close()
    conn.close()


def test_cli_raffle_and_overlay_flag(capsys):
    assert cli.build_parser().parse_args(["overlay", "--no-chat-commands"]).no_chat_commands is True
    srv = OverlayServer([], port=0, chat_commands=False).start()
    try:
        srv.hub.publish(chat("!모집", role="owner"))
        assert not srv.raffle.open  # 명령줄에서 끈 경우
        port = str(srv.port)
        assert cli.main(["raffle", "--port", port, "start", "--keyword", "!참가", "--title", "시청자 추첨", "--donation-min", "5000"]) == 0
        assert "모집 중: 시청자 추첨, 참가 명령 !참가, 참가 0명, 5,000원 이상 후원 참가" in capsys.readouterr().out
        for name in ("하나", "둘"):
            srv.hub.publish(chat("!참가", name=name))
        assert cli.main(["raffle", "--port", port, "status"]) == 0 and "하나" in capsys.readouterr().out
        assert cli.main(["raffle", "--port", port, "draw", "--order"]) == 0 and "순서(참가 2명): 1 " in capsys.readouterr().out
        assert cli.main(["raffle", "--port", port, "draw", "40"]) == 1 and "1에서 30" in capsys.readouterr().err
        assert cli.main(["raffle", "--port", port, "start", "--donation-min", "-1"]) == 0 and "후원 참가" not in capsys.readouterr().out
        assert cli.main(["raffle", "--port", port, "stop"]) == 0 and "모집 마감" in capsys.readouterr().out
    finally:
        srv.stop()
    assert cli.main(["raffle", "--port", port, "status"]) == 1 and "오버레이에 연결하지 못함" in capsys.readouterr().err


def test_overlay_page_handles_raffle():
    from pathlib import Path

    static = Path(raffle.__file__).parent / "overlay" / "static"
    script = (static / "draw.js").read_text(encoding="utf-8")
    assert 'subscribe(["draw", "raffle", "theme"]' in script and "acceptRaffle" in script and 'band: "당첨"' in script
    assert 'id="raffle"' in (static / "draw.html").read_text(encoding="utf-8")
    control = (static / "draw-control.html").read_text(encoding="utf-8")
    assert "/raffle/start" in control and "/raffle/draw" in control and "!모집" in control
