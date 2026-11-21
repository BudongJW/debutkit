"""명령줄: debutkit doctor | scenes | overlay"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Callable

from . import __version__
from .doctor import OVERLAY_PORT


def _doctor(args: argparse.Namespace) -> int:
    from .doctor import FAIL, format_report, run_checks, to_json

    checks = run_checks(avatar=args.avatar, agency=args.agency, overlay_port=args.port)
    print(to_json(checks) if args.json else format_report(checks))
    if not args.json:
        print("\n소속 버튜버 프로그램(선택): https://github.com/BudongJW/debutkit/blob/main/docs/MEMBERSHIP.md  - 키트 사용과는 무관합니다.")
    return 1 if any(check.status == FAIL for check in checks) else 0


def _scenes(args: argparse.Namespace) -> int:
    from .scenes import SceneOptions, build_scenes, connect_and_apply, default_kinds, format_plan, format_report

    base = f"http://127.0.0.1:{args.overlay_port}"
    options = SceneOptions(overlay_url=f"{base}/chat", alerts_url=f"{base}/alerts", avatar=args.avatar)
    if args.dry_run:
        kinds = default_kinds(options.os_name)
        print(format_plan(build_scenes(1920, 1080, kinds, options), kinds))
        print("\n(--dry-run: OBS에 아무것도 만들지 않았습니다. 화면 크기 1920x1080 가정)")
        return 0
    try:
        report, scenes = connect_and_apply(args.host, args.port, args.password or os.environ.get("OBS_WEBSOCKET_PASSWORD"), options,
                                           replace=args.replace, switch=args.switch, replay_buffer=args.replay_buffer)
    except Exception as error:  # 연결 실패, 비밀번호 오류, stream2clip 없음
        print(f"OBS 장면을 만들지 못했습니다: {error}", file=sys.stderr)
        return 1
    print(format_report(report))
    return 0


def _overlay(args: argparse.Namespace) -> int:
    from .overlay import events
    from .overlay.server import OverlayServer

    sources: list[tuple[str, Callable[[], Any]]] = []
    if args.chzzk_api:
        sources.append(("CHZZK 공식 API", events.chzzk_api_source))
    for channel in args.chzzk or []:
        sources.append((f"CHZZK {channel}", lambda c=channel: events.chzzk_source(c)))
    for channel in args.soop or []:
        sources.append((f"SOOP {channel}", lambda c=channel: events.soop_source(c)))
    for channel in args.twitch or []:
        sources.append((f"Twitch {channel}", lambda c=channel: events.twitch_source(c)))
    if args.demo or not sources:
        sources.append(("데모", lambda: events.DemoChat()))
    try:
        server = OverlayServer(sources, port=args.port)
    except OSError as error:
        print(f"{args.port}번 포트를 열지 못했습니다 ({error}). --port 로 다른 번호를 지정하세요.", file=sys.stderr)
        return 1
    print(f"오버레이 실행 중: {server.url}  (설정 화면)")
    print(f"  채팅창  {server.url}/chat")
    print(f"  알림    {server.url}/alerts")
    print("  연결: " + ", ".join(label for label, _ in sources))
    if not (args.chzzk_api or args.chzzk or args.soop or args.twitch):
        print("  방송 채널을 지정하지 않아 데모 채팅을 보여 줍니다. 예: debutkit overlay --chzzk <채널 주소> --soop <방송국 주소>")
    if args.clip:
        if not _start_autoclip(server, args):
            server.stop()
            return 1
    print("끝내려면 Ctrl+C")
    server.serve_until_interrupted()
    return 0


def _start_autoclip(server: Any, args: argparse.Namespace) -> bool:
    from .clip import AutoClipper, default_clip_dir, replay_clipper

    out = args.clip_dir or default_clip_dir()
    password = args.obs_password or os.environ.get("OBS_WEBSOCKET_PASSWORD")
    try:
        clipper = replay_clipper(out, args.obs_host, args.obs_port, password)
        version = clipper.check(start_buffer=True)
    except ImportError:
        print('자동 클립에는 stream2clip이 필요합니다: pip install "debutkit[live]"', file=sys.stderr)
        return False
    except Exception as error:
        print(f"자동 클립을 켜지 못했습니다: {error}", file=sys.stderr)
        print("  OBS 실행, WebSocket 서버 사용, 리플레이 버퍼 사용(debutkit scenes --replay-buffer)을 확인하세요.", file=sys.stderr)
        return False
    server.attach(AutoClipper(server.hub, clipper).start())
    print(f"  자동 클립: 켬 (OBS {version}, 저장 위치 {out}). 채팅이 몰리거나 방장이 !clip 을 쓰면 저장")
    return True


def _gui(args: argparse.Namespace) -> int:
    try:
        from .gui.app import main as gui_main
    except ImportError as error:
        print(f'설정 마법사에는 PySide6가 필요합니다: pip install "debutkit[gui]" ({error})', file=sys.stderr)
        return 1
    return gui_main([sys.argv[0]])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="debutkit", description="버튜버 데뷔 키트: 방송 준비 점검, OBS 장면 세트, 통합 채팅 오버레이")
    parser.add_argument("--version", action="version", version=f"debutkit {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    gui = sub.add_parser("gui", help="설정 마법사 창 열기 (PySide6 필요)")
    gui.set_defaults(func=_gui)

    doctor = sub.add_parser("doctor", help="이 PC의 방송 준비 상태 점검")
    doctor.add_argument("--avatar", help="아바타 모델 파일(.vrm)의 사용 조건 점검")
    doctor.add_argument("--agency", action="store_true", help="기획사 소속 활동 기준(법인 사용)으로 아바타 점검")
    doctor.add_argument("--port", type=int, default=OVERLAY_PORT, help="오버레이 포트 (기본 %(default)s)")
    doctor.add_argument("--json", action="store_true", help="JSON으로 출력")
    doctor.set_defaults(func=_doctor)

    scenes = sub.add_parser("scenes", help="OBS에 버튜버 장면 세트(대기, 본방송, 토크, 자리 비움, 엔딩) 만들기")
    scenes.add_argument("--host", default="127.0.0.1")
    scenes.add_argument("--port", type=int, default=4455, help="OBS WebSocket 포트 (기본 %(default)s)")
    scenes.add_argument("--password", help="OBS WebSocket 비밀번호 (또는 OBS_WEBSOCKET_PASSWORD)")
    scenes.add_argument("--avatar", default="vts", choices=["vts", "vseeface", "warudo", "vmagicmirror", "none"], help="아바타 프로그램 (기본 %(default)s)")
    scenes.add_argument("--overlay-port", type=int, default=OVERLAY_PORT, help="debutkit overlay 포트 (기본 %(default)s)")
    scenes.add_argument("--replace", action="store_true", help="같은 이름의 장면이 있으면 지우고 다시 만들기")
    scenes.add_argument("--switch", action="store_true", help="다 만든 뒤 '대기 화면'으로 전환")
    scenes.add_argument("--replay-buffer", type=int, nargs="?", const=60, metavar="초",
                        help="자동 클립용 리플레이 버퍼 켜기 (길이 기본 60초)")
    scenes.add_argument("--dry-run", action="store_true", help="OBS에 연결하지 않고 설계도만 출력")
    scenes.set_defaults(func=_scenes)

    overlay = sub.add_parser("overlay", help="OBS 브라우저 소스용 통합 채팅창, 후원 알림 서버 실행")
    overlay.add_argument("--chzzk", action="append", metavar="채널", help="CHZZK 채널 주소 또는 ID (여러 번 지정 가능, 로그인 없이 읽기)")
    overlay.add_argument("--chzzk-api", action="store_true", help="내 CHZZK 채널을 공식 Open API로 읽기 (stream2clip chzzk login 필요, 권장)")
    overlay.add_argument("--soop", action="append", metavar="채널", help="SOOP 방송국 주소 또는 아이디")
    overlay.add_argument("--twitch", action="append", metavar="채널", help="Twitch 채널 이름")
    overlay.add_argument("--demo", action="store_true", help="가짜 채팅을 함께 보여 주기 (모양 맞추기)")
    overlay.add_argument("--port", type=int, default=OVERLAY_PORT, help="포트 (기본 %(default)s)")
    clip = overlay.add_argument_group("자동 클립 (stream2clip 라이브 모드)")
    clip.add_argument("--clip", action="store_true", help="채팅이 몰리면 OBS 리플레이 버퍼를 저장해 클립으로")
    clip.add_argument("--clip-dir", help="클립 저장 폴더 (기본 동영상/debutkit-clips)")
    clip.add_argument("--obs-host", default="127.0.0.1")
    clip.add_argument("--obs-port", type=int, default=4455)
    clip.add_argument("--obs-password", help="OBS WebSocket 비밀번호 (또는 OBS_WEBSOCKET_PASSWORD)")
    overlay.set_defaults(func=_overlay)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # 한국어 출력이 리디렉션돼도 깨지지 않게
        try:
            stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
