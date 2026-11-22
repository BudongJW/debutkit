"""명령줄: debutkit gui | doctor | scenes | overlay | setup | chzzk"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Callable

from . import __version__
from .doctor import JOIN_URL, OVERLAY_PORT


def _doctor(args: argparse.Namespace) -> int:
    from .doctor import FAIL, format_report, run_checks, to_json

    checks = run_checks(avatar=args.avatar, agency=args.agency, overlay_port=args.port)
    if args.speed:
        checks.append(_measure_speed(quiet=args.json))
    print(to_json(checks) if args.json else format_report(checks))
    if not args.json:
        print(f"\n소속 버튜버 프로그램(선택, 키트 사용과 무관): {JOIN_URL}")
    return 1 if any(check.status == FAIL for check in checks) else 0


def _measure_speed(*, quiet: bool = False) -> Any:
    from . import speed
    from .doctor import INFO, Check

    if not quiet:
        print("업로드 속도 측정 중 (약 10초, speed.cloudflare.com에 임의 데이터 전송)", file=sys.stderr, flush=True)
    try:
        return speed.check(speed.measure_upload())
    except Exception as error:
        return Check("upload", "업로드 속도", INFO, f"측정 실패: {error}")


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


#: overlay 옵션과 저장 설정 항목의 대응(API 키, 비밀번호는 저장하지 않음)
OVERLAY_SETTINGS = {"chzzk": "chzzk", "chzzk_api": "chzzk_api", "soop": "soop", "twitch": "twitch", "youtube": "youtube",
                    "youtube_mode": "youtube_mode", "youtube_interval": "youtube_interval", "demo": "demo", "port": "overlay_port",
                    "clip": "clip", "clip_dir": "clip_dir", "obs_port": "obs_port"}


def apply_saved(args: argparse.Namespace, saved: dict[str, Any], defaults: dict[str, Any]) -> list[str]:
    """명령줄에서 지정하지 않은(기본값 그대로인) 항목만 저장한 설정으로 채운다. 반환: 사용한 항목."""
    used = []
    for dest, key in OVERLAY_SETTINGS.items():
        if key in saved and getattr(args, dest) == defaults.get(dest):
            setattr(args, dest, saved[key])
            used.append(key)
    return used


def _overlay_settings(args: argparse.Namespace) -> None:
    from . import settings

    if args.saved:
        saved = settings.load()
        if saved:
            used = apply_saved(args, saved, args.overlay_defaults)
            print(f"저장한 설정 사용({len(used)}개 항목): {settings.settings_path()}")
        else:
            print("저장한 설정 없음. 설정 마법사에서 오버레이를 시작하거나 --save 로 저장", file=sys.stderr)
    if args.save:
        values = {key: getattr(args, dest) for dest, key in OVERLAY_SETTINGS.items() if getattr(args, dest) is not None}
        path = settings.save({**settings.load(), **values})
        print(f"설정 저장: {path} (API 키, 비밀번호는 저장하지 않음)")


def _overlay(args: argparse.Namespace) -> int:
    from .overlay import events
    from .overlay.server import OverlayServer
    from .overlay.youtube import youtube_source

    _overlay_settings(args)
    sources: list[tuple[str, Callable[[], Any]]] = []
    if args.chzzk_api:
        sources.append(("CHZZK 공식 API", events.chzzk_api_source))
    for channel in args.chzzk or []:
        sources.append((f"CHZZK {channel}", lambda c=channel: events.chzzk_source(c)))
    for channel in args.soop or []:
        sources.append((f"SOOP {channel}", lambda c=channel: events.soop_source(c)))
    for channel in args.twitch or []:
        sources.append((f"Twitch {channel}", lambda c=channel: events.twitch_source(c)))
    for video in args.youtube or []:
        sources.append((f"YouTube {video}", lambda v=video: youtube_source(v, args.youtube_key, args.youtube_interval, args.youtube_mode)))
    if args.demo or not sources:
        sources.append(("데모", lambda: events.DemoChat()))
    try:
        server = OverlayServer(sources, port=args.port)
    except OSError as error:
        print(f"{args.port}번 포트 열기 실패 ({error}). --port 로 다른 번호 지정", file=sys.stderr)
        return 1
    from . import logs

    record = logs.setup("overlay")
    server.hub.taps.append(logs.status)  # 상태 안내(연결, 클립 저장, 오류)만 이 PC의 기록 파일에. 채팅 내용은 기록하지 않음
    print(f"오버레이 실행 중: {server.url}  (설정 화면)")
    print(f"  채팅창  {server.url}/chat")
    print(f"  알림    {server.url}/alerts")
    print("  연결: " + ", ".join(label for label, _ in sources))
    if not (args.chzzk_api or args.chzzk or args.soop or args.twitch or args.youtube):
        print("  채널 미지정, 데모 채팅 표시. 예: debutkit overlay --chzzk 채널주소 --soop 방송국주소")
    if args.clip:
        if not _start_autoclip(server, args):
            server.stop()
            logs.close(record)
            return 1
    print("종료: Ctrl+C")
    try:
        server.serve_until_interrupted()
    finally:
        logs.close(record)
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
    print(f"  자동 클립: 사용(OBS {version}, 저장 위치 {out}). 채팅 급증 또는 스트리머의 !clip 입력 시 저장")
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
            print(f"ffmpeg 다운로드 중({size} MB)", flush=True)
        try:
            written = tools.download_ffmpeg(archive=args.archive, on_progress=tools.progress_printer(size, write=lambda line: print(line, flush=True)))
        except Exception as error:
            print(f"ffmpeg 다운로드 실패: {error}", file=sys.stderr)
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

    print(f"치지직 로그인 대기 중(제한 시간 5분, 리디렉션 주소 {args.redirect})", flush=True)
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


def _settings(args: argparse.Namespace) -> int:
    from . import settings

    path = settings.settings_path()
    if args.clear:
        removed = settings.clear()
        print(f"저장한 설정 삭제: {removed}" if removed else "저장한 설정 없음")
        return 0
    saved = settings.load()
    print(f"설정 파일: {path}" + ("" if path.is_file() else " (없음)"))
    if saved:
        print(json.dumps(saved, ensure_ascii=False, indent=2))
    print("API 키, 비밀번호, Client Secret은 저장하지 않음")
    return 0


def _youtube_check(args: argparse.Namespace) -> int:
    from .overlay.youtube_check import as_json, check, format_steps

    steps = check(args.address, args.youtube_key, timeout=args.timeout)
    if args.json:
        print(json.dumps(as_json(steps), ensure_ascii=False, indent=2))
    else:
        print("YouTube 연결 확인(할당량 약 11 단위 사용)")
        print(format_steps(steps))
    return 1 if any(step.ok is False for step in steps) else 0


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

    gui = sub.add_parser("gui", help="설정 마법사 실행(PySide6 필요)")
    gui.set_defaults(func=_gui)

    doctor = sub.add_parser("doctor", help="이 PC의 방송 준비 상태 점검")
    doctor.add_argument("--avatar", help="아바타 모델 파일(.vrm)의 사용 조건 점검")
    doctor.add_argument("--agency", action="store_true", help="기획사 소속 활동 기준(법인 사용)으로 아바타 점검")
    doctor.add_argument("--port", type=int, default=OVERLAY_PORT, help="오버레이 포트 (기본 %(default)s)")
    doctor.add_argument("--json", action="store_true", help="JSON으로 출력")
    doctor.add_argument("--speed", action="store_true", help="업로드 속도 측정, 송출 비트레이트 추천 (약 10초, 지정할 때만 외부 연결)")
    doctor.set_defaults(func=_doctor)

    scenes = sub.add_parser("scenes", help="OBS에 버튜버 장면 세트(대기, 본방송, 토크, 자리 비움, 엔딩) 생성")
    scenes.add_argument("--host", default="127.0.0.1")
    scenes.add_argument("--port", type=int, default=4455, help="OBS WebSocket 포트 (기본 %(default)s)")
    scenes.add_argument("--password", help="OBS WebSocket 비밀번호 (또는 OBS_WEBSOCKET_PASSWORD)")
    scenes.add_argument("--avatar", default="vts", choices=["vts", "vseeface", "warudo", "vmagicmirror", "none"], help="아바타 프로그램 (기본 %(default)s)")
    scenes.add_argument("--overlay-port", type=int, default=OVERLAY_PORT, help="debutkit overlay 포트 (기본 %(default)s)")
    scenes.add_argument("--replace", action="store_true", help="같은 이름의 장면을 삭제 후 다시 생성")
    scenes.add_argument("--switch", action="store_true", help="생성 후 대기 화면으로 전환")
    scenes.add_argument("--replay-buffer", type=int, nargs="?", const=60, metavar="초",
                        help="자동 클립용 리플레이 버퍼 켜기 (길이 기본 60초)")
    scenes.add_argument("--dry-run", action="store_true", help="OBS에 연결하지 않고 설계도만 출력")
    scenes.set_defaults(func=_scenes)

    youtube = sub.add_parser("youtube", help="YouTube 연결 확인")
    youtube_sub = youtube.add_subparsers(dest="youtube_command", required=True)
    youtube_check = youtube_sub.add_parser("check", help="API 키, 라이브 채팅, 요청 방식, 스트리밍 방식을 한 번씩 실행해 확인 (할당량 약 11 단위)")
    youtube_check.add_argument("address", metavar="방송", help="방송 중인 YouTube 방송 주소 또는 영상 ID")
    youtube_check.add_argument("--youtube-key", help="YouTube Data API 키 (또는 YOUTUBE_API_KEY)")
    youtube_check.add_argument("--timeout", type=float, default=20.0, metavar="초", help="스트리밍 첫 응답 대기 시간 (기본 %(default)s초)")
    youtube_check.add_argument("--json", action="store_true", help="JSON으로 출력")
    youtube_check.set_defaults(func=_youtube_check)

    overlay = sub.add_parser("overlay", help="OBS 브라우저 소스용 통합 채팅창, 후원 알림 서버 실행")
    overlay.add_argument("--chzzk", action="append", metavar="채널", help="CHZZK 채널 주소 또는 ID (여러 번 지정 가능, 로그인 없는 비공식 수신)")
    overlay.add_argument("--chzzk-api", action="store_true", help="본인 CHZZK 채널을 공식 Open API로 수신 (debutkit chzzk login 필요, 권장)")
    overlay.add_argument("--soop", action="append", metavar="채널", help="SOOP 방송국 주소 또는 아이디")
    overlay.add_argument("--twitch", action="append", metavar="채널", help="Twitch 채널 이름")
    overlay.add_argument("--youtube", action="append", metavar="방송", help="YouTube 방송 주소 또는 영상 ID (공식 API, API 키 필요)")
    overlay.add_argument("--youtube-key", help="YouTube Data API 키 (또는 YOUTUBE_API_KEY)")
    overlay.add_argument("--youtube-mode", choices=["auto", "stream", "poll"], default="auto",
                         help="YouTube 수신 방식: stream(스트리밍, 할당량 적음), poll(요청 방식), auto(스트리밍 우선, 실패 시 요청 방식. 기본)")
    overlay.add_argument("--youtube-interval", type=float, default=10.0, metavar="초",
                         help="YouTube 채팅 요청 간격 (기본 %(default)s초, 최소 5초. 짧을수록 할당량 빨리 소진)")
    overlay.add_argument("--demo", action="store_true", help="데모 채팅 함께 표시 (표시 형태 확인용)")
    overlay.add_argument("--port", type=int, default=OVERLAY_PORT, help="포트 (기본 %(default)s)")
    clip = overlay.add_argument_group("자동 클립")
    clip.add_argument("--clip", action="store_true", help="채팅 급증 또는 스트리머의 !clip 입력 시 OBS 리플레이 버퍼를 클립으로 저장 (ffmpeg 필요)")
    clip.add_argument("--clip-dir", help="클립 저장 폴더 (기본 동영상/debutkit-clips)")
    clip.add_argument("--obs-host", default="127.0.0.1")
    clip.add_argument("--obs-port", type=int, default=4455)
    clip.add_argument("--obs-password", help="OBS WebSocket 비밀번호 (또는 OBS_WEBSOCKET_PASSWORD)")
    saved = overlay.add_argument_group("저장한 설정")
    saved.add_argument("--saved", action="store_true", help="저장한 설정(채널, 포트, 자동 클립 등) 사용. 명령줄에 지정한 항목이 우선")
    saved.add_argument("--save", action="store_true", help="이번 실행의 채널과 옵션을 저장 (API 키, 비밀번호 제외)")
    overlay.set_defaults(func=_overlay, overlay_defaults={dest: overlay.get_default(dest) for dest in OVERLAY_SETTINGS})

    stored = sub.add_parser("settings", help="저장한 설정 보기 또는 삭제")
    stored.add_argument("--clear", action="store_true", help="저장한 설정 삭제")
    stored.set_defaults(func=_settings)

    setup = sub.add_parser("setup", help="외부 프로그램 확인, ffmpeg 다운로드, 새 버전 확인")
    setup.add_argument("--ffmpeg", action="store_true", help="ffmpeg 다운로드 (Windows, 약 115 MB, SHA-256 검증)")
    setup.add_argument("--from", dest="archive", metavar="ZIP", help="이미 다운로드한 ffmpeg 압축 파일 사용")
    setup.add_argument("--force", action="store_true", help="설치되어 있어도 다시 다운로드")
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
