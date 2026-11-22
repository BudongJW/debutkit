import json

import pytest

from debutkit.overlay.youtube import YouTubeLiveChat, video_id, youtube_event

VIDEO = "dQw4w9WgXcQ"


@pytest.mark.parametrize("address", [
    VIDEO,
    f"https://www.youtube.com/watch?v={VIDEO}",
    f"https://youtube.com/watch?feature=share&v={VIDEO}",
    f"https://youtu.be/{VIDEO}?si=abc",
    f"https://www.youtube.com/live/{VIDEO}",
    f"m.youtube.com/watch?v={VIDEO}",
])
def test_video_id_from_addresses(address):
    assert video_id(address) == VIDEO


@pytest.mark.parametrize("address", ["https://www.youtube.com/@channel/live", "https://example.com/watch?v=dQw4w9WgXcQ", "short"])
def test_video_id_rejects_channels_and_others(address):
    with pytest.raises(ValueError, match="채널 주소"):
        video_id(address)


def item(kind, author=None, **snippet):
    return {"snippet": {"type": kind, "publishedAt": "2026-11-22T03:00:01.5+00:00", **snippet},
            "authorDetails": {"displayName": "시청자", **(author or {})}}


def test_chat_and_roles():
    chat = youtube_event(item("textMessageEvent", {"isChatOwner": True}, textMessageDetails={"messageText": "안녕"}))
    assert (chat.platform, chat.kind, chat.name, chat.text, chat.role) == ("youtube", "chat", "시청자", "안녕", "owner")
    from datetime import datetime, timezone

    assert chat.time == pytest.approx(datetime(2026, 11, 22, 3, 0, 1, 500000, tzinfo=timezone.utc).timestamp())
    moderator = youtube_event(item("textMessageEvent", {"isChatModerator": True}, displayMessage="hi"))
    assert moderator.role == "moderator" and moderator.text == "hi"


def test_super_chat_and_sticker():
    paid = youtube_event(item("superChatEvent", superChatDetails={"amountMicros": "10000000000", "currency": "KRW", "userComment": "데뷔 축하"}))
    assert (paid.kind, paid.amount, paid.unit, paid.text) == ("donation", 10000.0, "원", "데뷔 축하")
    sticker = youtube_event(item("superStickerEvent", superStickerDetails={"amountMicros": "2000000", "currency": "USD"}))
    assert (sticker.amount, sticker.unit, sticker.parts) == (2.0, "USD", ())


def test_memberships():
    assert youtube_event(item("newSponsorEvent", newSponsorDetails={"memberLevelName": "팬"})).text == "멤버십 가입 (팬)"
    milestone = youtube_event(item("memberMilestoneChatEvent", memberMilestoneChatDetails={"memberMonth": 3, "userComment": "고마워요"}))
    assert milestone.kind == "member" and milestone.text == "멤버십 3개월 고마워요"
    assert youtube_event(item("membershipGiftingEvent", membershipGiftingDetails={"giftMembershipsCount": 5})).text == "멤버십 선물 5개"
    assert youtube_event(item("chatEndedEvent")) is None


class FakeApi:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers):
        self.calls.append((url, headers))
        status, data = self.responses.pop(0)
        return status, json.dumps(data).encode()


def messages(*items, token="t", wait=2000, **extra):
    return 200, {"items": list(items), "nextPageToken": token, "pollingIntervalMillis": wait, **extra}


def test_live_chat_flow_skips_history_and_keeps_interval():
    now = [0.0]
    api = FakeApi(
        (200, {"items": [{"liveStreamingDetails": {"activeLiveChatId": "CHAT"}}]}),
        messages(item("textMessageEvent", textMessageDetails={"messageText": "지난 채팅"}), token="p1"),
        messages(item("textMessageEvent", textMessageDetails={"messageText": "새 채팅"}), token="p2", wait=15000),
    )
    chat = YouTubeLiveChat(VIDEO, "KEY", interval=10, send=api, clock=lambda: now[0])
    assert chat.read() == []  # 첫 응답은 지난 채팅
    assert "videos?" in api.calls[0][0] and api.calls[0][1]["X-Goog-Api-Key"] == "KEY" and "KEY" not in api.calls[0][0]
    now[0] = 5.0
    assert chat.read() == [] and len(api.calls) == 2  # 간격 전에는 묻지 않는다
    now[0] = 10.0
    assert [event.text for event in chat.read()] == ["새 채팅"]
    assert "pageToken=p1" in api.calls[2][0] and "liveChatId=CHAT" in api.calls[2][0]
    now[0] = 20.0
    assert chat.read() == [] and len(api.calls) == 3  # YouTube가 15초를 요구하면 15초를 기다린다


def test_live_chat_errors_are_korean():
    quota = FakeApi((403, {"error": {"code": 403, "message": "quota", "errors": [{"reason": "quotaExceeded"}]}}))
    with pytest.raises(RuntimeError, match="할당량 초과"):
        YouTubeLiveChat(VIDEO, "KEY", send=quota, clock=lambda: 0.0).read()
    bad_key = FakeApi((400, {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "errors": [{"reason": "badRequest"}]}}))
    with pytest.raises(RuntimeError, match="API 키 확인"):
        YouTubeLiveChat(VIDEO, "KEY", send=bad_key, clock=lambda: 0.0).read()
    offline = FakeApi((200, {"items": [{"liveStreamingDetails": {}}]}))
    with pytest.raises(RuntimeError, match="방송 중이 아니거나"):
        YouTubeLiveChat(VIDEO, "KEY", send=offline, clock=lambda: 0.0).read()


def test_ended_stream_stops_reading():
    now = [0.0]
    api = FakeApi((200, {"items": [{"liveStreamingDetails": {"activeLiveChatId": "CHAT"}}]}), messages(offlineAt="2026-11-22T05:00:00Z"))
    chat = YouTubeLiveChat(VIDEO, "KEY", send=api, clock=lambda: now[0])
    chat.read()
    assert chat.ended


def test_key_is_required(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="API 키 필요"):
        YouTubeLiveChat(VIDEO)
    monkeypatch.setenv("YOUTUBE_API_KEY", "ENV")
    assert YouTubeLiveChat(VIDEO).api_key == "ENV"
    assert YouTubeLiveChat(VIDEO, interval=1).interval == 5.0  # 최소 5초
