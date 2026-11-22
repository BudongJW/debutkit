"""YouTube 스트리밍 수신: 같은 메시지 정의로 띄운 gRPC 서버(이 PC)와 실제로 통신해 확인한다."""

import json
import time
from concurrent import futures

import pytest

grpc = pytest.importorskip("grpc")

from debutkit.overlay import youtube_stream  # noqa: E402
from debutkit.overlay.youtube import YouTubeLiveChat, youtube_source  # noqa: E402

VIDEO = "dQw4w9WgXcQ"


def videos_api(url, headers):
    """videos.list(라이브 채팅 ID)와 요청 방식 전환 후의 liveChat/messages 응답."""
    if "/videos?" in url:
        return 200, json.dumps({"items": [{"liveStreamingDetails": {"activeLiveChatId": "CHAT"}}]}).encode()
    item = {"snippet": {"type": "textMessageEvent", "textMessageDetails": {"messageText": "요청 방식 채팅"}}, "authorDetails": {"displayName": "a"}}
    return 200, json.dumps({"items": [item], "nextPageToken": "n", "pollingIntervalMillis": 0}).encode()


def response(token, *items, offline=""):
    classes = youtube_stream.messages()
    message = classes["LiveChatMessageListResponse"](next_page_token=token)
    if offline:
        message.offline_at = offline
    for kind, name, text, extra in items:
        item = message.items.add()
        item.snippet.type = youtube_stream.SNIPPET_TYPES[kind]
        item.snippet.published_at = "2026-11-22T03:00:00Z"
        item.author_details.display_name = name
        if text:
            item.snippet.text_message_details.message_text = text
        for field, value in extra.items():
            setattr(item.snippet.super_chat_details, field, value) if field != "owner" else setattr(item.author_details, "is_chat_owner", value)
    return message


class Server:
    def __init__(self, handler):
        classes = youtube_stream.messages()
        self.requests = []
        self.metadata = []

        def stream_list(request, context):
            self.requests.append(request)
            self.metadata.append(dict(context.invocation_metadata()))
            yield from handler(request, context, len(self.requests))

        method = grpc.unary_stream_rpc_method_handler(stream_list, request_deserializer=classes["LiveChatMessageListRequest"].FromString,
                                                      response_serializer=classes["LiveChatMessageListResponse"].SerializeToString)
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        self.server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(youtube_stream.SERVICE, {"StreamList": method}),))
        self.port = self.server.add_insecure_port("127.0.0.1:0")
        self.server.start()

    def client(self, **kwargs):
        return youtube_stream.YouTubeStreamChat(VIDEO, "KEY", target=f"127.0.0.1:{self.port}", secure=False, send=videos_api, retry=0.05, **kwargs)

    def stop(self):
        self.server.stop(0)


def collect(chat, until, seconds=5.0):
    found = []
    end = time.monotonic() + seconds
    while time.monotonic() < end and not until(found):
        found += chat.read()
        time.sleep(0.02)
    return found


def test_message_definitions_follow_google_field_numbers():
    classes = youtube_stream.messages()
    fields = {field.name: field.number for field in classes["LiveChatMessageListResponse"].DESCRIPTOR.fields}
    assert fields == {"kind": 200, "offline_at": 2, "next_page_token": 100602, "items": 1007}
    snippet = classes["LiveChatMessage"].DESCRIPTOR.fields_by_name["snippet"].message_type
    assert snippet.fields_by_name["super_chat_details"].number == 27 and snippet.fields_by_name["text_message_details"].number == 19


def test_stream_skips_history_reconnects_with_page_token_and_ends_offline():
    def handler(request, context, count):
        if count == 1:
            yield response("p1", ("TEXT_MESSAGE_EVENT", "지난", "지난 채팅", {}))
            yield response("p2", ("TEXT_MESSAGE_EVENT", "시청자", "새 채팅", {}),
                           ("SUPER_CHAT_EVENT", "후원자", "", {"amount_micros": 10_000_000_000, "currency": "KRW", "user_comment": "축하"}))
            return  # 서버가 연결을 닫음: 클라이언트는 마지막 위치부터 다시 연결
        yield response("p3", ("TEXT_MESSAGE_EVENT", "스트리머", "다시 연결 후", {"owner": True}), offline="2026-11-22T05:00:00Z")

    server = Server(handler)
    chat = server.client()
    try:
        events = collect(chat, lambda found: len(found) >= 3)
        assert [(event.kind, event.text) for event in events] == [("chat", "새 채팅"), ("donation", "축하"), ("chat", "다시 연결 후")]
        assert events[1].amount == 10000 and events[1].unit == "원" and events[2].role == "owner"
        assert server.requests[0].live_chat_id == "CHAT" and list(server.requests[0].part) == ["snippet", "authorDetails"]
        assert server.requests[1].page_token == "p2"
        assert server.metadata[0]["x-goog-api-key"] == "KEY"
        end = time.monotonic() + 3
        while not chat.ended and time.monotonic() < end:
            time.sleep(0.02)
        assert chat.ended  # offlineAt
    finally:
        chat.close()
        server.stop()


def test_unsupported_stream_falls_back_to_polling():
    def handler(request, context, count):
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "not here")
        yield  # pragma: no cover

    server = Server(handler)
    chat = server.client(interval=5)
    chat.poller._clock = lambda: 1000.0
    try:
        events = collect(chat, lambda found: any(event.kind == "system" for event in found))
        assert any("요청 방식으로 전환" in event.text for event in events)
        assert "UNIMPLEMENTED" in chat.fallback_reason
    finally:
        chat.close()
        server.stop()


def test_quota_error_is_reported():
    def handler(request, context, count):
        context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "quota")
        yield  # pragma: no cover

    server = Server(handler)
    chat = server.client()
    try:
        with pytest.raises(RuntimeError, match="할당량 초과"):
            end = time.monotonic() + 5
            while time.monotonic() < end:
                chat.read()
                time.sleep(0.02)
    finally:
        chat.close()
        server.stop()


def test_source_modes(monkeypatch):
    assert isinstance(youtube_source(VIDEO, "KEY", mode="poll"), YouTubeLiveChat)
    assert isinstance(youtube_source(VIDEO, "KEY"), youtube_stream.YouTubeStreamChat)
    monkeypatch.setattr(youtube_stream, "available", lambda: False)
    assert isinstance(youtube_source(VIDEO, "KEY"), YouTubeLiveChat)
    with pytest.raises(RuntimeError, match="grpcio"):
        youtube_source(VIDEO, "KEY", mode="stream")
    with pytest.raises(ValueError):
        youtube_source(VIDEO, "KEY", mode="fast")


def test_probe_stream_reports_first_response_and_errors():
    def history(request, context, count):
        yield response("p1", ("TEXT_MESSAGE_EVENT", "a", "지난 채팅", {}))
        time.sleep(5)  # 첫 응답 뒤에는 연결 유지: 확인은 첫 응답에서 끝나야 함

    server = Server(history)
    try:
        started = time.monotonic()
        ok, detail = youtube_stream.probe_stream("CHAT", "KEY", target=f"127.0.0.1:{server.port}", secure=False, timeout=5)
        assert ok and "채팅 1개" in detail and time.monotonic() - started < 3
        assert server.metadata[0]["x-goog-api-key"] == "KEY"
    finally:
        server.stop()

    def denied(request, context, count):
        context.abort(grpc.StatusCode.PERMISSION_DENIED, "Permission denied on the service.")
        yield from ()

    server = Server(denied)
    try:
        ok, detail = youtube_stream.probe_stream("CHAT", "KEY", target=f"127.0.0.1:{server.port}", secure=False, timeout=5)
        assert not ok and detail.startswith("PERMISSION_DENIED")
    finally:
        server.stop()

    def silent(request, context, count):
        time.sleep(3)
        yield from ()

    server = Server(silent)
    try:
        ok, detail = youtube_stream.probe_stream("CHAT", "KEY", target=f"127.0.0.1:{server.port}", secure=False, timeout=0.5)
        assert not ok and "응답 없음" in detail
    finally:
        server.stop()
