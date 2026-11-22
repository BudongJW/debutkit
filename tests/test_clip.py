import time
from pathlib import Path

import pytest

pytest.importorskip("stream2clip.live")

from debutkit.clip import AutoClipper, ChatTap, to_chat_message  # noqa: E402
from debutkit.overlay.events import OverlayEvent, system_event  # noqa: E402
from debutkit.overlay.server import Hub  # noqa: E402
from debutkit.scenes import enable_replay_buffer  # noqa: E402


def test_overlay_events_become_hashed_chat_messages():
    chat = to_chat_message(OverlayEvent("chzzk", "chat", "치즈냥", (("text", "ㅋㅋㅋ"),), time=100.0))
    assert chat.text == "ㅋㅋㅋ" and chat.time == 100.0 and chat.kind == "text"
    assert chat.author and "치즈냥" not in chat.author  # 닉네임은 해시로만
    other = to_chat_message(OverlayEvent("soop", "chat", "치즈냥", (("text", "a"),)))
    assert other.author != chat.author  # 플랫폼이 다르면 다른 사람
    paid = to_chat_message(OverlayEvent("soop", "donation", "a", (), amount=10, unit="별풍선"))
    assert paid.kind == "paid" and paid.amount == 10 and paid.currency == "별풍선"
    assert to_chat_message(system_event("연결")) is None


def test_tap_queues_until_read():
    tap = ChatTap()
    tap(OverlayEvent("twitch", "chat", "a", (("text", "hi"),)))
    tap(system_event("x"))
    assert [m.text for m in tap.read()] == ["hi"]
    assert tap.read() == []
    tap.close()
    tap(OverlayEvent("twitch", "chat", "a", (("text", "late"),)))
    assert tap.read() == []


class FakeSaved:
    def __init__(self, n):
        self.clip = Path(f"live_{n}.mp4")
        self.note = ""


def wait_for(condition, seconds=10.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_streamer_marker_saves_a_clip_and_reports_it():
    from stream2clip.live import LiveConfig

    now = [1000.0]
    triggers = []

    def clipper(trigger):
        triggers.append(trigger)
        return FakeSaved(len(triggers))

    hub = Hub()
    config = LiveConfig(lag=0.5, chat_delay=0.0, tail=0.0)
    auto = AutoClipper(hub, clipper, config=config, clock=lambda: now[0], poll=0.01).start()
    try:
        hub.publish(OverlayEvent("chzzk", "chat", "나", (("text", "!clip"),), role="owner", time=now[0] + 1))
        hub.publish(OverlayEvent("chzzk", "chat", "시청자", (("text", "!clip"),), time=now[0] + 1.5))  # 시청자의 명령은 무시
        now[0] += 10
        assert wait_for(lambda: triggers)
        assert wait_for(lambda: any("클립 저장: live_1.mp4" in e.text for e in hub.history))
        assert len(triggers) == 1
    finally:
        auto.stop()
    assert auto.tap not in hub.taps


def test_clip_failure_is_reported_not_raised():
    from stream2clip.live import LiveConfig

    now = [0.0]

    def clipper(trigger):
        raise RuntimeError("OBS가 꺼져 있음")

    hub = Hub()
    auto = AutoClipper(hub, clipper, config=LiveConfig(lag=0.5, chat_delay=0.0, tail=0.0), clock=lambda: now[0], poll=0.01).start()
    try:
        hub.publish(OverlayEvent("soop", "chat", "방장", (("text", "!클립"),), role="owner", time=1.0))
        now[0] = 20.0
        assert wait_for(lambda: any("클립 저장 실패" in e.text and "OBS가 꺼져 있음" in e.text for e in hub.history))
    finally:
        auto.stop()


class FakeObs:
    def __init__(self, mode="Simple", available=True, active=False):
        self.mode, self.available, self.active = mode, available, active
        self.params = {}
        self.calls = []

    def request(self, kind, data=None):
        from stream2clip.obs import ObsError

        self.calls.append(kind)
        if kind == "GetProfileParameter":
            return {"parameterValue": self.mode}
        if kind == "SetProfileParameter":
            self.params[(data["parameterCategory"], data["parameterName"])] = data["parameterValue"]
            return {}
        if not self.available:
            raise ObsError(f"{kind} failed (604): Replay buffer is not available.", 604)
        if kind == "GetReplayBufferStatus":
            return {"outputActive": self.active}
        return {}


@pytest.mark.parametrize("mode, category", [("Simple", "SimpleOutput"), ("Advanced", "AdvOut")])
def test_enable_replay_buffer_writes_the_right_settings(mode, category):
    obs = FakeObs(mode=mode)
    ready, message = enable_replay_buffer(obs, 45)
    assert ready and "45" in message
    assert obs.params == {(category, "RecRB"): "true", (category, "RecRBTime"): "45"}
    assert obs.calls[-1] == "StartReplayBuffer"


def test_enable_replay_buffer_asks_for_restart_when_obs_has_none_yet():
    ready, message = enable_replay_buffer(FakeObs(available=False), 30)
    assert not ready and "껐다 켜면" in message


def test_enable_replay_buffer_leaves_running_buffer():
    obs = FakeObs(active=True)
    assert enable_replay_buffer(obs)[0]
    assert "StartReplayBuffer" not in obs.calls


def test_english_notes_become_korean():
    from debutkit.clip import korean

    note = "the replay buffer holds 30 s but the clip wanted 45 s: raise Settings > Output > Replay Buffer > Maximum Replay Time in OBS"
    assert korean(note) == "리플레이 버퍼 길이 30초, 필요한 길이 45초. OBS 설정의 출력 탭에서 리플레이 버퍼 최대 시간 늘리기"
    assert "리플레이 버퍼 꺼짐" in korean("The replay buffer is not running. Start it in OBS")
    assert "debutkit setup --ffmpeg" in korean("ffprobe not found: run ...")
    assert korean("그대로") == "그대로"


def test_saved_note_is_reported_in_korean():
    from stream2clip.live import LiveConfig

    now = [0.0]

    class Short(FakeSaved):
        def __init__(self):
            super().__init__(1)
            self.note = "the replay buffer holds 20 s but the clip wanted 40 s: raise ..."

    hub = Hub()
    auto = AutoClipper(hub, lambda trigger: Short(), config=LiveConfig(lag=0.5, chat_delay=0.0, tail=0.0), clock=lambda: now[0], poll=0.01).start()
    try:
        hub.publish(OverlayEvent("twitch", "chat", "me", (("text", "!clip"),), role="owner", time=1.0))
        now[0] = 20.0
        assert wait_for(lambda: any("리플레이 버퍼 길이 20초" in e.text for e in hub.history))
    finally:
        auto.stop()


def test_preflight_needs_ffmpeg():
    from debutkit.clip import preflight

    assert "ffmpeg 필요" in preflight(lambda: None)
    assert preflight(lambda: "ffmpeg") is None


def test_clipper_check_errors_are_korean():
    from debutkit.clip import _KoreanClipper

    class Inner:
        def check(self, *, start_buffer=False):
            raise RuntimeError("OBS accepted the request, but the replay buffer did not start.")

    with pytest.raises(RuntimeError, match="리플레이 버퍼를 시작하지 않음"):
        _KoreanClipper(Inner()).check(start_buffer=True)
