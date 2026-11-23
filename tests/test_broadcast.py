"""OBS 없이 바로 방송(broadcast.py, program_window.py): 설정 확인, 플랫폼별 서버, 스트림 키 보관, ffmpeg 명령, 장치와 인코더 찾기,
송출 화면 크기, 송출 관리(가짜 ffmpeg 프로세스로 시작, 진행 상황, 멈춤, 실패, 다시 연결), 서버 요청."""

from __future__ import annotations

import http.client
import json
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from types import SimpleNamespace

import pytest

from debutkit import broadcast as bc
from debutkit import program_window as pw
from debutkit.overlay.server import OverlayServer

# 진행 상황을 0.05초마다 쓰고 표준 입력에 q가 오면 끝나는 가짜 ffmpeg. 인자: 몇 초 뒤 스스로 끝날지, 오류 문장, 종료 코드, 몇 초 뒤 멈출지
FAKE_FFMPEG = r"""
import sys, threading, time
limit, error, code, stall = float(sys.argv[1]), sys.argv[2], int(sys.argv[3]), float(sys.argv[4])
stop = threading.Event()
threading.Thread(target=lambda: (sys.stdin.read(1), stop.set()), daemon=True).start()
began, frame = time.monotonic(), 0
if error:
    sys.stderr.write(error + "\n"); sys.stderr.flush()
while not stop.is_set() and (limit <= 0 or time.monotonic() - began < limit):
    if stall <= 0 or time.monotonic() - began < stall:  # stall초 뒤로는 프레임이 늘지 않음(창을 닫은 경우의 ffmpeg처럼)
        frame += 3
    sys.stdout.write(f"frame={frame}\nfps=30.0\nbitrate=4500.0kbits/s\nout_time_us={frame * 33333}\ndrop_frames=1\ndup_frames=0\nspeed=1.0x\nprogress=continue\n")
    sys.stdout.flush()
    time.sleep(0.05)
sys.stdout.write("progress=end\n")
sys.exit(0 if stop.is_set() else code)
"""
KEY = "live_abcd1234"


@pytest.fixture(autouse=True)
def _fresh_encoder_cache():
    bc._ENCODER_CACHE.clear()
    yield
    bc._ENCODER_CACHE.clear()


def fake_popen(limit: float = 0, error: str = "", code: int = 0, record: list | None = None, stall: float = 0):
    def popen(command, **kwargs):
        if record is not None:
            record.append(command)
        return subprocess.Popen([sys.executable, "-c", FAKE_FFMPEG, str(limit), error, str(code), str(stall)], **kwargs)
    return popen


class FakeWindow:
    """송출 화면 창 대신: 열면 핸들 77이 생기고 페이지가 화면 크기를 알린 것처럼 만든다."""

    def __init__(self, program: bc.ProgramState, width: float = 1280, height: float = 720, appear: bool = True) -> None:
        self.program, self.width, self.height, self.appear = program, width, height, appear
        self.launched: list[str] = []
        self.closed: list[int] = []
        self.tokens: set[str] = set()
        self.is_minimized = False

    def find_browser(self):
        return "msedge.exe"

    def launch(self, browser, url, profile, width, height):
        self.launched.append(url)
        token = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["window"][0]
        if self.appear:
            self.tokens = {token}
            self.program.update({"window": token, "width": self.width, "height": self.height, "ratio": 1, "hidden": False})

    def find(self, token):
        return 77 if token in self.tokens else None

    def minimized(self, hwnd):
        return self.is_minimized

    def close(self, hwnd):
        self.closed.append(hwnd)
        self.tokens = set()


def fake_run(working=("h264_qsv", "libx264")):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if "-list_devices" in command:
            return SimpleNamespace(returncode=1, stdout=b"", stderr=DEVICES.encode("utf-8"))
        encoder = command[command.index("-c:v") + 1]
        return SimpleNamespace(returncode=0 if encoder in working else 1, stdout=b"", stderr=b"")
    run.calls = calls  # type: ignore[attr-defined]
    return run


DEVICES = """[in#0 @ 000001] "720p HD Camera" (video)
[in#0 @ 000001]   Alternative name "@device_pnp_\\\\?\\usb#vid_0000"
[in#0 @ 000001] "마이크 배열(디지털 마이크용 인텔® 스마트 사운드 기술)" (audio)
[in#0 @ 000001]   Alternative name "@device_cm_{33D9A762-90C8-11D0-BD43-00A0C911CE86}\\wave_{74DF2960-0DB8-4986-B852-7DF3783C6A0A}"
[in#0 @ 000001] "스테레오 믹스(Realtek(R) Audio)" (audio)
[in#0 @ 000001] "OBS Virtual Camera" (none)
[in#0 @ 000001]   Alternative name "@device_sw_{860BB310}"
"""


def make(tmp_path: Path, **options) -> tuple[bc.Broadcaster, FakeWindow]:
    program = bc.ProgramState()
    window = FakeWindow(program, **options.pop("window", {}))
    defaults = dict(ffmpeg=lambda: "ffmpeg", window=window, popen=fake_popen(), run=fake_run(), platform="win32", wait_window=2.0,
                    retry_delay=0.01, stable=0.5, config_file=tmp_path / "broadcast.json", keys_file=tmp_path / "keys.json", key_reader=lambda name: KEY)
    defaults.update(options)
    broadcaster = bc.Broadcaster(program, lambda: 8790, **defaults)
    bc.save_config(bc.from_request({"platform": "custom", "server": "rtmp://127.0.0.1:1935/live"}), tmp_path / "broadcast.json")
    return broadcaster, window


def wait_for(broadcaster: bc.Broadcaster, states: tuple[str, ...], seconds: float = 10.0) -> dict:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        status = broadcaster.status()
        if status["state"] in states:
            return status
        time.sleep(0.05)
    raise AssertionError(f"state {broadcaster.status()['state']} not in {states}")


# --- 설정 ----------------------------------------------------------------------------------


def test_config_validation_and_platform_servers(tmp_path):
    config = bc.BroadcastConfig()
    assert config.platform == "chzzk" and config.quality == "720p30" and config.server_url() == ""
    for bad in ({"platform": "afreeca"}, {"server": "http://example.com/live"}, {"server": "rtmp://"}, {"server": "rtmp://a b/live"},
                {"quality": "4k"}, {"kbps": 100}, {"kbps": True}, {"encoder": "h265"}, {"mic": 'a"b'}, {"title": "x" * 41},
                {"background": "zzz"}, {"camera": "yes"}, {"server": 5}):
        with pytest.raises(bc.BroadcastError):
            bc.from_request(bad, config)
    config = bc.from_request({"server": " rtmp://rtmp.example.kr/live/ ", "title": "  첫   방송 ", "background": "#FFAA00", "camera": True})
    assert config.servers == {"chzzk": "rtmp://rtmp.example.kr/live"} and config.title == "첫 방송" and config.background == "ffaa00"
    youtube = bc.from_request({"platform": "youtube"}, config)
    assert youtube.server == "" and youtube.server_url() == "rtmps://a.rtmps.youtube.com/live2"
    back = bc.from_request({"platform": "chzzk"}, youtube)
    assert back.server_url() == "rtmp://rtmp.example.kr/live"  # 플랫폼마다 따로 기억
    cleared = bc.from_request({"server": ""}, back)
    assert cleared.servers == {} and cleared.to_dict()["server"] == ""
    soop = bc.from_request({"platform": "soop", "server": "rtmp://soop.example/app"}, config)
    assert soop.servers == {"chzzk": "rtmp://rtmp.example.kr/live", "soop": "rtmp://soop.example/app"}

    path = tmp_path / "broadcast.json"
    bc.save_config(soop, path)
    assert bc.load_config(path) == soop
    path.write_text(json.dumps({"platform": "nope", "quality": "720p30", "kbps": -5, "servers": {"youtube": "ftp://x", "bogus": "rtmp://a/b",
                                                                                                "twitch": "rtmps://live.twitch.tv:443/app"}}), encoding="utf-8")
    loaded = bc.load_config(path)
    assert loaded.platform == "chzzk" and loaded.kbps == 0 and loaded.servers == {"twitch": "rtmps://live.twitch.tv:443/app"}
    path.write_text("[1, 2]", encoding="utf-8")
    assert bc.load_config(path) == bc.BroadcastConfig()
    assert bc.load_config(tmp_path / "missing.json") == bc.BroadcastConfig()


def test_bitrate_is_capped_by_platform():
    assert bc.from_request({"platform": "twitch", "quality": "1080p60"}).video_kbps() == 6000
    assert bc.from_request({"platform": "youtube", "quality": "1080p60"}).video_kbps() == 8000
    assert bc.from_request({"platform": "youtube", "quality": "720p30", "kbps": 3000}).video_kbps() == 3000
    assert bc.from_request({"platform": "chzzk", "kbps": 15000}).video_kbps() == 8000


def test_stream_keys_are_sealed_and_masked(tmp_path):
    path = tmp_path / "keys.json"
    seal = lambda raw: b"S" + raw[::-1]  # noqa: E731
    unseal = lambda raw: raw[1:][::-1]  # noqa: E731
    assert bc.check_key("  live_123-abc?bandwidthtest=true \n") == "live_123-abc?bandwidthtest=true"
    for bad in ("", "abc", "has space", "a/b/c/d", "키값키값", "x" * 300, None):
        with pytest.raises(bc.BroadcastError):
            bc.check_key(bad)
    bc.save_key("twitch", " " + KEY, path, protect=seal)
    assert KEY not in path.read_text(encoding="utf-8")
    assert bc.load_key("twitch", path, unprotect=unseal) == KEY and bc.has_key("twitch", path) and not bc.has_key("soop", path)
    assert bc.load_key("twitch", path, unprotect=lambda raw: (_ for _ in ()).throw(OSError("other user"))) is None
    assert bc.load_key("soop", path, unprotect=unseal) is None
    assert bc.clear_key("twitch", path) and not bc.clear_key("twitch", path) and not bc.has_key("twitch", path)
    assert bc.mask(f"rtmp://x/app/{KEY} failed {KEY}", KEY, "") == "rtmp://x/app/**** failed ****"
    with pytest.raises(bc.BroadcastError, match="치지직 송출 서버 주소 필요"):
        bc.publish_url(bc.BroadcastConfig(), KEY)
    assert bc.publish_url(bc.from_request({"platform": "twitch"}), KEY) == f"rtmps://live.twitch.tv:443/app/{KEY}"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI")
def test_dpapi_round_trip(tmp_path):
    path = tmp_path / "keys.json"
    bc.save_key("youtube", KEY, path)
    assert KEY not in path.read_text(encoding="utf-8") and bc.load_key("youtube", path) == KEY


# --- ffmpeg ------------------------------------------------------------------------------


def test_device_list_and_encoder_detection():
    devices = bc.parse_devices(DEVICES)
    assert devices == [bc.AudioDevice("마이크 배열(디지털 마이크용 인텔® 스마트 사운드 기술)",
                                      "@device_cm_{33D9A762-90C8-11D0-BD43-00A0C911CE86}\\wave_{74DF2960-0DB8-4986-B852-7DF3783C6A0A}"),
                       bc.AudioDevice("스테레오 믹스(Realtek(R) Audio)", "스테레오 믹스(Realtek(R) Audio)")]
    run = fake_run()
    assert bc.audio_devices("ffmpeg-a", run) == devices
    assert bc.detect_encoder("ffmpeg-a", run, refresh=True) == "h264_qsv"
    tried = [command[command.index("-c:v") + 1] for command in run.calls if "-c:v" in command]
    assert tried == ["h264_nvenc", "h264_qsv"]
    assert bc.detect_encoder("ffmpeg-a", fake_run(working=())) == "h264_qsv"  # 기억한 값
    assert bc.detect_encoder("ffmpeg-a", fake_run(working=()), refresh=True) is None

    def broken(command, **kwargs):
        raise OSError("missing")
    assert bc.audio_devices("ffmpeg-b", broken) == [] and bc.encoder_works("ffmpeg-b", "libx264", broken) is False


def test_stage_crop_skips_title_bar_and_bars():
    exact = bc.stage_crop(1280, 720, 1)
    assert (exact.width, exact.height, exact.x, exact.y) == (1280, 720, "(iw-1280)/2+0", "ih-720+0")
    tall = bc.stage_crop(1280, 728, 1)  # 위아래 4픽셀 여백
    assert (tall.width, tall.height, tall.y) == (1280, 720, "ih-728+4")
    wide = bc.stage_crop(1600, 720, 1.25)  # 화면 2000x900, 무대 1600x900
    assert (wide.width, wide.height, wide.x, wide.y) == (1600, 900, "(iw-2000)/2+200", "ih-900+0")
    odd = bc.stage_crop(1001, 563, 1)
    assert odd.width % 2 == 0 and odd.height % 2 == 0


def test_command_and_encoder_settings():
    quality = bc.QUALITIES["1080p30"]
    crop = bc.stage_crop(1920, 1080, 1)
    silent = bc.build_command("ff", hwnd=77, crop=crop, quality=quality, kbps=6000, encoder="h264_qsv", keyframe=2, url=f"rtmp://x/app/{KEY}")
    graph = silent[silent.index("-filter_complex") + 1]
    assert silent[-1] == f"rtmp://x/app/{KEY}" and silent[:2] == ["ff", "-hide_banner"] and "-i" not in silent
    assert "gfxcapture=hwnd=77:capture_cursor=0:max_framerate=30" in graph and "crop=w=1920:h=1080:x=(iw-1920)/2+0:y=ih-1080+0" in graph
    assert "scale=1920:1080" in graph and "format=nv12,fps=30[v]" in graph and "anullsrc=r=48000:cl=stereo[a]" in graph
    assert ["-progress", "pipe:1"] == silent[silent.index("-progress"):silent.index("-progress") + 2]
    assert silent[silent.index("-g") + 1] == "60" and silent[silent.index("-b:v") + 1] == "6000k" and silent[silent.index("-maxrate") + 1] == "6000k"
    mic = bc.build_command("ff", hwnd=1, crop=crop, quality=quality, kbps=6000, encoder="libx264", keyframe=1, url="rtmp://x/a/k", mic="Mic")
    assert mic[mic.index("-i") + 1] == "audio=Mic" and "[0:a]aresample=48000" in mic[mic.index("-filter_complex") + 1]
    assert "format=yuv420p" in mic[mic.index("-filter_complex") + 1] and mic[mic.index("-g") + 1] == "30"
    both = bc.build_command("ff", hwnd=1, crop=crop, quality=quality, kbps=6000, encoder="h264_nvenc", keyframe=2, url="rtmp://x/a/k",
                            mic="Mic", extra_audio="스테레오 믹스")
    assert [both[i + 1] for i, part in enumerate(both) if part == "-i"] == ["audio=Mic", "audio=스테레오 믹스"]
    assert "amix=inputs=2:duration=longest:normalize=0[a]" in both[both.index("-filter_complex") + 1]
    for encoder in bc.ENCODERS:
        args = bc.encoder_args(encoder, 4500, 30, 2)
        assert args[:2] == ["-c:v", encoder] and "4500k" in args and args[args.index("-pix_fmt") + 1] in ("nv12", "yuv420p")
    assert "nal-hrd=cbr" in bc.encoder_args("libx264", 4500, 30, 2) and "cbr" in bc.encoder_args("h264_nvenc", 4500, 30, 2)


def test_failure_messages():
    assert "캡처하지 못함" in bc.describe_failure(["[Parsed_gfxcapture_0] Failed to find capture source"])
    no_gpu = ["[Parsed_gfxcapture_0 @ 0001] Failed to create D3D11VA device.", "[Parsed_gfxcapture_0 @ 0001] Failed to configure output pad",
              "[vost#0:0/libx264] [enc:libx264] Could not open encoder before EOF"]
    assert bc.describe_failure(no_gpu).startswith("그래픽 장치(D3D11)를 열지 못해")  # 인코더 문제로 보이지 않게
    assert "소리 장치를 열지 못함" in bc.describe_failure(["[dshow] Could not find audio only device with name [x] among source devices"])
    assert "연결하지 못함" in bc.describe_failure(["[tcp] Connection to tcp://127.0.0.1:1935 failed: Error number -138 occurred"])
    assert "스트림 키" in bc.describe_failure(["[rtmp] Server error: NetStream.Publish.BadName"])
    assert "x264" in bc.describe_failure(["[h264_nvenc] OpenEncodeSessionEx failed"])
    assert bc.describe_failure(["", "something odd"]) == "ffmpeg 종료: something odd"
    assert bc.describe_failure([]) == "ffmpeg가 예기치 않게 종료"


def test_program_state_reports():
    state = bc.ProgramState()
    assert state.update({"window": "ab12cd34", "width": 1280, "height": 720, "ratio": 1.25, "hidden": False})
    assert state.get("ab12cd34")["ratio"] == 1.25 and state.get("other") is None
    for bad in ({"window": "AB", "width": 1, "height": 1, "ratio": 1}, {"window": "ab12cd34", "width": True, "height": 1, "ratio": 1},
                {"window": "ab12cd34", "width": 0, "height": 720, "ratio": 1}, {"window": "ab12cd34", "width": 10, "height": 10, "ratio": 20},
                {"window": "ab12cd34"}, {"window": "../x", "width": 1, "height": 1, "ratio": 1}):
        assert not state.update(bad)
    for index in range(10):
        state.update({"window": f"tok{index:05d}", "width": 1, "height": 1, "ratio": 1})
    assert state.get("ab12cd34") is None and state.get("tok00009") is not None  # 오래된 창 기록은 버린다


def test_browser_and_window_helpers():
    environ = {"ProgramFiles(x86)": r"C:\PF86", "ProgramFiles": r"C:\PF", "LOCALAPPDATA": r"C:\Users\me\AppData\Local"}
    paths = pw.browser_candidates(environ)
    assert paths[0] == Path(r"C:\PF86", "Microsoft", "Edge", "Application", "msedge.exe") and paths[-1].name == "chrome.exe"
    assert pw.find_browser(lambda path: path.name == "chrome.exe", environ) == str(Path(r"C:\PF86", "Google", "Chrome", "Application", "chrome.exe"))
    assert pw.find_browser(lambda path: False, environ) is None
    edge = pw.browser_args("C:/x/msedge.exe", "http://127.0.0.1:8790/program?window=ab12cd34", Path("prof"), 1280, 720)
    assert "--inprivate" in edge and "--window-size=1296,759" in edge and "--force-device-scale-factor=1" in edge
    assert edge[1] == "--app=http://127.0.0.1:8790/program?window=ab12cd34" and "--disable-features=CalculateNativeWinOcclusion" in edge
    assert "--inprivate" not in pw.browser_args("C:/x/chrome.exe", "http://x", Path("prof"), 1920, 1080)
    listing = lambda: [(1, "Chrome_WidgetWin_1", "debutkit program - 개인 - Microsoft Edge"),  # noqa: E731 - 평소 브라우저 탭
                       (2, "Notepad", "debutkit program ab12cd34"), (3, "Chrome_WidgetWin_1", "debutkit program ab12cd34 - [InPrivate]")]
    assert pw.find("ab12cd34", listing) == 3 and pw.find("zz99zz99", listing) is None
    assert pw.available("win32") and not pw.available("darwin")


# --- 송출 관리 -----------------------------------------------------------------------------


def test_broadcast_goes_live_and_stops(tmp_path):
    record: list = []
    broadcaster, window = make(tmp_path, popen=fake_popen(record=record))
    status = broadcaster.start()
    assert status["state"] == "starting"
    live = wait_for(broadcaster, ("live",))
    assert live["encoder"] == "h264_qsv" and live["encoder_name"] == "Intel Quick Sync" and live["window"] is True
    assert live["stats"]["frames"] > 0 and live["stats"]["kbps"] == 4500 and live["stats"]["dropped"] == 1
    assert broadcaster.start()["state"] == "live"  # 이미 방송 중이면 그대로
    command = record[0]
    assert command[-1] == f"rtmp://127.0.0.1:1935/live/{KEY}" and "gfxcapture=hwnd=77" in command[command.index("-filter_complex") + 1]
    assert KEY not in json.dumps(broadcaster.status(), ensure_ascii=False)
    assert window.launched and "/program?window=" in window.launched[0] and "bg=2a1f3d" in window.launched[0]
    stopped = broadcaster.stop()
    assert stopped["state"] == "off" and broadcaster._process is None and not window.closed
    broadcaster.stop(close_window=True)
    assert window.closed == [77]


def test_broadcast_reports_quick_failure_without_key(tmp_path):
    broadcaster, _ = make(tmp_path, popen=fake_popen(limit=0.1, error=f"[out#0/flv] Error opening output rtmp://x/app/{KEY}: Error number -138 occurred",
                                                     code=1), stable=5.0)  # 느린 CI의 파이썬 시작 시간까지 짧은 실행으로
    broadcaster.start()
    failed = wait_for(broadcaster, ("error",))
    assert "송출 서버에 연결하지 못함" in failed["error"] and KEY not in failed["error"]
    assert broadcaster.stop()["error"] == failed["error"]  # 최근 오류는 남긴다


def test_broadcast_reconnects_after_long_run(tmp_path):
    record: list = []
    broadcaster, _ = make(tmp_path, popen=fake_popen(limit=0.6, error="[rtmp] Broken pipe", code=1, record=record), stable=0.3)
    notes: list[str] = []
    broadcaster.notify = notes.append
    broadcaster.start()
    deadline = time.monotonic() + 10
    while len(record) < 3 and time.monotonic() < deadline:
        time.sleep(0.05)
    assert len(record) >= 3 and broadcaster.status()["state"] in ("live", "retrying")
    assert "방송 시작" in notes and any("다시 연결" in note for note in notes)
    assert broadcaster.stop()["state"] == "off"


def test_closing_the_window_stops_without_retrying(tmp_path):
    record: list = []
    broadcaster, window = make(tmp_path, popen=fake_popen(limit=0.6, error="[Parsed_gfxcapture_0] capture item closed", code=1, record=record), stable=0.3)
    broadcaster.start()
    wait_for(broadcaster, ("live",))
    window.tokens = set()  # 사용자가 송출 화면 창을 닫음
    failed = wait_for(broadcaster, ("error",))
    assert "창이 닫혀" in failed["error"] and len(record) == 1
    broadcaster.stop()


def test_stall_watchdog(tmp_path, monkeypatch):
    monkeypatch.setattr(bc, "STALL_SECONDS", 1.5)  # 느린 CI에서도 감시 스레드가 늦게 돌아 잘못 끝내지 않을 여유
    record: list = []
    broadcaster, window = make(tmp_path, popen=fake_popen(stall=0.3, record=record))
    broadcaster.poll_interval = 0.05
    broadcaster.start()
    wait_for(broadcaster, ("live",))
    window.is_minimized = True  # 최소화: 프레임이 멈춰도 기다린다(창을 다시 띄우면 이어서 송출)
    time.sleep(2.5)
    assert broadcaster.status()["state"] == "live" and broadcaster._process is not None and len(record) == 1
    window.is_minimized = False  # 다시 띄운 직후에는 멈춤 시간을 새로 잰다
    time.sleep(0.3)
    assert broadcaster._process is not None and len(record) == 1
    window.tokens = set()  # 창을 닫으면 ffmpeg가 멈춰 있으므로 끝내고 이유 표시
    failed = wait_for(broadcaster, ("error",))
    assert "창이 닫혀" in failed["error"] and len(record) == 1
    broadcaster.stop()


def test_broadcast_start_checks(tmp_path):
    broadcaster, _ = make(tmp_path, key_reader=lambda name: None)
    with pytest.raises(bc.BroadcastError, match="스트림 키를 먼저 저장"):
        broadcaster.start()
    broadcaster, _ = make(tmp_path, platform="darwin")
    with pytest.raises(bc.BroadcastError, match="Windows"):
        broadcaster.start()
    with pytest.raises(bc.BroadcastError, match="Windows"):
        broadcaster.open_window()
    broadcaster, _ = make(tmp_path, ffmpeg=lambda: None)
    with pytest.raises(bc.BroadcastError, match="ffmpeg 필요"):
        broadcaster.start()
    broadcaster, _ = make(tmp_path)
    broadcaster.update_config({"platform": "soop"})
    with pytest.raises(bc.BroadcastError, match="SOOP 송출 서버 주소 필요"):
        broadcaster.start()
    broadcaster, _ = make(tmp_path, window={"appear": False}, wait_window=0.3)
    broadcaster.start()
    assert "송출 화면 창이 열리지 않음" in wait_for(broadcaster, ("error",))["error"]
    broadcaster, _ = make(tmp_path, run=fake_run(working=()))
    broadcaster.start()
    assert "인코더 없음" in wait_for(broadcaster, ("error",))["error"]


def test_window_reuse_reopen_and_warnings(tmp_path):
    broadcaster, window = make(tmp_path, window={"width": 640, "height": 360})
    broadcaster.open_window()
    broadcaster.open_window()  # 이미 열림: 다시 열지 않음
    assert len(window.launched) == 1
    broadcaster.update_config({"title": "첫 방송"})
    broadcaster.open_window()  # 화면 구성 변경: 닫고 다시 연다
    assert len(window.launched) == 2 and window.closed == [77] and "title=" in window.launched[1]
    broadcaster.start()
    wait_for(broadcaster, ("live",))
    warnings = broadcaster.status()["warnings"]
    assert any("창이 작아" in text for text in warnings)  # 640x360 창으로 720p 송출
    window.is_minimized = True
    broadcaster.program.update({"window": broadcaster._token, "width": 700, "height": 360, "ratio": 1})
    warnings = broadcaster.status()["warnings"]
    assert any("최소화" in text for text in warnings) and any("크기가 바뀜" in text for text in warnings)
    broadcaster.update_config({"title": "바꾼 제목"})
    broadcaster.open_window()  # 방송 중에는 다시 열지 않음
    assert len(window.launched) == 2
    window.tokens = set()
    assert broadcaster.status()["warnings"] == ["송출 화면 창이 닫힘: 방송을 끝내고 다시 시작"]
    broadcaster.stop()


def test_devices_and_key_through_broadcaster(tmp_path, monkeypatch):
    monkeypatch.setattr(bc, "_dpapi", lambda raw, protect: (b"S" + raw) if protect else raw[1:])
    broadcaster, _ = make(tmp_path, key_reader=None)
    found = broadcaster.devices()
    assert found["ffmpeg"] and found["encoder"] in ("h264_qsv", None) and len(found["audio"]) == 2
    assert broadcaster.set_key(KEY)["key_saved"] is True
    assert bc.load_key("custom", tmp_path / "keys.json") == KEY
    assert broadcaster.set_key(None)["key_saved"] is False
    with pytest.raises(bc.BroadcastError):
        broadcaster.set_key("bad key")
    assert make(tmp_path, ffmpeg=lambda: None)[0].devices() == {"ffmpeg": False, "audio": [], "encoder": None}


# --- 서버 요청 ----------------------------------------------------------------------------


def request(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, data


def test_server_routes(monkeypatch):
    monkeypatch.setattr(bc, "_dpapi", lambda raw, protect: (b"S" + raw) if protect else raw[1:])
    srv = OverlayServer(port=0).start()
    try:
        broadcaster = srv.broadcast
        broadcaster.window = FakeWindow(srv.program)
        broadcaster._ffmpeg = lambda: "ffmpeg"
        broadcaster._run = fake_run()
        broadcaster._popen = fake_popen()
        broadcaster._platform = "win32"
        for path in ("/program", "/broadcast/control"):
            code, body = request(srv.port, "GET", path)
            assert code == 200 and b"<html" in body
        code, body = request(srv.port, "POST", "/program/size", {"window": "ab12cd34", "width": 1280, "height": 720, "ratio": 1})
        assert code == 200 and json.loads(body) == {"ok": True} and srv.program.get("ab12cd34")
        assert json.loads(request(srv.port, "POST", "/program/size", {"window": "x"})[1]) == {"ok": False}
        code, body = request(srv.port, "GET", "/broadcast")
        status = json.loads(body)
        assert code == 200 and status["state"] == "off" and status["config"]["platform"] == "chzzk" and "twitch" in status["platforms"]
        code, body = request(srv.port, "POST", "/broadcast/config", {"platform": "youtube", "quality": "1080p30"})
        assert code == 200 and json.loads(body)["server"] == "rtmps://a.rtmps.youtube.com/live2" and json.loads(body)["video_kbps"] == 6000
        code, body = request(srv.port, "POST", "/broadcast/config", {"quality": "8k"})
        assert code == 400 and "화질" in json.loads(body)["error"]
        code, body = request(srv.port, "POST", "/broadcast/start")
        assert code == 400 and "스트림 키를 먼저 저장" in json.loads(body)["error"]
        code, body = request(srv.port, "POST", "/broadcast/key", {"key": KEY})
        assert code == 200 and json.loads(body)["key_saved"] is True and KEY.encode() not in body
        code, body = request(srv.port, "GET", "/broadcast/devices")
        assert code == 200 and json.loads(body)["encoder"] in ("h264_qsv", None)
        code, body = request(srv.port, "POST", "/broadcast/window")
        assert code == 200 and broadcaster.window.launched
        code, body = request(srv.port, "POST", "/broadcast/start")
        assert code == 200 and json.loads(body)["state"] in ("starting", "live")
        wait_for(broadcaster, ("live",))
        code, body = request(srv.port, "POST", "/broadcast/stop", {"close": True})
        assert code == 200 and json.loads(body)["state"] == "off" and broadcaster.window.closed == [77]
        code, body = request(srv.port, "POST", "/broadcast/key", {"clear": True})
        assert json.loads(body)["key_saved"] is False
    finally:
        srv.stop()


def test_cli_broadcast(capsys, monkeypatch):
    from debutkit.cli import main

    monkeypatch.setattr(bc, "_dpapi", lambda raw, protect: (b"S" + raw) if protect else raw[1:])
    srv = OverlayServer([], port=0).start()
    try:
        broadcaster = srv.broadcast
        broadcaster.window = FakeWindow(srv.program)
        broadcaster._ffmpeg = lambda: "ffmpeg"
        broadcaster._run = fake_run()
        broadcaster._popen = fake_popen()
        broadcaster._platform = "win32"
        port = str(srv.port)
        assert main(["broadcast", "--port", port, "status"]) == 0 and "방송 꺼짐" in capsys.readouterr().out
        assert main(["broadcast", "--port", port, "devices"]) == 0
        out = capsys.readouterr().out
        assert "Intel Quick Sync" in out and "스테레오 믹스" in out
        assert main(["broadcast", "--port", port, "set", "--platform", "twitch", "--quality", "1080p30", "--no-camera", "--title", "첫 방송"]) == 0
        out = capsys.readouterr().out
        assert "Twitch, 서버 rtmps://live.twitch.tv:443/app, 스트림 키 없음" in out and "영상 6000 kbps" in out
        assert main(["broadcast", "--port", port, "set", "--server", "http://x"]) == 1 and "rtmp://" in capsys.readouterr().err
        assert main(["broadcast", "--port", port, "start"]) == 1 and "스트림 키를 먼저 저장" in capsys.readouterr().err
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(KEY + "\n"))
        assert main(["broadcast", "--port", port, "key", "--stdin"]) == 0
        out = capsys.readouterr().out
        assert "스트림 키 저장됨" in out and KEY not in out
        monkeypatch.setattr("getpass.getpass", lambda prompt: "  " + KEY)
        assert main(["broadcast", "--port", port, "key", "--platform", "youtube"]) == 0
        assert bc.has_key("youtube")
        capsys.readouterr()
        assert main(["broadcast", "--port", port, "window"]) == 0 and broadcaster.window.launched
        assert main(["broadcast", "--port", port, "start"]) == 0
        out = capsys.readouterr().out
        assert "방송 중" in out and "초당 30.0 프레임" in out and KEY not in out
        assert main(["broadcast", "--port", port, "stop", "--close"]) == 0 and "방송 꺼짐" in capsys.readouterr().out
        assert broadcaster.window.closed == [77]
        assert main(["broadcast", "--port", port, "key", "--clear"]) == 0 and "스트림 키 없음" in capsys.readouterr().out
    finally:
        srv.stop()
    assert main(["broadcast", "--port", port, "status"]) == 1 and "오버레이에 연결하지 못함" in capsys.readouterr().err
