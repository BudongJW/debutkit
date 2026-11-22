"""실제 YouTube 서버로 채팅 수신 경로를 검증한다(CI용, .github/workflows/verify.yml).

    python packaging/verify_youtube.py endpoint        # API 키 없이 확인 가능한 범위
    python packaging/verify_youtube.py check 방송주소  # 실제 API 키로 전체 확인(YOUTUBE_API_KEY 필요)

endpoint: 잘못된 키로 요청해 다음을 확인한다(할당량 사용 없음).
- 스트리밍(streamList): debutkit이 쓰는 메서드 경로에 "API key not valid"(INVALID_ARGUMENT) 응답.
  없는 메서드 이름의 응답(2026-11 기준 UNKNOWN)과 비교해 경로와 키 전달 방식을 함께 확인한다
- 요청 방식(REST): 잘못된 키 오류를 한국어 안내로 변환
check: debutkit youtube check 실행. 모든 단계가 정상이어야 통과(약 11 단위 사용).
"""

from __future__ import annotations

import os
import sys

INVALID_KEY = "AIzaSyInvalidKeyForDebutkitVerify0000000"


def stream_code(method: str) -> tuple[str, str]:
    import grpc

    from debutkit.overlay.youtube_stream import TARGET, messages

    classes = messages()
    request = classes["LiveChatMessageListRequest"](live_chat_id="debutkit-verify", part=["snippet", "authorDetails"])
    channel = grpc.secure_channel(TARGET, grpc.ssl_channel_credentials())
    try:
        call = channel.unary_stream(method, request_serializer=lambda message: message.SerializeToString(),
                                    response_deserializer=classes["LiveChatMessageListResponse"].FromString)
        for _ in call(request, metadata=(("x-goog-api-key", INVALID_KEY),), timeout=30):
            return "OK", "응답 수신"
        return "OK", "응답 없이 종료"
    except grpc.RpcError as error:
        return (error.code().name if error.code() else "UNKNOWN"), error.details() or ""
    finally:
        channel.close()


def endpoint() -> None:
    from debutkit.overlay.youtube_check import check, format_steps
    from debutkit.overlay.youtube_stream import METHOD

    code, detail = stream_code(METHOD)
    print(f"streamList({METHOD}), 잘못된 키: {code}: {detail}")
    if code != "INVALID_ARGUMENT" or "API key not valid" not in detail:
        raise SystemExit("streamList 메서드 경로 또는 API 키 전달 방식 확인 필요")
    wrong_code, wrong_detail = stream_code(METHOD.replace("StreamList", "NoSuchMethod"))
    print(f"없는 메서드 이름, 잘못된 키: {wrong_code}: {wrong_detail}")
    if wrong_code == code:  # Google의 오류 처리 순서가 바뀌면 같을 수 있어 실패로 보지 않음
        print("참고: 없는 메서드와 응답이 같아 이번 실행으로는 메서드 경로를 구분하지 못함")
    steps = check("jfKfPfyJRdk", INVALID_KEY)
    print(format_steps(steps))
    if steps[-1].ok is not False or steps[-1].detail != "API 키 확인 필요(잘못된 키)":
        raise SystemExit("요청 방식의 잘못된 키 안내가 예상과 다름")
    print("확인: 스트리밍 메서드 경로와 API 키 전달 방식, 요청 방식의 오류 안내")


def full_check(address: str) -> None:
    from debutkit.overlay.youtube_check import check, format_steps

    if not os.environ.get("YOUTUBE_API_KEY"):
        raise SystemExit("YOUTUBE_API_KEY 필요")
    steps = check(address, timeout=30)
    print(format_steps(steps))
    if not all(step.ok for step in steps):
        raise SystemExit("YouTube 실제 수신 확인 실패")


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if argv == ["endpoint"]:
        endpoint()
    elif len(argv) == 2 and argv[0] == "check":
        full_check(argv[1])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
