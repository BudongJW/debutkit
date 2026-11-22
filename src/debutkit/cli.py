"""명령줄: debutkit gui | doctor | scenes | overlay | setup | chzzk"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Callable

from . import __version__
from .doctor import JOIN_URL, OVERLAY_PORT


def _doctor(args: argparse.Namespace) -> int:
    from .doctor import FAIL, format_report, run_checks, to_json

    checks = run_checks(avatar=args.avatar, agency=args.agency, overlay_port=args.port)
    print(to_json(checks) if args.json else format_report(checks))
    if not args.json:
        print(f"\n소속 버튜버 프로그램(선택, 키트 사용과 무관): {JOIN_URL}")
    return 1 if any(check.status == FAIL for check in checks) else 0


def _scenes(args: argparse.Namespace) -> int:
    from .scenes import SceneOptions, build_scenes, connect_and_apply, default_kinds, format_plan, format_report

    base = f"http://127.0.0.1:{args.overlay_port}"
    options = SceneOptions(overlay_url=f"{base}/chat", alerts_url=f"{base}/alerts", avatar=args.avatar)
    if args.dry_run:
        kinds = default_kinds(options.os_name)
        print(format_plan(build_scenes(1920, 1080, kinds, options), kinds))
        print("\n(--dry-run: OBS 변경 없음. 화면 크기 1920x1080 가정)")
        return 0
    try:
        report, scenes = connect_and_apply(args.host, args.port, args.password or os.environ.get("OBS_WEBSOCKET_PASSWORD"), options,
                                           replace=args.replace, switch=args.switch, replay_buffer=args.replay_buffer)
    except Exception as error:  # 연결 실패, 비밀번호 오류, 채팅 연결 모듈 없음
        print(f"OBS 장면 생성 실패: {error}", file=sys.stderr)
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
        print(f"{args.port}번 포트 열기 실패 ({error}). --port 로 다른 번호 지정", file=sys.stderr)
        return 1
    print(f"오버레이 실행 중: {server.url}  (설정 화면)")
    print(f"  채팅창  {server.url}/chat")
    print(f"  알림    {server.url}/alerts")
    print("  연결: " + ", ".join(label for label, _ in sources))
    if not (args.chzzk_api or args.chzzk or args.soop or args.twitch):
        print("  채널 미지정, 데모 채팅 표시. 예: debutkit overlay --chzzk 채널주소 --soop 방송국주소")
    if args.clip:
        if not _start_autoclip(server, args):
            server.stop()
            return 1
    print("종료: Ctrl+C")
    server.serve_until_interrupted()
    return 0


def _start_autoclip(server: Any, args: argparse.Namespace) -> bool:
    from .clip import AutoClipper, default_clip_dir, preflight, replay_clipper

    problem = preflight()
    if problem:
        print(problem, file=sys.stderr)
        return False
    out = args.clip_dir or default_clip_dir()
    password = args.obs_password or os.environ.get("OBS_WEBSOCKET_PASSWORD")
    try:
        clipper = replay_clipper(out, args.obs_host, args.obs_port, password)
        version = clipper.check(start_buffer=True)
    except Exception as error:
        print(f"자동 클립 켜기 실패: {error}", file=sys.stderr)
        print("  확인: OBS 실행, WebSocket 서버 사용, 리플레이 버퍼 사용(debutkit scenes --replay-buffer)", file=sys.stderr)
        return False
    server.attach(AutoClipper(server.hub, clipper).start())
    print(f"  자동 클립: 켬 (OBS {version}, 저장 위치 {out}). 채팅 급증 또는 방장 !clip 시 저장")
    return True


def _setup(args: argparse.Namespace) -> int:
    from . import tools

    if args.archive and not args.ffmpeg:
        print("--from 은 --ffmpeg 와 함께 사용", file=sys.stderr)
        return 2
    found = tools.ffmpeg_path()
    if args.ffmpeg and (args.force or not found):
        size = tools.ffmpeg_megabytes()
        if not args.archive:
            print(f"ffmpeg 내려받는 중 ({size} MB)", flush=True)
        try:
            written = tools.download_ffmpeg(archive=args.archive, on_progress=tools.progress_printer(size, write=lambda line: print(line, flush=True)))
        except Exception as error:
            print(f"ffmpeg 내려받기 실패: {error}", file=sys.stderr)
            return 1
        for path in written:
            print(f"저장: {path}")
        found = tools.ffmpeg_path()
    print(f"ffmpeg: {found}" if found else f"ffmpeg: 없음. {tools.install_hint()}")
    try:
        import stream2clip  # noqa: F401
    except ImportError:
        print('채팅 연결 모듈: 없음. pip install "debutkit[live]"')
    else:
        print("채팅 연결 모듈: 설치됨")
    if args.check_update:
        print(tools.update_message(__version__))
    return 0 if found else 1


def _chzzk_login(args: argparse.Namespace) -> int:
    from .chzzk import ChzzkLoginError, login

    def show(url: str) -> None:
        print(f"치지직 로그인 주소: {url}", flush=True)

    print(f"치지직 로그인 대기 중 (5분, 돌아올 주소 {args.redirect})", flush=True)
    try:
        path = login(args.client_id, args.client_secret, args.redirect, open_browser=(lambda url: None) if args.no_browser else None, on_url=show)
    except ChzzkLoginError as error:
        print(f"치지직 로그인 실패: {error}", file=sys.stderr)
        return 1
    print(f"로그인 완료. 토큰 저장 위치: {path}")
    print("사용: debutkit overlay --chzzk-api")
    return 0


def _chzzk_logout(args: argparse.Namespace) -> int:
    from .chzzk import logout

    path = logout()
    print(f"토큰 삭제: {path}" if path else "로그인 상태 아님")
    return 0


def _gui(args: argparse.Namespace) -> int:
    try:
        from .gui.app import main as gui_main
    except ImportError as error:
        print(f'설정 마법사에는 PySide6 필요: pip install "debutkit[gui]" ({error})', file=sys.stderr)
        return 1
    return gui_main([sys.argv[0]])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="debutkit", description="버튜버 데뷔 키트: 방송 준비 점검, OBS 장면 세트, 통합 채팅 오버레이, 자동 클립")
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
    scenes.add_argument("--switch", action="store_true", help="생성 후 대기 화면으로 전환")
    scenes.add_argument("--replay-buffer", type=int, nargs="?", const=60, metavar="초",
                        help="자동 클립용 리플레이 버퍼 켜기 (길이 기본 60초)")
    scenes.add_argument("--dry-run", action="store_true", help="OBS에 연결하지 않고 설계도만 출력")
    scenes.set_defaults(func=_scenes)

    overlay = sub.add_parser("overlay", help="OBS 브라우저 소스용 통합 채팅창, 후원 알림 서버 실행")
    overlay.add_argument("--chzzk", action="append", metavar="채널", help="CHZZK 채널 주소 또는 ID (여러 번 지정 가능, 로그인 없이 읽기)")
    overlay.add_argument("--chzzk-api", action="store_true", help="내 CHZZK 채널을 공식 Open API로 읽기 (debutkit chzzk login 필요, 권장)")
    overlay.add_argument("--soop", action="append", metavar="채널", help="SOOP 방송국 주소 또는 아이디")
    overlay.add_argument("--twitch", action="append", metavar="채널", help="Twitch 채널 이름")
    overlay.add_argument("--demo", action="store_true", help="데모 채팅 함께 표시 (모양 맞추기)")
    overlay.add_argument("--port", type=int, default=OVERLAY_PORT, help="포트 (기본 %(default)s)")
    clip = overlay.add_argument_group("자동 클립")
    clip.add_argument("--clip", action="store_true", help="채팅 급증 또는 방장 !clip 시 OBS 리플레이 버퍼를 클립으로 저장 (ffmpeg 필요)")
    clip.add_argument("--clip-dir", help="클립 저장 폴더 (기본 동영상/debutkit-clips)")
    clip.add_argument("--obs-host", default="127.0.0.1")
    clip.add_argument("--obs-port", type=int, default=4455)
    clip.add_argument("--obs-password", help="OBS WebSocket 비밀번호 (또는 OBS_WEBSOCKET_PASSWORD)")
    overlay.set_defaults(func=_overlay)

    setup = sub.add_parser("setup", help="필요한 외부 프로그램 확인, ffmpeg 내려받기")
    setup.add_argument("--ffmpeg", action="store_true", help="ffmpeg 내려받기 (Windows, 약 115 MB, SHA-256 확인)")
    setup.add_argument("--from", dest="archive", metavar="ZIP", help="이미 받은 ffmpeg 압축 파일 사용")
    setup.add_argument("--force", action="store_true", help="이미 있어도 다시 받기")
    setup.add_argument("--check-update", action="store_true", help="GitHub에서 새 버전 확인 (지정할 때만 연결)")
    setup.set_defaults(func=_setup)

    chzzk = sub.add_parser("chzzk", help="치지직 공식 Open API 로그인 (내 채널의 채팅, 후원, 구독)")
    chzzk_sub = chzzk.add_subparsers(dest="chzzk_command", required=True)
    login = chzzk_sub.add_parser("login", help="브라우저에서 치지직 로그인, 동의")
    login.add_argument("--client-id", help="애플리케이션 Client ID (또는 CHZZK_CLIENT_ID)")
    login.add_argument("--client-secret", help="애플리케이션 Client Secret (또는 CHZZK_CLIENT_SECRET)")
    login.add_argument("--redirect", default="http://localhost:8765/callback", help="개발자 센터에 등록한 로그인 리디렉션 주소 (기본 %(default)s)")
    login.add_argument("--no-browser", action="store_true", help="브라우저를 열지 않고 주소만 출력")
    login.set_defaults(func=_chzzk_login)
    logout = chzzk_sub.add_parser("logout", help="이 PC에 보관한 치지직 토큰 삭제")
    logout.set_defaults(func=_chzzk_logout)
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
