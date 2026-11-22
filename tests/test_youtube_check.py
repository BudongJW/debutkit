"""YouTube 연결 확인(debutkit youtube check): 가짜 YouTube 응답으로 단계별 결과 확인."""

import json

from debutkit import cli
from debutkit.overlay import youtube_check

VIDEO = "dQw4w9WgXcQ"


def api(*, videos=None, messages=None):
    calls = []

    def send(url, headers):
        calls.append((url, headers))
        if "/videos?" in url:
            return videos or (200, json.dumps({"items": [{"liveStreamingDetails": {"activeLiveChatId": "CHAT"}}]}).encode())
        return messages or (200, json.dumps({"items": [{}, {}], "pollingIntervalMillis": 3000}).encode())

    send.calls = calls
    return send


def test_all_steps_pass():
    send = api()
    probed = []
    steps = youtube_check.check(VIDEO, "KEY", send=send, streaming=True, probe=lambda chat, key, timeout: probed.append((chat, key)) or (True, "연결 성공"))
    assert [step.ok for step in steps] == [True, True, True, True]
    assert "채팅 2개" in steps[2].detail and "3.0초" in steps[2].detail
    assert probed == [("CHAT", "KEY")]
    assert all(headers["X-Goog-Api-Key"] == "KEY" for _, headers in send.calls)
    assert "KEY" not in youtube_check.format_steps(steps)  # 키는 출력하지 않음


def test_invalid_key_stops_before_streaming():
    body = json.dumps({"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "errors": [{"reason": "badRequest"}]}}).encode()
    steps = youtube_check.check(VIDEO, "BAD", send=api(videos=(400, body)), streaming=True, probe=lambda *a, **k: (True, ""))
    assert [step.ok for step in steps] == [True, False]
    assert steps[-1].detail == "API 키 확인 필요(잘못된 키)"


def test_not_live_and_missing_key():
    steps = youtube_check.check(VIDEO, "KEY", send=api(videos=(200, json.dumps({"items": [{"liveStreamingDetails": {}}]}).encode())), streaming=True)
    assert steps[-1].ok is False and "방송 중이 아니거나" in steps[-1].detail
    steps = youtube_check.check("https://www.youtube.com/@channel", "KEY", send=api())
    assert steps[0].ok is False and "채널 주소는 지원 안 함" in steps[0].detail


def test_streaming_skipped_without_grpc():
    steps = youtube_check.check(VIDEO, "KEY", send=api(), streaming=False)
    assert steps[-1].ok is None and "grpcio" in steps[-1].detail
    assert "[생략] 스트리밍 방식" in youtube_check.format_steps(steps)


def test_cli_exit_code_and_json(monkeypatch, capsys):
    results = {"ok": [youtube_check.Step("방송 주소", True, "영상 ID x")], "fail": [youtube_check.Step("요청 방식", False, "오류")]}
    for name, expected in (("ok", 0), ("fail", 1)):
        monkeypatch.setattr(youtube_check, "check", lambda address, key, timeout, name=name: results[name])
        assert cli.main(["youtube", "check", VIDEO, "--youtube-key", "KEY"]) == expected
    assert "[실패] 요청 방식" in capsys.readouterr().out
    monkeypatch.setattr(youtube_check, "check", lambda address, key, timeout: results["ok"])
    assert cli.main(["youtube", "check", VIDEO, "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == [{"name": "방송 주소", "ok": True, "detail": "영상 ID x"}]
