"""YouTube 라이브 채팅 스트리밍: liveChatMessages.streamList(gRPC 서버 스트리밍).

- 요청 방식(:mod:`.youtube`)은 10초마다 5 단위를 쓰지만, 스트리밍은 연결 1회에 5 단위를 쓰고
  연결을 유지한다. 지연이 짧고 할당량 사용이 적다
- 메시지 정의는 Google 스트리밍 안내(stream_list.proto)의 필드 번호를 따르되, 화면 표시에 필요한
  필드만 코드로 정의한다(정의하지 않은 필드는 무시). 받은 메시지는 REST 응답과 같은 JSON 형태로 바꿔
  :func:`.youtube.youtube_event` 를 그대로 쓴다
- 스트림을 쓸 수 없으면(gRPC 미설치, 연결 거부, 미지원) 요청 방식으로 자동 전환
- 필요 패키지: grpcio, protobuf(``pip install "debutkit[youtube]"``, 설정 마법사 설치에 포함)
"""

from __future__ import annotations

import functools
import queue
import threading
import time
from typing import Any, Callable

from .events import OverlayEvent, system_event
from .youtube import DEFAULT_INTERVAL, YouTubeLiveChat, youtube_event

TARGET = "dns:///youtube.googleapis.com:443"
SERVICE = "youtube.api.v3.V3DataLiveChatMessageService"
METHOD = f"/{SERVICE}/StreamList"
PACKAGE = "youtube.api.v3"

#: 메시지 이름과 필드(이름, 번호, 형식, 반복 여부). 형식은 string, uint32, uint64, int32, bool, 또는 다른 메시지 이름
MESSAGES: dict[str, list[tuple[str, int, str, bool]]] = {
    "LiveChatMessageListRequest": [("live_chat_id", 1, "string", False), ("hl", 2, "string", False), ("profile_image_size", 3, "uint32", False),
                                   ("max_results", 98, "uint32", False), ("page_token", 99, "string", False), ("part", 100, "string", True)],
    "LiveChatMessageListResponse": [("kind", 200, "string", False), ("offline_at", 2, "string", False),
                                    ("next_page_token", 100602, "string", False), ("items", 1007, "LiveChatMessage", True)],
    "LiveChatMessage": [("id", 101, "string", False), ("snippet", 2, "LiveChatMessageSnippet", False),
                        ("author_details", 3, "LiveChatMessageAuthorDetails", False)],
    "LiveChatMessageAuthorDetails": [("channel_id", 10101, "string", False), ("display_name", 103, "string", False),
                                     ("is_chat_owner", 5, "bool", False), ("is_chat_sponsor", 6, "bool", False), ("is_chat_moderator", 7, "bool", False)],
    "LiveChatMessageSnippet": [("type", 1, "enum", False), ("published_at", 4, "string", False), ("display_message", 16, "string", False),
                               ("text_message_details", 19, "LiveChatTextMessageDetails", False),
                               ("super_chat_details", 27, "LiveChatSuperChatDetails", False),
                               ("super_sticker_details", 28, "LiveChatSuperStickerDetails", False),
                               ("new_sponsor_details", 29, "LiveChatNewSponsorDetails", False),
                               ("member_milestone_chat_details", 30, "LiveChatMemberMilestoneChatDetails", False),
                               ("membership_gifting_details", 31, "LiveChatMembershipGiftingDetails", False)],
    "LiveChatTextMessageDetails": [("message_text", 1, "string", False)],
    "LiveChatSuperChatDetails": [("amount_micros", 1, "uint64", False), ("currency", 2, "string", False), ("amount_display_string", 3, "string", False),
                                 ("user_comment", 4, "string", False), ("tier", 5, "uint32", False)],
    "LiveChatSuperStickerDetails": [("amount_micros", 1, "uint64", False), ("currency", 2, "string", False), ("amount_display_string", 3, "string", False),
                                    ("tier", 4, "uint32", False)],
    "LiveChatNewSponsorDetails": [("member_level_name", 1, "string", False), ("is_upgrade", 2, "bool", False)],
    "LiveChatMemberMilestoneChatDetails": [("member_level_name", 1, "string", False), ("member_month", 2, "uint32", False), ("user_comment", 3, "string", False)],
    "LiveChatMembershipGiftingDetails": [("gift_memberships_count", 1, "int32", False), ("gift_memberships_level_name", 2, "string", False)],
}
#: LiveChatMessageSnippet.TypeWrapper.Type
SNIPPET_TYPES = {"INVALID_TYPE": 0, "TEXT_MESSAGE_EVENT": 1, "TOMBSTONE": 2, "FAN_FUNDING_EVENT": 3, "CHAT_ENDED_EVENT": 4,
                 "SPONSOR_ONLY_MODE_STARTED_EVENT": 5, "SPONSOR_ONLY_MODE_ENDED_EVENT": 6, "NEW_SPONSOR_EVENT": 7, "USER_BANNED_EVENT": 10,
                 "SUPER_CHAT_EVENT": 15, "SUPER_STICKER_EVENT": 16, "MEMBER_MILESTONE_CHAT_EVENT": 17, "MEMBERSHIP_GIFTING_EVENT": 18,
                 "GIFT_MEMBERSHIP_RECEIVED_EVENT": 19, "POLL_EVENT": 20, "GIFT_EVENT": 21}


def available() -> bool:
    try:
        import grpc  # noqa: F401
        from google.protobuf import descriptor_pb2  # noqa: F401
    except ImportError:
        return False
    return True


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.capitalize() for part in rest)


@functools.lru_cache(maxsize=1)
def messages() -> dict[str, Any]:
    """MESSAGES로 메시지 클래스를 만든다(protoc 생성 코드 없이)."""
    from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

    scalar = {"string": descriptor_pb2.FieldDescriptorProto.TYPE_STRING, "uint32": descriptor_pb2.FieldDescriptorProto.TYPE_UINT32,
              "uint64": descriptor_pb2.FieldDescriptorProto.TYPE_UINT64, "int32": descriptor_pb2.FieldDescriptorProto.TYPE_INT32,
              "bool": descriptor_pb2.FieldDescriptorProto.TYPE_BOOL}
    file = descriptor_pb2.FileDescriptorProto(name="debutkit_youtube_stream.proto", package=PACKAGE, syntax="proto2")
    for message_name, fields in MESSAGES.items():
        message = file.message_type.add(name=message_name)
        if message_name == "LiveChatMessageSnippet":
            wrapper = message.nested_type.add(name="TypeWrapper")
            enum = wrapper.enum_type.add(name="Type")
            for value_name, number in SNIPPET_TYPES.items():
                enum.value.add(name=value_name, number=number)
        for name, number, kind, repeated in fields:
            field = message.field.add(name=name, number=number, json_name=_camel(name),
                                      label=descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED if repeated else descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL)
            if kind in scalar:
                field.type = scalar[kind]
            elif kind == "enum":
                field.type = descriptor_pb2.FieldDescriptorProto.TYPE_ENUM
                field.type_name = f".{PACKAGE}.LiveChatMessageSnippet.TypeWrapper.Type"
            else:
                field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
                field.type_name = f".{PACKAGE}.{kind}"
    pool = descriptor_pool.DescriptorPool()
    pool.Add(file)
    return {name: message_factory.GetMessageClass(pool.FindMessageTypeByName(f"{PACKAGE}.{name}")) for name in MESSAGES}


def to_dict(response: Any) -> dict[str, Any]:
    """스트림 응답을 REST 응답과 같은 JSON 형태로(snippet.type은 textMessageEvent 형식)."""
    from google.protobuf.json_format import MessageToDict

    data = MessageToDict(response)
    for item in data.get("items") or []:
        snippet = item.get("snippet") or {}
        if "type" in snippet:
            snippet["type"] = _camel(str(snippet["type"]).lower())
    return data


def probe_stream(chat_id: str, api_key: str, *, timeout: float = 20.0, target: str = TARGET, secure: bool = True) -> tuple[bool, str]:
    """스트림을 열어 첫 응답까지만 확인하고 닫는다(연결 1회 5 단위). (성공 여부, 설명)."""
    import grpc

    classes = messages()
    request_class, response_class = classes["LiveChatMessageListRequest"], classes["LiveChatMessageListResponse"]
    channel = grpc.secure_channel(target, grpc.ssl_channel_credentials()) if secure else grpc.insecure_channel(target)
    try:
        call = channel.unary_stream(METHOD, request_serializer=request_class.SerializeToString, response_deserializer=response_class.FromString)
        responses = call(request_class(live_chat_id=chat_id, hl="ko", part=["snippet", "authorDetails"]),
                         metadata=(("x-goog-api-key", api_key),), timeout=timeout)
        for response in responses:
            count = len(to_dict(response).get("items") or [])
            responses.cancel()
            return True, f"연결 성공. 첫 응답 채팅 {count}개(5 단위)"
        return False, "응답 없이 연결 종료"
    except grpc.RpcError as error:
        code = error.code().name if error.code() else "UNKNOWN"
        if code == "DEADLINE_EXCEEDED":
            return False, f"{timeout:.0f}초 안에 응답 없음"
        if code == "RESOURCE_EXHAUSTED":
            return False, "YouTube API 일일 할당량 초과(태평양 시간 자정 초기화)"
        return False, f"{code}: {error.details() or ''}".strip()
    finally:
        channel.close()


#: 스트림 연결 전에 이 오류가 나면 스트리밍을 쓸 수 없는 것으로 보고 요청 방식으로 전환
_FALLBACK_CODES = ("UNIMPLEMENTED", "INVALID_ARGUMENT", "PERMISSION_DENIED", "UNAUTHENTICATED", "NOT_FOUND", "FAILED_PRECONDITION")


class YouTubeStreamChat:
    """오버레이 수신기. 스트림은 별도 스레드에서 받고 ``read()`` 는 받은 사건을 바로 돌려준다."""

    def __init__(self, address: str, api_key: str | None = None, *, interval: float = DEFAULT_INTERVAL, target: str = TARGET, secure: bool = True,
                 send: Callable[[str, dict[str, str]], tuple[int, bytes]] | None = None, clock: Callable[[], float] = time.monotonic,
                 retry: float = 5.0) -> None:
        self.poller = YouTubeLiveChat(address, api_key, interval=interval, send=send, clock=clock)  # 주소, 키 확인과 전환 대상
        self.api_key, self.video = self.poller.api_key, self.poller.video
        self.target, self.secure, self.retry = target, secure, retry
        self.ended = False
        self.fallback_reason = ""
        self._queue: queue.Queue[OverlayEvent] = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._call: Any = None
        self._error = ""
        self._announced = False

    def _channel(self) -> Any:
        import grpc

        return grpc.secure_channel(self.target, grpc.ssl_channel_credentials()) if self.secure else grpc.insecure_channel(self.target)

    def _run(self) -> None:
        import grpc

        try:
            chat_id = self.poller.chat_id()
        except Exception as error:
            self._error = str(error)
            return
        classes = messages()
        request_class, response_class = classes["LiveChatMessageListRequest"], classes["LiveChatMessageListResponse"]
        page, first, connected = "", True, False
        while not self._stop.is_set() and not self.ended:
            channel = self._channel()
            try:
                call = channel.unary_stream(METHOD, request_serializer=request_class.SerializeToString, response_deserializer=response_class.FromString)
                request = request_class(live_chat_id=chat_id, hl="ko", part=["snippet", "authorDetails"])
                if page:
                    request.page_token = page
                self._call = call(request, metadata=(("x-goog-api-key", self.api_key),))
                for response in self._call:
                    connected = True
                    data = to_dict(response)
                    page = str(data.get("nextPageToken") or page)
                    events = [event for event in (youtube_event(item) for item in data.get("items") or []) if event is not None]
                    if first:  # 첫 응답은 이미 지난 채팅: 알림이 다시 뜨지 않게 버린다
                        first = False
                    else:
                        for event in events:
                            self._queue.put(event)
                    if data.get("offlineAt"):
                        self.ended = True
                        return
                    if self._stop.is_set():
                        return
            except grpc.RpcError as error:
                if self._stop.is_set():
                    return
                code = error.code().name if error.code() else ""
                if code == "RESOURCE_EXHAUSTED":
                    self._error = "YouTube API 일일 할당량 초과(태평양 시간 자정 초기화)"
                    return
                if not connected and code in _FALLBACK_CODES:
                    self.fallback_reason = f"{code}: {error.details() or ''}".strip()
                    return
                self._stop.wait(self.retry)  # 일시적 오류: 마지막 위치부터 다시 연결
            finally:
                channel.close()

    def read(self) -> list[OverlayEvent]:
        if self.fallback_reason:  # 요청 방식으로 전환
            found = self.poller.read()
            if not self._announced:
                self._announced = True
                return [system_event(f"YouTube 스트리밍 연결 불가({self.fallback_reason}), 요청 방식으로 전환"), *found]
            return found
        if self._error:
            raise RuntimeError(self._error)
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="youtube-stream", daemon=True)
            self._thread.start()
        found = []
        while True:
            try:
                found.append(self._queue.get_nowait())
            except queue.Empty:
                return found

    def close(self) -> None:
        self._stop.set()
        self.ended = True
        if self._call is not None:
            self._call.cancel()
        self.poller.close()
