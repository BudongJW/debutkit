import http.client
import json
import threading
import time

import pytest

from debutkit.overlay.events import (
    DemoChat,
    OverlayEvent,
    chzzk_api_event,
    chzzk_event,
    chzzk_frame,
    soop_event,
    text_parts,
    twitch_event,
)
from debutkit.overlay.server import Hub, OverlayServer

# ---------------------------------------------------------------------------- 변환


def test_text_parts_splits_emotes_and_rejects_non_https():
    parts = text_parts("안녕{:cheese:}하세요{:bad:}", {"cheese": "https://ssl.pstatic.net/a.png", "bad": "javascript:alert(1)"})
    assert parts == (("text", "안녕"), ("emote", "https://ssl.pstatic.net/a.png"), ("text", "하세요{:bad:}"))


def chzzk_item(**overrides):
    item = {"msg": "ㅋㅋㅋ {:smile:}", "msgTime": 1763700000000, "msgTypeCode": 1, "msgStatusType": "NORMAL",
            "profile": json.dumps({"nickname": "치즈냥", "userRoleCode": "common_user"}),
            "extras": json.dumps({"emojis": {"smile": "https://nng-phinf.pstatic.net/smile.png"}})}
    item.update(overrides)
    return item


def test_chzzk_chat_keeps_nickname_and_emotes():
    event = chzzk_event(chzzk_item())
    assert event.platform == "chzzk" and event.kind == "chat" and event.name == "치즈냥"
    assert event.parts == (("text", "ㅋㅋㅋ "), ("emote", "https://nng-phinf.pstatic.net/smile.png"))
    assert event.time == 1763700000.0


def test_chzzk_donation_and_roles():
    donation = chzzk_event(chzzk_item(msg="응원해요", msgTypeCode=10, extras=json.dumps({"payAmount": 5000})), donation=True)
    assert donation.kind == "donation" and donation.amount == 5000 and donation.unit == "원"
    anonymous = chzzk_event(chzzk_item(profile="", msgTypeCode=10, extras=json.dumps({"payAmount": 1000})))
    assert anonymous.name == "익명 후원자"
    owner = chzzk_event(chzzk_item(profile=json.dumps({"nickname": "나", "userRoleCode": "streamer"})))
    assert owner.role == "owner"
    assert chzzk_event(chzzk_item(msgStatusType="HIDDEN")) is None


def test_chzzk_frame_picks_chat_and_donation_commands():
    frame = json.dumps({"cmd": 93101, "bdy": [chzzk_item(), chzzk_item(msgStatusType="HIDDEN")]})
    assert [event.name for event in chzzk_frame(frame)] == ["치즈냥"]
    assert chzzk_frame(json.dumps({"cmd": 0})) == []
    assert chzzk_frame("not json") == []
    donation = chzzk_frame(json.dumps({"cmd": 93102, "bdy": [chzzk_item(extras=json.dumps({"payAmount": 1000}))]}))
    assert donation[0].kind == "donation"


def test_chzzk_open_api_events():
    chat = chzzk_api_event("CHAT", {"content": "안녕 {:hi:}", "emojis": {"hi": "https://x.pstatic.net/hi.png"}, "messageTime": 1763700000000,
                                    "profile": {"nickname": "숲속토끼", "userRoleCode": "streaming_chat_manager"}})
    assert chat.name == "숲속토끼" and chat.role == "moderator" and chat.parts[-1] == ("emote", "https://x.pstatic.net/hi.png")
    donation = chzzk_api_event("DONATION", {"donatorNickname": "도토리", "payAmount": "10,000", "donationText": "데뷔 축하!"})
    assert donation.kind == "donation" and donation.amount == 10000 and donation.text == "데뷔 축하!"
    member = chzzk_api_event("SUBSCRIPTION", {"subscriberNickname": "Haru", "month": 3})
    assert member.kind == "member" and member.text == "3개월 구독"
    assert chzzk_api_event("UNKNOWN", {}) is None


def soop_packet(service: int, *fields: str) -> bytes:
    body = "\x0c".join(("",) + fields + ("",)).encode("utf-8")
    return f"\x1b\t{service:04d}{len(body):06d}00".encode() + body


def test_soop_chat_and_balloons():
    chat = soop_event(soop_packet(5, "안녕하세요", "viewer1(2)", "0", "0", "0", "숲속토끼", "flag"))
    assert chat.kind == "chat" and chat.name == "숲속토끼" and chat.text == "안녕하세요"
    owner = soop_event(soop_packet(5, "반가워요", "bjid", "0", "0", "0", "방장"), streamer="bjid")
    assert owner.role == "owner"
    no_nick = soop_event(soop_packet(5, "짧은 패킷", "viewer2"))
    assert no_nick.name == "viewer2"
    balloon = soop_event(soop_packet(18, "bjid", "fan1", "별빛시청자", "100"))
    assert balloon.kind == "donation" and balloon.amount == 100 and balloon.unit == "별풍선" and balloon.name == "별빛시청자"
    assert soop_event(soop_packet(18, "bjid", "fan1", "닉", "not-a-number")) is None
    assert soop_event(soop_packet(4, "something")) is None
    assert soop_event(b"garbage") is None


def test_twitch_chat_bits_and_subs():
    line = "@badges=broadcaster/1;color=#FF4F8B;display-name=Haru;mod=0 :haru!haru@haru.tmi.twitch.tv PRIVMSG #haru :hello chat"
    chat = twitch_event(line)
    assert chat.name == "Haru" and chat.role == "owner" and chat.color == "#FF4F8B" and chat.text == "hello chat"
    bits = twitch_event("@bits=500;display-name=Fan;color= :fan!fan@fan PRIVMSG #haru :cheer500 축하")
    assert bits.kind == "donation" and bits.amount == 500 and bits.unit == "bits" and bits.color == ""
    sub = twitch_event(r"@msg-id=resub;display-name=Fan;system-msg=Fan\ssubscribed\sfor\s3\smonths :tmi.twitch.tv USERNOTICE #haru :yay")
    assert sub.kind == "member" and sub.text == "Fan subscribed for 3 months yay"
    assert twitch_event("@msg-id=raid :tmi.twitch.tv USERNOTICE #haru") is None
    assert twitch_event(":tmi.twitch.tv 001 justinfan :Welcome") is None


def test_demo_chat_is_paced_by_the_clock():
    now = [0.0]
    demo = DemoChat(every=1.0, seed=7, clock=lambda: now[0])
    assert len(demo.read()) == 1  # 시작 즉시 하나
    assert demo.read() == []
    now[0] = 30.0
    burst = demo.read()
    assert 10 <= len(burst) <= 80
    assert all(isinstance(event, OverlayEvent) and event.name for event in burst)


def test_event_dict_is_json_ready():
    data = OverlayEvent("chzzk", "chat", "a", (("text", "b"),)).to_dict()
    assert data["parts"] == [{"type": "text", "value": "b"}]
    json.dumps(data)


# ---------------------------------------------------------------------------- 서버


def test_hub_replays_history_to_new_listeners():
    hub = Hub(history=2)
    for n in range(3):
        hub.publish(OverlayEvent("demo", "chat", str(n)))
    subscriber, backlog = hub.subscribe()
    assert [event.name for event in backlog] == ["1", "2"]
    hub.publish(OverlayEvent("demo", "chat", "3"))
    assert subscriber.get_nowait().name == "3"
    hub.unsubscribe(subscriber)
    assert hub.listeners == 0


class OneShot:
    ended = False

    def __init__(self):
        self.sent = False

    def read(self):
        if self.sent:
            return []
        self.sent = True
        return [OverlayEvent("chzzk", "chat", "치즈냥", (("text", "첫 채팅"),))]

    def close(self):
        self.ended = True


@pytest.fixture
def server():
    srv = OverlayServer([("테스트", OneShot)], port=0, poll=0.01).start()
    yield srv
    srv.stop()


def get(srv, path, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    conn.request("GET", path, headers=headers or {})
    response = conn.getresponse()
    return response.status, response.read() if path != "/events" else response


def test_pages_are_served(server):
    for path, marker in (("/", "debutkit"), ("/chat", "startChat"), ("/alerts", "startAlerts"), ("/overlay.js", "EventSource"), ("/overlay.css", "transparent")):
        status, body = get(server, path)
        assert status == 200 and marker.encode() in body, path
    assert get(server, "/nope")[0] == 404


def test_foreign_host_or_origin_is_refused(server):
    assert get(server, "/chat", {"Host": "evil.example:80"})[0] == 403
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.request("POST", "/test", body=b"{}", headers={"Origin": "https://evil.example", "Content-Type": "application/json"})
    assert conn.getresponse().status == 403


def read_event(response, deadline=5.0):
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        line = response.fp.readline().decode("utf-8")
        if line.startswith("data: "):
            return json.loads(line[6:])
    raise AssertionError("no event")


def test_events_stream_carries_source_and_test_messages(server):
    for _ in range(100):  # 수신 스레드가 첫 채팅을 올릴 때까지
        if any(event.name == "치즈냥" for event in server.hub.history):
            break
        time.sleep(0.02)
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.request("GET", "/events")
    response = conn.getresponse()
    assert response.getheader("Content-Type").startswith("text/event-stream")
    seen = []
    while not any(event["name"] == "치즈냥" for event in seen):
        seen.append(read_event(response))
    assert seen[-1]["replay"] is True and seen[-1]["parts"] == [{"type": "text", "value": "첫 채팅"}]

    def post():
        c = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        c.request("POST", "/test", body=json.dumps({"kind": "donation", "text": "<b>hi</b>"}).encode(),
                  headers={"Origin": f"http://127.0.0.1:{server.port}", "Content-Type": "application/json"})
        assert c.getresponse().status == 200

    threading.Thread(target=post).start()
    event = read_event(response)
    while event["platform"] != "demo":
        event = read_event(response)
    assert event["kind"] == "donation" and event["replay"] is False
    assert event["parts"][0]["value"] == "<b>hi</b>"  # 글 그대로 전달, 화면은 textContent로만 넣는다


def test_bad_source_reports_and_stops():
    def broken():
        raise ValueError("Not a CHZZK channel")

    srv = OverlayServer([("CHZZK x", broken)], port=0, poll=0.01).start()
    try:
        for _ in range(100):
            if srv.hub.history:
                break
            time.sleep(0.02)
        assert "Not a CHZZK channel" in srv.hub.history[-1].text
    finally:
        srv.stop()


def test_stop_before_start_returns():
    srv = OverlayServer([], port=0)
    worker = threading.Thread(target=srv.stop, daemon=True)
    worker.start()
    worker.join(3)
    assert not worker.is_alive()  # 시작 전 shutdown()은 영원히 기다리므로 건너뛰어야 한다


def test_settings_page_has_streamer_clip_test(server):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.request("GET", "/")
    page = conn.getresponse().read().decode("utf-8")
    assert 'id="test-clip"' in page and '"owner"' in page


def test_settings_page_has_theme_picker_and_youtube_badge(server):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.request("GET", "/")
    page = conn.getresponse().read().decode("utf-8")
    for theme in ("shadow", "bubble", "card", "outline", "light", "style"):
        assert f'value="{theme}"' in page
    # 채팅창 꾸미기(카드 스타일, 이름 색, 등장, 정렬, 쌓이는 방향, 이모티콘 크기, 역할 표시)와 알림 꾸미기 화면
    for option in ("opt-look", "opt-names", "opt-enter", "opt-align", "opt-direction", "opt-emote", "opt-roles"):
        assert f'id="{option}"' in page, option
    assert 'href="/alerts/control"' in page
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.request("GET", "/overlay.js")
    script = conn.getresponse().read().decode("utf-8")
    assert "youtube:" in script and "--line-color" in script
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.request("GET", "/overlay.css")
    css = conn.getresponse().read().decode("utf-8")
    assert all(f'data-theme="{theme}"' in css for theme in ("card", "outline", "light"))
