"""실제 OBS로 장면 생성, 고급 출력 모드 리플레이 버퍼, 자동 클립을 검증한다(CI용, .github/workflows/verify.yml).

    python packaging/verify_obs.py configure   # OBS 설정 파일 준비(첫 실행 안내 생략, WebSocket 사용, 고급 출력 모드)
    python packaging/verify_obs.py wait        # OBS WebSocket 응답 대기
    python packaging/verify_obs.py scenes      # debutkit scenes --replay-buffer 30 실행과 결과 확인
    python packaging/verify_obs.py clip        # debutkit overlay --clip 실행, 스트리머 !clip 입력, 클립 파일 확인

configure는 이 PC의 OBS 설정을 덮어쓰므로 CI 전용 컴퓨터에서만 실행한다(DEBUTKIT_VERIFY_OBS=1 필요).
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HOST, PORT = "127.0.0.1", 4455
OVERLAY_PORT = 8791
RECORDINGS = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "obs-recordings"
CLIPS = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "debutkit-clips"
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
    general = "[General]\nFirstRun=true\nEnableAutoUpdates=false\n\n[Basic]\nProfile=Untitled\nProfileDir=Untitled\nSceneCollection=Untitled\nSceneCollectionFile=Untitled\n"
    for name in ("global.ini", "user.ini"):  # OBS 31부터 사용자 설정은 user.ini
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(general, encoding="utf-8")
    profile = root / "basic" / "profiles" / "Untitled"
    profile.mkdir(parents=True, exist_ok=True)
    (profile / "basic.ini").write_text(
        "[General]\nName=Untitled\n\n[Video]\nBaseCX=1280\nBaseCY=720\nOutputCX=1280\nOutputCY=720\nFPSType=0\nFPSCommon=30\n\n"
        f"[Output]\nMode=Advanced\n\n[AdvOut]\nRecType=Standard\nRecFilePath={RECORDINGS}\nRecFormat2=mkv\nRecEncoder=obs_x264\n", encoding="utf-8")
    websocket = root / "plugin_config" / "obs-websocket"
    websocket.mkdir(parents=True, exist_ok=True)
    (websocket / "config.json").write_text(json.dumps({"alerts_enabled": False, "auth_required": False, "first_load": False,
                                                       "server_enabled": True, "server_password": "", "server_port": PORT}), encoding="utf-8")
    print(f"OBS 설정 준비: {root} (고급 출력 모드, 녹화 위치 {RECORDINGS})")


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
                probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(found[-1])],
                                       capture_output=True, text=True)
                duration = float(probe.stdout.strip() or 0)
                print(f"클립 저장 확인: {found[-1].name}, {found[-1].stat().st_size / 1024:.0f} KB, {duration:.1f}초")
                if duration <= 0:
                    raise SystemExit("클립 길이 0")
                return
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


def main(argv: list[str]) -> int:
    steps = {"configure": configure, "wait": wait, "scenes": scenes, "clip": clip}
    if len(argv) != 1 or argv[0] not in steps:
        print(__doc__)
        return 2
    steps[argv[0]]()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
