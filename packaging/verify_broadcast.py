"""OBS 없이 바로 방송 확인(Windows): 오버레이 서버, 송출 화면 창(Edge), ffmpeg 창 캡처와 인코딩, 이 PC 안의 RTMP 수신까지.

사용: python packaging/verify_broadcast.py [--seconds 10] [--encoder auto] [--quality 720p30] [--keep 받은파일.flv]

- 설정은 임시 폴더(DEBUTKIT_SETTINGS)에 만들고 끝나면 지운다. 스트림 키는 시험용 값(DPAPI 저장까지 실제로 거친다)
- 송출 대상은 ffmpeg의 RTMP 수신(``-listen 1``)이 대신한다. 받은 영상의 해상도, 프레임 수, 소리 트랙을 ffprobe로 확인
- 마이크는 쓰지 않는다(무음 트랙). 설정 마법사, 실제 방송 플랫폼과 무관
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

KEY = "verify-key-1234"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def ffprobe_for(ffmpeg: str) -> str:
    try:
        from stream2clip.ffmpeg import find_ffprobe

        return find_ffprobe()
    except Exception:
        sibling = Path(ffmpeg).with_name("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
        return str(sibling) if sibling.exists() else (shutil.which("ffprobe") or "ffprobe")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seconds", type=float, default=10.0, help="방송 시간(초)")
    parser.add_argument("--encoder", default="auto", help="인코더(기본 auto)")
    parser.add_argument("--quality", default="720p30", help="화질(기본 720p30)")
    parser.add_argument("--keep", metavar="FILE", help="받은 영상을 이 파일로 남기기")
    parser.add_argument("--no-gpu-ok", action="store_true",
                        help="그래픽 장치(D3D11)가 없어 창 캡처만 못 한 경우 경고로 통과(GitHub Actions 등). 창 열기, 화면 크기 보고, 인코더 확인까지는 검사")
    args = parser.parse_args()
    if sys.platform != "win32":
        print("Windows에서만 확인 가능")
        return 2
    temp = Path(tempfile.mkdtemp(prefix="debutkit-broadcast-"))
    os.environ["DEBUTKIT_SETTINGS"] = str(temp / "settings.json")

    from debutkit import broadcast, tools
    from debutkit.overlay.server import OverlayServer

    ffmpeg = tools.ffmpeg_path()
    if not ffmpeg:
        print(f"ffmpeg 없음: {tools.install_hint()}")
        return 1
    received = Path(args.keep) if args.keep else temp / "received.flv"
    port = free_port()
    listener = subprocess.Popen([ffmpeg, "-hide_banner", "-v", "fatal", "-y", "-listen", "1", "-timeout", "120", "-i", f"rtmp://127.0.0.1:{port}/live/{KEY}",
                                 "-c", "copy", str(received)], stdin=subprocess.DEVNULL)
    server = OverlayServer(port=0).start()
    caster = server.broadcast
    failed = False
    try:
        caster.update_config({"platform": "custom", "server": f"rtmp://127.0.0.1:{port}/live", "quality": args.quality, "encoder": args.encoder,
                              "title": "debutkit verify", "mic": "", "extra_audio": ""})
        caster.set_key(KEY)
        print("장치:", json.dumps(caster.devices(), ensure_ascii=False))
        caster.start()
        deadline = time.monotonic() + 120
        status = caster.status()
        while status["state"] == "starting" and time.monotonic() < deadline:
            time.sleep(0.5)
            status = caster.status()
        print("시작:", json.dumps({key: status[key] for key in ("state", "phase", "error", "encoder", "stats", "warnings")}, ensure_ascii=False))
        if status["state"] != "live":
            log = list(caster._log)
            print("ffmpeg 기록:", *log, sep="\n  ")
            no_gpu = any(broadcast.NO_GPU in line.lower() for line in log)
            if args.no_gpu_ok and no_gpu:
                earlier = {"송출 화면 창": status["window"], "화면 크기 보고": caster.program.get(caster._token) is not None,
                           "인코더 확인": bool(status["encoder"]), "안내 문장": status["error"].startswith("그래픽 장치(D3D11)")}
                for name, ok in earlier.items():
                    print(("확인 " if ok else "실패 ") + name)
                print("::warning::그래픽 장치(D3D11)가 없는 환경이라 창 캡처와 송출은 실제 PC에서만 확인")
                received.unlink(missing_ok=True)
                return 0 if all(earlier.values()) else 1
            failed = True
            return 1
        time.sleep(args.seconds)
        status = caster.status()
        print("방송 중:", json.dumps({key: status[key] for key in ("state", "seconds", "stats", "warnings")}, ensure_ascii=False))
        if KEY in json.dumps(status, ensure_ascii=False):
            print("상태에 스트림 키가 보임")
            failed = True
            return 1
    finally:
        caster.stop(close_window=True)
        server.stop()
        if failed or caster.status()["stats"].get("frames", 0) == 0:
            listener.kill()  # 연결이 없었으면 기다리지 않는다
        try:
            listener.wait(30)
        except subprocess.TimeoutExpired:
            listener.kill()
            failed = True
    probe = subprocess.run([ffprobe_for(ffmpeg), "-v", "error", "-count_frames", "-show_entries", "stream=codec_type,codec_name,width,height,nb_read_frames",
                            "-show_entries", "format=duration", "-of", "json", str(received)], capture_output=True, text=True, encoding="utf-8")
    try:
        info = json.loads(probe.stdout or "{}")
    except ValueError:
        info = {}
    print("받은 영상:", json.dumps(info, ensure_ascii=False))
    streams = {item.get("codec_type"): item for item in info.get("streams", [])}
    quality = broadcast.QUALITIES[args.quality]
    video, audio = streams.get("video", {}), streams.get("audio", {})
    frames = int(video.get("nb_read_frames") or 0)
    checks = {
        "H.264 영상": video.get("codec_name") == "h264",
        f"{quality.width}x{quality.height}": (video.get("width"), video.get("height")) == (quality.width, quality.height),
        f"프레임 {frames}개(최소 {int(args.seconds * quality.fps * 0.8)}개)": frames >= args.seconds * quality.fps * 0.8,
        "AAC 소리": audio.get("codec_name") == "aac",
    }
    for name, ok in checks.items():
        print(("확인 " if ok else "실패 ") + name)
    if not args.keep:
        shutil.rmtree(temp, ignore_errors=True)
    return 0 if all(checks.values()) and not failed else 1


if __name__ == "__main__":
    sys.exit(main())
