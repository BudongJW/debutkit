"""실제 OBS로 장면 생성, 고급 출력 모드 리플레이 버퍼, 자동 클립을 검증한다(CI용, .github/workflows/verify.yml).

    python packaging/verify_obs.py configure   # OBS 설정 파일 준비(첫 실행 안내 생략, WebSocket 사용, 고급 출력 모드)
    python packaging/verify_obs.py start 이름  # OBS 실행(출력은 RUNNER_TEMP/obs-이름.log)과 WebSocket 응답 대기
    python packaging/verify_obs.py wait        # OBS WebSocket 응답 대기
    python packaging/verify_obs.py scenes      # debutkit scenes --replay-buffer 30 실행과 결과 확인
    python packaging/verify_obs.py stop        # OBS 종료(정상 종료 요청 후 30초가 지나면 강제 종료)
    python packaging/verify_obs.py clip        # debutkit overlay --clip 실행, 스트리머 !clip 입력, 클립 파일 확인
    python packaging/verify_obs.py voice       # 시험음을 재생하는 미디어 소스로 캐릭터 음성 반응(InputVolumeMeters) 확인
    python packaging/verify_obs.py camera      # debutkit camera setup으로 SRT 수신 소스 생성, ffmpeg가 휴대폰처럼 송신, 재생 상태와 틀린 암호 거부 확인
    python packaging/verify_obs.py logs        # OBS 출력과 로그 파일의 마지막 부분 출력

Windows, macOS, Linux에서 같은 순서로 실행한다. configure는 이 PC의 OBS 설정을 덮어쓰므로
CI 전용 컴퓨터에서만 실행한다(DEBUTKIT_VERIFY_OBS=1 필요).
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HOST, PORT = "127.0.0.1", 4455
OVERLAY_PORT = 8791
TEMP = Path(os.environ.get("RUNNER_TEMP") or "/tmp")
RECORDINGS = TEMP / "obs-recordings"
CLIPS = TEMP / "debutkit-clips"
PID_FILE = TEMP / "obs.pid"
SCENES = ["대기 화면", "본방송", "토크", "자리 비움", "엔딩"]


def config_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ["APPDATA"]) / "obs-studio"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "obs-studio"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "obs-studio"


def configure() -> None:
    if os.environ.get("DEBUTKIT_VERIFY_OBS") != "1":
        raise SystemExit("OBS 설정을 덮어쓰므로 CI에서만 실행(DEBUTKIT_VERIFY_OBS=1)")
    root = config_dir()
    RECORDINGS.mkdir(parents=True, exist_ok=True)
    # 브라우저 소스 하드웨어 가속 끔: 가상 화면(Xvfb)에서 Chromium GPU 프로세스가 실패하면 OBS 전체가 종료됨
    # MacOSPermissionsDialogLastShown: macOS 첫 실행의 권한 안내 창 생략
    general = ("[General]\nFirstRun=true\nEnableAutoUpdates=false\nBrowserHWAccel=false\nMacOSPermissionsDialogLastShown=99\n\n"
               "[Basic]\nProfile=Untitled\nProfileDir=Untitled\nSceneCollection=Untitled\nSceneCollectionFile=Untitled\n")
    for name in ("global.ini", "user.ini"):  # OBS 31부터 사용자 설정은 user.ini
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(general, encoding="utf-8")
    profile = root / "basic" / "profiles" / "Untitled"
    profile.mkdir(parents=True, exist_ok=True)
    (profile / "basic.ini").write_text(
        "[General]\nName=Untitled\n\n[Video]\nBaseCX=1280\nBaseCY=720\nOutputCX=1280\nOutputCY=720\nFPSType=0\nFPSCommon=30\n\n"
        f"[Output]\nMode=Advanced\n\n[AdvOut]\nRecType=Standard\nRecFilePath={RECORDINGS.as_posix()}\nRecFormat2=mkv\nRecEncoder=obs_x264\n", encoding="utf-8")
    websocket = root / "plugin_config" / "obs-websocket"
    websocket.mkdir(parents=True, exist_ok=True)
    (websocket / "config.json").write_text(json.dumps({"alerts_enabled": False, "auth_required": False, "first_load": False,
                                                       "server_enabled": True, "server_password": "", "server_port": PORT}), encoding="utf-8")
    print(f"OBS 설정 준비: {root} (고급 출력 모드, 녹화 위치 {RECORDINGS})")


def obs_command() -> tuple[list[str], Path | None]:
    """(실행 명령, 실행 폴더). Windows OBS는 실행 폴더를 기준으로 data 폴더를 찾는다."""
    if sys.platform == "win32":
        folder = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "obs-studio" / "bin" / "64bit"
        return [str(folder / "obs64.exe"), "--disable-shutdown-check", "--disable-updater"], folder
    if sys.platform == "darwin":
        return ["/Applications/OBS.app/Contents/MacOS/OBS", "--disable-shutdown-check"], None
    return ["obs", "--disable-shutdown-check", "--minimize-to-tray"], None


def running(pid: int) -> bool:
    if sys.platform == "win32":
        found = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"], capture_output=True, text=True, errors="replace").stdout
        return f'"{pid}"' in found
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def start(name: str) -> None:
    command, folder = obs_command()
    log = open(TEMP / f"obs-{name}.log", "w", encoding="utf-8")  # noqa: SIM115 - OBS가 계속 기록
    if sys.platform == "win32":
        detach = {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        detach = {"start_new_session": True}
    process = subprocess.Popen(command, cwd=folder, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **detach)
    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    print(f"OBS 실행: {command[0]} (PID {process.pid})")
    wait()


def stop(timeout: float = 30.0) -> None:
    pid = int(PID_FILE.read_text(encoding="utf-8"))
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid)], capture_output=True)
    elif running(pid):
        os.kill(pid, signal.SIGTERM)
    end = time.monotonic() + timeout
    while running(pid) and time.monotonic() < end:
        time.sleep(1)
    if running(pid):
        print("정상 종료되지 않아 강제 종료")
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        else:
            os.kill(pid, signal.SIGKILL)
        time.sleep(2)
    print("OBS 종료")


def logs(lines: int = 80) -> None:
    files = sorted(TEMP.glob("obs-*.log"))
    newest = sorted((config_dir() / "logs").glob("*.txt"), key=lambda path: path.stat().st_mtime)[-2:]
    for path in [*files, *newest]:
        text = path.read_text(encoding="utf-8", errors="replace").splitlines()
        print(f"==> {path} <==")
        print("\n".join(text[-lines:]))


def client():
    from stream2clip.obs import ObsClient

    return ObsClient(HOST, PORT, None, events=0)


def wait(timeout: float = 150.0) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            with socket.create_connection((HOST, PORT), timeout=1):
                break
        except OSError:
            time.sleep(1)
    else:
        raise SystemExit("OBS WebSocket 응답 없음")
    for _ in range(30):  # 포트가 열린 직후에는 인증 단계가 준비되지 않을 수 있음
        try:
            with client() as obs:
                version = obs.request("GetVersion")
                print(f"OBS {version.get('obsVersion')}, WebSocket {version.get('obsWebSocketVersion')}, {version.get('platformDescription')}")
                return
        except Exception as error:  # noqa: BLE001
            last = error
            time.sleep(2)
    raise SystemExit(f"OBS 연결 실패: {last}")


def scenes() -> None:
    from debutkit.scenes import SceneOptions, connect_and_apply, format_report

    report, planned = connect_and_apply(HOST, PORT, None, SceneOptions(avatar="vts"), switch=True, replay_buffer=30)
    print(format_report(report))
    with client() as obs:
        kinds = obs.request("GetInputKindList", {"unversioned": False}).get("inputKinds", [])
        print("사용 가능한 캡처 소스:", ", ".join(kind for kind in kinds if "capture" in kind or "input" in kind))
        names = [scene["sceneName"] for scene in obs.request("GetSceneList").get("scenes", [])]
        inputs = {item["inputName"]: item.get("inputKind") for item in obs.request("GetInputList").get("inputs", [])}
        mode = obs.request("GetProfileParameter", {"parameterCategory": "Output", "parameterName": "Mode"}).get("parameterValue")
        replay = {name: obs.request("GetProfileParameter", {"parameterCategory": "AdvOut", "parameterName": name}).get("parameterValue")
                  for name in ("RecRB", "RecRBTime")}
        current = obs.request("GetCurrentProgramScene").get("currentProgramSceneName")
    missing = [name for name in SCENES if name not in names]
    if missing:
        raise SystemExit(f"장면 누락: {missing}")
    created = {name: kind for name, kind in inputs.items() if name.startswith("[DK] ")}
    print("장면:", ", ".join(SCENES), f"(현재 {current})")
    for name, kind in sorted(created.items()):
        print(f"  {name}: {kind}")
    print(f"출력 모드 {mode}, 리플레이 버퍼 설정 {replay}")
    if str(mode).lower() != "advanced" or str(replay["RecRB"]).lower() not in ("true", "1") or str(replay["RecRBTime"]) != "30":
        raise SystemExit("고급 출력 모드의 리플레이 버퍼 설정이 저장되지 않음")
    if len(created) < 7:
        raise SystemExit(f"debutkit 소스가 부족함: {len(created)}개")
    if not any(name.startswith("[DK] 아바타") for name in created):
        if not any(note.startswith("이 OBS에는 창 캡처 소스가 없어") for note in report.notes):
            raise SystemExit("아바타 소스가 없는데 안내도 없음")
        print("아바타 소스: 창 캡처 소스 종류가 없어 생략(안내 표시 확인)")


def clip(timeout: float = 120.0) -> None:
    import queue
    import threading

    CLIPS.mkdir(parents=True, exist_ok=True)
    # 파이프로 받는 출력은 기본으로 블록 단위 버퍼링: 줄 단위로 받도록 버퍼링 해제
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    overlay = subprocess.Popen([sys.executable, "-m", "debutkit", "overlay", "--port", str(OVERLAY_PORT), "--clip", "--clip-dir", str(CLIPS)],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", env=env)
    lines: queue.Queue[str] = queue.Queue()

    def pump() -> None:
        for line in overlay.stdout or []:
            lines.put(line)

    threading.Thread(target=pump, daemon=True).start()
    try:
        deadline = time.monotonic() + 60
        while True:
            if time.monotonic() > deadline:
                raise SystemExit("자동 클립이 60초 안에 시작되지 않음")
            try:
                line = lines.get(timeout=1)
            except queue.Empty:
                if overlay.poll() is not None:
                    raise SystemExit(f"overlay 종료({overlay.returncode})") from None
                continue
            print("  " + line.rstrip())
            if "자동 클립: 사용" in line:
                break
        request = urllib.request.Request(f"http://127.0.0.1:{OVERLAY_PORT}/test", data=json.dumps({"kind": "chat", "role": "owner", "text": "!clip"}).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
        time.sleep(8)  # 리플레이 버퍼에 영상이 쌓일 시간
        urllib.request.urlopen(request, timeout=10).read()
        print("스트리머 !clip 입력")
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            while not lines.empty():
                print("  " + lines.get().rstrip())
            found = sorted(CLIPS.glob("*.mp4"))
            if found and found[-1].stat().st_size > 0:
                time.sleep(2)
                from stream2clip.ffmpeg import find_ffprobe

                probe = subprocess.run([find_ffprobe(), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(found[-1])],
                                       capture_output=True, text=True)
                duration = float(probe.stdout.strip() or 0)
                print(f"클립 저장 확인: {found[-1].name}, {found[-1].stat().st_size / 1024:.0f} KB, {duration:.1f}초")
                if duration <= 0:
                    raise SystemExit("클립 길이 0")
                return
            try:
                socket.create_connection((HOST, PORT), timeout=2).close()
            except OSError:
                raise SystemExit("OBS가 종료됨(OBS 로그 확인)") from None
            time.sleep(2)
        raise SystemExit("클립 파일이 만들어지지 않음")
    finally:
        overlay.terminate()
        try:
            overlay.wait(timeout=10)
        except subprocess.TimeoutExpired:
            overlay.kill()
        while not lines.empty():
            print("  " + lines.get().rstrip())


def voice(timeout: float = 30.0) -> None:
    """캐릭터 음성 반응: OBS 미디어 소스로 시험음(440 Hz)을 재생하고, 음량 이벤트로 말하는 상태가 되는지 확인."""
    from stream2clip.ffmpeg import find_ffmpeg

    from debutkit.overlay.voice import VoiceMeter, VoiceState

    tone = TEMP / "debutkit-tone.wav"
    subprocess.run([find_ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=60", "-ac", "2", str(tone)], check=True)
    name = "debutkit 음성 시험"
    with client() as obs:
        scene = obs.request("GetCurrentProgramScene").get("currentProgramSceneName")
        obs.request("CreateInput", {"sceneName": scene, "inputName": name, "inputKind": "ffmpeg_source",
                                    "inputSettings": {"is_local_file": True, "local_file": str(tone), "looping": True, "restart_on_activate": True}})
    state = VoiceState()
    subscriber, _ = state.subscribe()
    notes: list[str] = []
    meter = VoiceMeter(state, HOST, PORT, None, input_name=name, threshold=-40.0, notify=notes.append).start()
    try:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                update = subscriber.get(timeout=1)
            except Exception:
                continue
            if update["talking"]:
                print(f"말하는 상태 확인: {update['source']}, {update['db']} dBFS")
                print("  " + "\n  ".join(notes))
                return
        raise SystemExit("OBS 음량 이벤트로 말하는 상태가 되지 않음: " + "; ".join(notes))
    finally:
        meter.stop()
        with client() as obs:
            obs.request("RemoveInput", {"inputName": name})


def camera(timeout: float = 60.0) -> None:
    """휴대폰 카메라 영상: debutkit camera setup으로 OBS에 SRT 수신 미디어 소스를 만들고, ffmpeg를 휴대폰 앱처럼 SRT(Caller, 암호)로 보내
    화면이 실제로 그려지는지, debutkit 상태(휴대폰 연결 대기, 수신 중)가 맞는지, 틀린 암호는 연결되지 않는지 확인.
    OBS 미디어 상태는 SRT 수신 대기 중에도 재생 중(PLAYING)으로 표시되므로 단계마다 상태, 소스 크기, 화면 캡처를 함께 기록한다."""
    import base64

    from stream2clip.ffmpeg import find_ffmpeg

    from debutkit import camera as cameras

    ffmpeg = find_ffmpeg()
    protocols = subprocess.run([ffmpeg, "-hide_banner", "-protocols"], capture_output=True, text=True, errors="replace").stdout
    can_send = "srt" in protocols.split()  # Homebrew ffmpeg(macOS)에는 SRT가 없음: 소스 생성과 수신 대기만 확인
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    setup = subprocess.run([sys.executable, "-m", "debutkit", "camera", "setup", "--obs-port", str(PORT)], capture_output=True, text=True,
                           encoding="utf-8", env=env)
    print(setup.stdout.strip())
    if setup.returncode != 0:
        raise SystemExit(f"debutkit camera setup 실패: {setup.stderr.strip()}")
    config = cameras.load_config()

    def probe(label: str) -> dict:
        """OBS 미디어 상태, 소스 크기, 화면 캡처 크기, debutkit이 표시하는 상태."""
        with client() as obs:
            raw = str(obs.request("GetMediaInputStatus", {"inputName": cameras.SOURCE_NAME}).get("mediaState"))
            scene = obs.request("GetCurrentProgramScene").get("currentProgramSceneName")
            item = obs.request("GetSceneItemId", {"sceneName": scene, "sourceName": cameras.SOURCE_NAME}).get("sceneItemId")
            transform = obs.request("GetSceneItemTransform", {"sceneName": scene, "sceneItemId": item}).get("sceneItemTransform", {})
            try:
                shot = obs.request("GetSourceScreenshot", {"sourceName": cameras.SOURCE_NAME, "imageFormat": "png", "imageWidth": 320})
                size = len(base64.b64decode(str(shot.get("imageData", "")).split(",", 1)[-1]))
            except Exception as error:  # noqa: BLE001
                size = f"오류 {error}"
            shown = cameras.media_state(obs)
        found = {"state": raw, "source": (transform.get("sourceWidth"), transform.get("sourceHeight")), "shot": size, "debutkit": shown}
        print(f"[{label}] {found}")
        return found

    def send(passphrase: str, seconds: int) -> subprocess.Popen:
        target = f"srt://127.0.0.1:{config.port}?mode=caller&latency={config.latency * 1000}&passphrase={passphrase}&pbkeylen=16"
        return subprocess.Popen([ffmpeg, "-hide_banner", "-loglevel", "error", "-re", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30",
                                 "-t", str(seconds), "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-g", "30", "-pix_fmt", "yuv420p",
                                 "-f", "mpegts", target], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")

    def receiving(found: dict) -> bool:
        return isinstance(found["shot"], int) and found["shot"] >= 2000

    time.sleep(3)
    before = probe("송신 전")
    if before["state"] == "OBS_MEDIA_STATE_ERROR":
        raise SystemExit("휴대폰 카메라 소스 오류(포트 사용 중 등)")
    if receiving(before):
        raise SystemExit("휴대폰이 보내기 전인데 화면이 있음")
    if before["debutkit"]["receiving"]:
        raise SystemExit(f"휴대폰이 보내기 전인데 debutkit이 수신 중으로 표시: {before['debutkit']['text']}")
    if not can_send:
        with client() as obs:
            obs.request("RemoveInput", {"inputName": cameras.SOURCE_NAME})
        print(f"::warning::이 ffmpeg에는 SRT 송신 기능이 없어 소스 생성과 수신 대기만 확인: {ffmpeg}")
        return
    sender = send(config.passphrase, int(timeout))
    try:
        end = time.monotonic() + timeout - 5
        while True:
            during = probe("송신 중")
            if receiving(during):
                break
            if sender.poll() is not None:
                raise SystemExit(f"송신 ffmpeg 종료: {sender.stdout.read() if sender.stdout else ''}")
            if time.monotonic() > end:
                raise SystemExit("휴대폰 카메라 소스 화면이 그려지지 않음")
            time.sleep(2)
        time.sleep(2)
        during = probe("송신 중(2초 뒤)")
        if not during["debutkit"]["receiving"]:
            raise SystemExit(f"영상이 오는데 debutkit이 수신 중으로 표시하지 않음: {during['debutkit']['text']}")
        sender.kill()
        sender.wait(timeout=10)
        # 휴대폰이 끊긴 뒤 다시 기다리는지(1초 뒤 재연결 대기), 그 상태에서 틀린 암호는 거부되는지
        time.sleep(4)
        after = probe("끊김 4초 뒤")
        time.sleep(8)
        after = probe("끊김 12초 뒤")
        if after["debutkit"]["receiving"]:
            print(f"::warning::휴대폰이 끊긴 뒤에도 debutkit이 수신 중으로 표시: {after['debutkit']['text']}")
        wrong = send("wrongpassword1", 5)
        try:
            output, _ = wrong.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            wrong.kill()
            raise SystemExit("틀린 암호로 보낸 영상이 거부되지 않음(송신이 끝나지 않음)") from None
        if wrong.returncode == 0 or "BADSECRET" not in output:
            raise SystemExit(f"틀린 암호 거부를 확인하지 못함(종료 코드 {wrong.returncode}): {output.strip()[-400:]}")
        print("틀린 암호 거부 확인(BADSECRET)")
        # 다시 연결하면 다시 그려지는지(휴대폰 앱을 다시 켠 경우)
        sender = send(config.passphrase, 20)
        end = time.monotonic() + 20
        while not receiving(probe("다시 송신")) and time.monotonic() < end:
            time.sleep(2)
        if not receiving(probe("다시 송신 확인")):
            raise SystemExit("휴대폰이 다시 연결했는데 화면이 그려지지 않음")
    finally:
        sender.kill()
        sender.wait(timeout=10)
        with client() as obs:
            obs.request("RemoveInput", {"inputName": cameras.SOURCE_NAME})


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows 기본 코드 페이지로는 한국어 출력 불가
    steps = {"configure": configure, "start": start, "wait": wait, "scenes": scenes, "stop": stop, "clip": clip, "voice": voice, "camera": camera, "logs": logs}
    if not argv or argv[0] not in steps or len(argv) != (2 if argv[0] == "start" else 1):
        print(__doc__)
        return 2
    steps[argv[0]](*argv[1:])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
