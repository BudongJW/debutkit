"""명령줄: debutkit gui | doctor | scenes | camera | overlay | draw | raffle | phone | remote | broadcast | launch | logo | character | motion | vts |
settings | setup | chzzk"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
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
    options = SceneOptions(overlay_url=f"{base}/chat", alerts_url=f"{base}/alerts", character_url=f"{base}/character", draw_url=f"{base}/draw",
                           avatar=args.avatar)
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


def _camera_info(info: dict[str, Any]) -> str:
    if not info["address"]:
        return "이 PC의 내부 네트워크 주소를 찾지 못함: Wi-Fi나 유선 연결 확인"
    lines = ["휴대폰 앱 연결 정보(SRT, 모드 Caller)", f"  주소      {info['url']}", f"  암호      {info['passphrase']} (암호 길이 16)",
             f"  지연 여유 {info['latency']}밀리초"]
    if len(info["addresses"]) > 1:
        lines.append(f"  다른 주소 {', '.join(info['addresses'][1:])} (같은 Wi-Fi가 아니면 다른 주소 사용)")
    lines += ["  Larix Broadcaster 가져오기 주소(휴대폰에서 열기):", f"  {info['larix']}",
              "  QR 코드: 오버레이 실행 중 http://127.0.0.1:8790/phone#camera"]
    return "\n".join(lines)


def _camera(args: argparse.Namespace) -> int:
    """휴대폰 카메라 영상(SRT)을 받는 OBS 미디어 소스와 휴대폰 앱 연결 정보."""
    from . import camera

    try:
        if args.camera_command == "setup" and (args.port is not None or args.latency is not None or args.new_passphrase):
            config = camera.update_config(args.port, args.latency, args.new_passphrase)
        else:
            config = camera.load_config()
    except camera.CameraError as error:
        print(f"설정 오류: {error}", file=sys.stderr)
        return 1
    if args.camera_command == "info":
        print(_camera_info(camera.connection_info(config)))
        return 0
    password = args.obs_password or os.environ.get("OBS_WEBSOCKET_PASSWORD")
    try:
        with camera.connect(args.obs_host, args.obs_port, password) as client:
            if args.camera_command == "status":
                print(f"OBS 휴대폰 카메라 소스: {camera.media_state(client)['text']}")
                return 0
            if args.app:  # debutkit 휴대폰 앱 영상(WebRTC) 수신 화면
                result = camera.add_app_to_obs(client, args.overlay_port, args.scene or ())
                state = {"text": f"앱에서 카메라 영상 보내기를 누르면 표시(수신 화면 http://127.0.0.1:{args.overlay_port}/camera/view)"}
            else:
                result = camera.add_to_obs(client, config, args.scene or ())
                state = camera.media_state(client)
    except camera.CameraError as error:
        print(f"휴대폰 카메라 소스 실패: {error}", file=sys.stderr)
        return 1
    except Exception as error:  # OBS 꺼짐, 비밀번호 오류
        print(camera.obs_failure(error), file=sys.stderr)
        return 1
    done = "만듦" if result["created"] else "설정 맞춤"
    where = ", ".join(result["added"]) + " 장면에 추가" if result["added"] else ", ".join(result["kept"]) + " 장면에 이미 있음"
    print(f"OBS 소스 {camera.SOURCE_NAME} {done}, {where}. 상태: {state['text']}")
    if args.app:
        print("앱 등록: 오버레이 설정 화면의 휴대폰 연결에서 휴대폰 조작 화면을 켜고 QR 등록, PC에서 승인")
        return 0
    print("OBS가 처음 수신할 때 Windows 보안 경고가 나오면 개인 네트워크 허용")
    print(_camera_info(camera.connection_info(config)))
    return 0


#: overlay 옵션과 저장 설정 항목의 대응(API 키, 비밀번호는 저장하지 않음)
OVERLAY_SETTINGS = {"chzzk": "chzzk", "chzzk_api": "chzzk_api", "soop": "soop", "twitch": "twitch", "youtube": "youtube",
                    "youtube_mode": "youtube_mode", "youtube_interval": "youtube_interval", "demo": "demo", "port": "overlay_port",
                    "clip": "clip", "clip_dir": "clip_dir", "clip_gif": "clip_gif", "clip_shorts": "clip_shorts", "obs_port": "obs_port", "voice_input": "voice_input", "voice_threshold": "voice_threshold",
                    "vts_reaction": "vts_reactions", "motion_reaction": "motion_reactions"}


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
        server = OverlayServer(sources, port=args.port, chat_commands=False if args.no_chat_commands else None)
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
    server.obs_target = (args.obs_host, args.obs_port, args.obs_password or os.environ.get("OBS_WEBSOCKET_PASSWORD"))  # 휴대폰 카메라 소스 만들기
    if not (args.chzzk_api or args.chzzk or args.soop or args.twitch or args.youtube):
        print("  채널 미지정, 데모 채팅 표시. 예: debutkit overlay --chzzk 채널주소 --soop 방송국주소")
    _start_voice(server, args)
    _start_vts_reactions(server, args)
    _start_motion_reactions(server, args)
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


def _start_voice(server: Any, args: argparse.Namespace) -> None:
    """캐릭터 화면의 입 움직임: OBS 마이크 음량을 받는다(채팅 연결 모듈 필요)."""
    if args.no_voice:
        return
    try:
        import stream2clip.obs  # noqa: F401
    except ImportError:
        print('  캐릭터 음성 반응: 채팅 연결 모듈 없음(pip install "debutkit[live]")')
        return
    from .overlay.events import system_event
    from .overlay.voice import VoiceMeter

    password = args.obs_password or os.environ.get("OBS_WEBSOCKET_PASSWORD")
    meter = VoiceMeter(server.voice, args.obs_host, args.obs_port, password, input_name=args.voice_input, threshold=args.voice_threshold,
                       notify=lambda text: server.hub.publish(system_event(text)))
    server.attach(meter.start())
    print(f"  캐릭터 화면: {server.url}/character (OBS 마이크 음량으로 입 움직임, 기준 {args.voice_threshold:.0f} dB)")
    print(f"  얼굴 추적: {server.url}/tracker (일반 브라우저에서 열고 카메라 허용. OBS에는 추가하지 않음)")
    print(f"  휴대폰 얼굴 추적: {server.url}/phone (아이폰 iFacialMocap, VTube Studio 앱. debutkit phone start)")


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
    post = None
    if args.clip_gif or args.clip_shorts:
        from .clipfx import PostProcessor
        from .overlay.events import system_event

        post = PostProcessor(bool(args.clip_gif), bool(args.clip_shorts), lambda text: server.hub.publish(system_event(text)))
    server.attach(AutoClipper(server.hub, clipper, post=post).start())
    extra = ", ".join(name for name, on in (("움짤", args.clip_gif), ("세로 쇼츠", args.clip_shorts)) if on)
    print(f"  자동 클립: 사용(OBS {version}, 저장 위치 {out}). 채팅 급증 또는 스트리머의 !clip 입력 시 저장" + (f". 클립마다 {extra}도 만듦" if extra else ""))
    return True


def _clipfx(args: argparse.Namespace) -> int:
    """클립 다듬기: 움짤(GIF, WebP), 세로 쇼츠."""
    from . import clipfx

    try:
        watermark = clipfx.Watermark(Path(args.watermark), args.watermark_position, args.watermark_size / 100, args.watermark_opacity / 100) \
            if args.watermark else None
        made = []
        for source in args.files:
            if args.clipfx_command == "gif":
                made.append(clipfx.make_gif(Path(source), start=args.start, duration=args.duration, width=args.width, fps=args.fps, watermark=watermark))
            elif args.clipfx_command == "webp":
                made.append(clipfx.make_webp(Path(source), start=args.start, duration=args.duration, width=args.width, fps=args.fps, quality=args.quality,
                                             watermark=watermark))
            else:
                made.append(clipfx.make_shorts(Path(source), mode=args.mode, focus=args.focus, start=args.start, duration=args.duration, watermark=watermark))
            print(f"저장: {made[-1]}", flush=True)
    except clipfx.ClipFxError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


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


def _describe(item: Any, active_id: str) -> str:
    mark = "* " if item.id == active_id else "  "
    note = f"  확인 필요 {len(item.warnings)}건" if item.warnings else ""
    return f"{mark}{item.id:20} {item.kind_name:12} {item.name}{note}"


def _character(args: argparse.Namespace) -> int:
    from . import character

    command = args.character_command
    try:
        if command == "list":
            active_id = character.active().id
            print("등록한 캐릭터(* 방송에 사용)")
            for item in character.all_characters():
                print(_describe(item, active_id))
            print(f"보관 위치: {character.library_dir()}")
            return 0
        if command in ("add", "png"):
            if command == "add":
                item = character.add(args.path, name=args.name or "")
            else:
                item = character.add_png(args.idle, args.talk, args.blink, args.talk_blink, name=args.name)
            print(f"등록: {item.id} ({item.kind_name}, {item.name})")
        else:
            item = character.get(args.id)
            if item is None:
                print(f"등록한 캐릭터 없음: {args.id}. debutkit character list 로 확인", file=sys.stderr)
                return 1
        if command == "use":
            character.use(item.id)
            print(f"방송에 사용: {item.name}. " + (f"OBS 브라우저 소스 주소 http://127.0.0.1:{OVERLAY_PORT}/character" if item.renders_in_overlay
                                                 else f"{item.broadcast}에서 표시"))
            return 0
        if command == "remove":
            print(f"삭제: {character.remove(item.id)}")
            return 0
        if command == "send":
            target = character.send(item, args.to, args.folder)
            app = character.APP_FOLDERS[args.to][0]
            print(f"{app}로 복사: {target}\n{app}를 다시 시작하면 모델 목록에 표시")
            return 0
    except (character.CharacterError, OSError) as error:
        print(f"캐릭터 작업 실패: {error}", file=sys.stderr)
        return 1
    print(f"  종류: {item.kind_name}" + (f" ({item.version})" if item.version else ""))
    if item.author:
        print(f"  제작자: {item.author}")
    print(f"  방송: {item.broadcast}")
    for line in item.license:
        print(f"  사용 조건: {line}")
    for line in item.warnings:
        print(f"  확인 필요: {line}")
    return 0


def _vts(args: argparse.Namespace) -> int:
    from . import vts

    command = args.vts_command
    if command == "logout":
        removed = vts.forget_token()
        print(f"VTube Studio 토큰 삭제: {removed}" if removed else "VTube Studio 연결 전")
        return 0
    try:
        prompt = lambda: print("VTube Studio 화면에서 debutkit 플러그인 허용을 누르십시오(제한 시간 약 1분)", flush=True)  # noqa: E731
        with vts.connect(args.url, request_new=command == "login", on_prompt=prompt) as client:
            if command == "login":
                print(f"VTube Studio 연결 완료. 토큰 저장 위치: {vts.token_path()}")
            elif command == "models":
                for model in client.models():
                    print(("* " if model.loaded else "  ") + model.name)
            elif command == "load":
                model = vts.find_model(client.models(), args.name)
                client.load_model(model.id)
                print(f"불러옴: {model.name}")
            elif command == "hotkeys":
                for hotkey in client.hotkeys():
                    print(f"  {hotkey.name}  ({hotkey.kind})")
            elif command == "trigger":
                client.trigger(args.name)
                print(f"실행: {args.name}")
    except vts.VtsError as error:
        print(f"VTube Studio: {error}", file=sys.stderr)
        return 1
    return 0


def _start_vts_reactions(server: Any, args: argparse.Namespace) -> None:
    """후원, 멤버십 알림 때 VTube Studio 단축키 실행(debutkit vts login 필요)."""
    from . import vts
    from .overlay.events import system_event

    reactions = vts.parse_reactions(args.vts_reaction)
    if not reactions:
        return
    if vts.load_token() is None:
        print("  VTube Studio 후원 반응: 연결 전(debutkit vts login 실행 필요)")
        return
    reactor = vts.VtsReactor(reactions, notify=lambda text: server.hub.publish(system_event(text))).start()
    server.hub.taps.append(reactor)
    server.attach(reactor)
    rules = ", ".join(f"{reaction.min_won:,}원 이상 {reaction.hotkey}" if reaction.min_won else f"모든 후원 {reaction.hotkey}" for reaction in reactions)
    print(f"  VTube Studio 후원 반응: {rules}")


def _start_motion_reactions(server: Any, args: argparse.Namespace) -> None:
    """후원, 멤버십 알림 때 debutkit 캐릭터 화면의 3D 캐릭터 동작 실행."""
    from . import motion, vts

    reactions = vts.parse_reactions(args.motion_reaction)
    if not reactions:
        return
    server.hub.taps.append(motion.MotionReactor(reactions, server.motion))
    unknown = [reaction.hotkey for reaction in reactions if motion.get(reaction.hotkey) is None]
    rules = ", ".join(f"{reaction.min_won:,}원 이상 {reaction.hotkey}" if reaction.min_won else f"모든 후원 {reaction.hotkey}" for reaction in reactions)
    print(f"  동작 후원 반응: {rules}" + (f" (등록하지 않은 동작: {', '.join(unknown)})" if unknown else ""))


def _motion_line(item: Any, idle_id: str) -> str:
    mark = "* " if item.id == idle_id else "  "
    length = f"{item.duration:.1f}초" if item.duration else "길이 미확인"
    return f"{mark}{item.id:20} {item.kind_name:5} {length:>9}  {item.name}"


def _motion(args: argparse.Namespace) -> int:
    from . import motion

    command = args.motion_command
    try:
        if command == "list":
            current = motion.idle()
            print("등록한 동작(* 기본 동작). 3D 캐릭터(VRM, GLB, FBX)에 사용")
            for item in motion.all_motions():
                print(_motion_line(item, current.id if current else ""))
            print(f"보관 위치: {motion.library_dir()}")
            return 0
        if command == "play":
            return _motion_play(args)
        if command == "idle":
            if args.off:
                motion.set_idle(None)
                print("기본 동작 해제: 캐릭터 화면의 기본 움직임 사용")
                return 0
            if not args.id:
                current = motion.idle()
                print(f"기본 동작: {current.name} ({current.id})" if current else "기본 동작 없음")
                return 0
            chosen = motion.set_idle(args.id)
            print(f"기본 동작: {chosen.name if chosen else args.id}. 실행 중인 캐릭터 화면은 5초 안에 바뀜")
            return 0
        if command == "add":
            added, skipped = motion.add(args.path, name=args.name or "", clip=args.clip or "")
            for found in added:
                print(f"등록: {found.id} ({found.kind_name}, {found.name})")
            for line in skipped:
                print(f"  건너뜀: {line}", file=sys.stderr)
            if len(added) != 1:
                return 0
            item = added[0]
        else:
            item = motion.get(args.id)
            if item is None:
                print(f"등록한 동작 없음: {args.id}. debutkit motion list 로 확인", file=sys.stderr)
                return 1
            if command == "remove":
                print(f"삭제: {motion.remove(item.id)}")
                return 0
    except (motion.MotionError, OSError) as error:
        print(f"동작 작업 실패: {error}", file=sys.stderr)
        return 1
    print(f"  종류: {item.kind_name}" + (f" ({item.version})" if item.version else "") + (f", 동작 이름 {item.clip}" if item.clip else ""))
    print(f"  길이: {item.duration:.1f}초, 움직이는 뼈 {item.bones}개" if item.duration else f"  움직이는 뼈 {item.bones}개")
    for line in item.license:
        print(f"  사용 조건: {line}")
    for line in item.warnings:
        print(f"  확인 필요: {line}")
    return 0


def _motion_play(args: argparse.Namespace) -> int:
    """실행 중인 오버레이(명령줄 또는 설정 마법사)에 동작 실행 요청."""
    import urllib.error
    import urllib.request

    if not args.stop and not args.id:
        print("실행할 동작을 지정하거나 --stop 사용", file=sys.stderr)
        return 2
    body = json.dumps({"stop": True} if args.stop else {"id": args.id}).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{args.port}/motion", data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            answer = {} if args.stop else json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        print(f"동작 실행 실패: 등록한 동작 없음({args.id})" if error.code == 404 else f"동작 실행 실패: {error}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, OSError, ValueError) as error:
        print(f"오버레이에 연결하지 못함({args.port}번 포트): debutkit overlay 또는 설정 마법사의 오버레이 시작 필요 ({error})", file=sys.stderr)
        return 1
    print("동작 멈춤" if args.stop else f"동작 실행: {answer.get('name', args.id)}")
    return 0


def _draw_show(config: Any, port: int) -> None:
    from . import draw

    print(f"후원 추첨: {'사용 중' if config.enabled else '사용 꺼짐'}")
    print("  상품표")
    for prize in config.prizes:
        entry = config.entry(prize)
        mark = "  희귀" if entry["rare"] else "  꽝" if entry["miss"] else ""
        print(f"    {prize.name:20} 가중치 {prize.weight:g}, 확률 {entry['percent']}%{mark}")
    kind = "금액이 정확히 같을 때만" if config.exact else "금액 이상이면 가장 큰 규칙"
    print(f"  추첨 규칙({kind})")
    for rule in reversed(config.rules):
        print(f"    {rule.min_won:>10,}원  {rule.draws}회")
    print(f"  구독, 멤버십: {'1회 추첨' if config.members else '추첨 안 함'}")
    print(f"  연출: {draw.STYLES[config.style]}, 결과 표시 {config.seconds}초, 추첨 이름 {config.title}")
    print(f"  표시: {draw.POSITIONS[config.position]}, 크기 {config.scale}%, 효과음 {'켬' if config.sound else '끔'}, 확률 {'표시' if config.show_percent else '표시 안 함'}")
    print(f"  방송 화면 http://127.0.0.1:{port}/draw  조작 화면 http://127.0.0.1:{port}/draw/control")


def _draw_pairs(values: list[str], label: str) -> list[tuple[str, str]]:
    pairs = []
    for value in values:
        first, sep, rest = value.partition(":")
        if not sep or not first.strip() or not rest.strip():
            raise ValueError(f"{label} 형식 오류: {value}")
        pairs.append((first.strip(), rest.strip()))
    return pairs


def _draw(args: argparse.Namespace) -> int:
    """후원 추첨 설정 보기, 바꾸기, 시험 추첨."""
    from . import draw

    command = args.draw_command
    if command == "show":
        _draw_show(draw.load_config(), args.port)
        return 0
    if command == "test":
        return _post_overlay(args.port, "/draw/test", {"amount": args.amount}, lambda answer: f"시험 추첨 {answer.get('count')}회: {answer.get('script', '')}")
    current = draw.load_config().to_dict()
    data: dict[str, Any] = {key: current[key] for key in ("enabled", "prizes", "rules", "exact", "members", "style", "seconds", "title", "position",
                                                           "scale", "sound", "show_percent")}
    try:
        if args.prize:
            data["prizes"] = [{"name": name, "weight": weight} for weight, name in _draw_pairs(args.prize, "상품(가중치:이름)")]
        if args.rule:
            data["rules"] = [{"min_won": amount, "draws": count} for amount, count in _draw_pairs(args.rule, "규칙(금액:횟수)")]
        for key in ("enabled", "exact", "members", "style", "seconds", "title", "position", "scale", "sound", "show_percent"):
            if getattr(args, key) is not None:
                data[key] = getattr(args, key)
        config = draw.save_config(draw.from_request(data))
    except (ValueError, OSError) as error:
        print(f"후원 추첨 설정 실패: {error}", file=sys.stderr)
        return 1
    _draw_show(config, args.port)
    print("저장했습니다. 실행 중인 오버레이에는 다음 후원부터 적용")
    return 0


def _raffle(args: argparse.Namespace) -> int:
    """실행 중인 오버레이의 시청자 참여 추첨 조작."""
    command = args.raffle_command

    def describe(status: dict[str, Any]) -> str:
        if status.get("type") == "result":
            names = ", ".join(f"{index + 1} {winner['name']}" if status["mode"] == "order" else winner["name"] for index, winner in enumerate(status["winners"]))
            return f"{'순서' if status['mode'] == 'order' else '당첨'}(참가 {status['total']}명): {names}" + (f" 외 {status['more']}명" if status.get("more") else "")
        lines = [f"{'모집 중' if status['open'] else '모집 마감'}: {status['title']}, 참가 명령 {status['keyword']}, 참가 {status['count']}명"
                 + (f", {status['donation_min']:,}원 이상 후원 참가" if status.get("donation_min") is not None else "")]
        lines += [f"  {entry['name']}  ({entry['platform']}, {entry['source']})" for entry in status.get("entries", [])[:30]]
        return "\n".join(lines)

    if command == "status":
        return _get_overlay(args.port, "/raffle", describe)
    if command == "start":
        body: dict[str, Any] = {"keyword": args.keyword, "title": args.title}
        if args.donation_min is not None:
            body["donation_min"] = None if args.donation_min < 0 else args.donation_min
        return _post_overlay(args.port, "/raffle/start", body, describe)
    if command == "draw":
        return _post_overlay(args.port, "/raffle/draw", {"mode": "order" if args.order else "pick", "count": args.count}, describe)
    return _post_overlay(args.port, f"/raffle/{command}", {}, describe)


def _phone(args: argparse.Namespace) -> int:
    """실행 중인 오버레이의 휴대폰 얼굴 추적 조작."""
    command = args.phone_command

    def describe(status: dict[str, Any]) -> str:
        app = status.get("apps", {}).get(status.get("app"), status.get("app"))
        if not status.get("running"):
            return f"휴대폰 얼굴 추적 꺼짐(저장한 설정: {app}, 휴대폰 {status.get('ip') or '없음'})"
        if status.get("receiving"):
            state = f"추적 중, 초당 {status['fps']}회, 표정 {status['shapes']}개" if status.get("found") else "연결됨, 얼굴을 찾지 못함"
        else:
            state = status.get("error") or "휴대폰 응답 대기: 앱 실행, 같은 Wi-Fi, 방화벽 허용 확인"
        options = ", ".join(name for name, on in (("거울처럼", status.get("mirror")), ("위아래 반전", status.get("flip_pitch"))) if on) or "선택 없음"
        return f"{app}, 휴대폰 {status['ip']}, PC 수신 {status['local']}:{status['port']}\n  {state}\n  {options}"

    if command == "status":
        return _get_overlay(args.port, "/phone/status", describe)
    if command == "start":
        body: dict[str, Any] = {"app": args.app, "ip": args.ip}
        if args.mirror is not None:
            body["mirror"] = args.mirror
        if args.flip_pitch is not None:
            body["flip_pitch"] = args.flip_pitch
        return _post_overlay(args.port, "/phone/start", body, describe)
    if command == "calibrate":
        return _post_overlay(args.port, "/phone/calibrate", {"reset": args.reset}, describe)
    return _post_overlay(args.port, "/phone/stop", {}, describe)


def _vmc(args: argparse.Namespace) -> int:
    """실행 중인 오버레이의 VMC 프로토콜 송신(얼굴 추적 값을 Warudo, VSeeFace 등으로)."""

    def describe(status: dict[str, Any]) -> str:
        if not status.get("running"):
            return "VMC 송신 꺼짐"
        options = ", ".join(name for name, on in (("퍼펙트 싱크 표정", status.get("perfect_sync")), ("거울처럼", status.get("mirror"))) if on) or "선택 없음"
        state = status.get("error") or (f"보낸 횟수 {status.get('sent', 0)}" if status.get("receiving") else "얼굴 추적 값 대기(추적 화면이나 휴대폰 추적 켜기)")
        return f"VMC 송신 중: {status['host']}:{status['port']}, 초당 최대 {status['rate']}회\n  {state}\n  {options}"

    if args.vmc_command == "status":
        return _get_overlay(args.port, "/vmc/status", describe)
    if args.vmc_command == "start":
        body = {"host": args.host, "port": args.vmc_port, "perfect_sync": not args.no_perfect_sync, "mirror": args.mirror, "rate": args.rate}
        return _post_overlay(args.port, "/vmc/start", body, describe)
    return _post_overlay(args.port, "/vmc/stop", {}, describe)


def _remote(args: argparse.Namespace) -> int:
    """실행 중인 오버레이의 휴대폰 조작 화면(켜기, 끄기, 등록, 승인, 삭제)."""
    command = args.remote_command

    def describe(status: dict[str, Any]) -> str:
        if "url" in status and "secret" not in status and "devices" not in status:  # 등록 QR 주소
            return (f"휴대폰 브라우저에서 열기(5분 유효, 1대): {status['url']}\n  휴대폰에 확인 번호 {status['code']}가 보이면 "
                    f"debutkit remote approve {status['id']} 또는 PC의 휴대폰 연결 화면에서 승인")
        state = f"켜짐: {status['url']}" if status.get("running") else (status.get("error") or "꺼짐")
        lines = [f"휴대폰 조작 화면 {state}"]
        for item in status.get("devices", []):
            mark = "승인됨" if item["approved"] else f"승인 대기(확인 번호 {item['code']})" if item["claimed"] else "QR 대기"
            lines.append(f"  {item['id']}  {item['name']}  {mark}")
        if not status.get("running") and status.get("addresses"):
            lines.append(f"  이 PC 주소: {', '.join(status['addresses'])}")
        return "\n".join(lines)

    if command == "status":
        return _get_overlay(args.port, "/remote/admin", describe)
    if command == "start":
        return _post_overlay(args.port, "/remote/admin/start", {"address": args.address, "port": args.listen_port}, describe)
    if command in ("approve", "remove"):
        return _post_overlay(args.port, f"/remote/admin/{command}", {"id": args.id}, describe)
    return _post_overlay(args.port, f"/remote/admin/{command}", {}, describe)


def _describe_broadcast(status: dict[str, Any]) -> str:
    config = status["config"]
    platform = status["platforms"][config["platform"]]["name"]
    head = status["message"] + (f"({status['phase']})" if status.get("phase") else "")
    lines = [head]
    if status.get("error"):
        lines.append(f"  최근 오류: {status['error']}")
    lines.append(f"  {platform}, 서버 {status.get('server') or '없음'}, 스트림 키 {'저장됨' if status.get('key_saved') else '없음'}")
    encoder = status.get("encoder_name") or ("자동" if config["encoder"] == "auto" else config["encoder"])
    lines.append(f"  화질 {status['qualities'][config['quality']]}, 영상 {status['video_kbps']} kbps, 인코더 {encoder}")
    lines.append(f"  마이크 {config['mic'] or '없음(무음)'}" + (f", 함께 보낼 소리 {config['extra_audio']}" if config["extra_audio"] else ""))
    stats = status.get("stats") or {}
    if status["state"] == "live":
        lines.append(f"  방송 {status['seconds']}초, 초당 {stats.get('fps')} 프레임, {stats.get('kbps')} kbps, 버린 프레임 {stats.get('dropped', 0)}")
    lines += [f"  주의: {text}" for text in status.get("warnings", [])]
    if not status.get("supported", True):
        lines.append("  OBS 없이 방송은 현재 Windows에서만 지원")
    return "\n".join(lines)


def _broadcast(args: argparse.Namespace) -> int:
    """실행 중인 오버레이의 OBS 없이 바로 방송."""
    command, port = args.broadcast_command, args.port
    if command == "status":
        return _get_overlay(port, "/broadcast", _describe_broadcast)
    if command == "devices":
        def devices(found: dict[str, Any]) -> str:
            if not found.get("ffmpeg"):
                from .tools import install_hint

                return f"ffmpeg 없음: {install_hint()}"
            lines = [f"인코더: {found.get('encoder_name') or '사용할 수 있는 H.264 인코더 없음'}", "녹음 장치(--mic, --extra-audio 에 이름 또는 대체 이름):"]
            lines += [f"  {item['name']}\n    {item['id']}" for item in found.get("audio", [])] or ["  없음"]
            return "\n".join(lines)

        return _get_overlay(port, "/broadcast/devices", devices, timeout=90)
    if command == "set":
        body = {name: getattr(args, name) for name in ("platform", "server", "quality", "kbps", "encoder", "mic", "extra_audio", "camera", "title",
                                                       "background") if getattr(args, name) is not None}
        return _post_overlay(port, "/broadcast/config", body, _describe_broadcast)
    if command == "key":
        if args.clear:
            body: dict[str, Any] = {"clear": True}
        else:
            import getpass

            key = sys.stdin.readline().strip() if args.stdin else getpass.getpass("스트림 키(입력한 글자는 표시하지 않음): ")
            body = {"key": key}
        if args.platform:
            body["platform"] = args.platform
        return _post_overlay(port, "/broadcast/key", body, _describe_broadcast)
    if command == "window":
        return _post_overlay(port, "/broadcast/window", {}, _describe_broadcast)
    if command == "stop":
        return _post_overlay(port, "/broadcast/stop", {"close": args.close}, _describe_broadcast)
    code = _post_overlay(port, "/broadcast/start", {}, lambda status: f"{status['message']}: 송출 화면 창을 열고 연결합니다")
    if code:
        return code
    import time

    status = _fetch_overlay(port, "/broadcast")
    deadline = time.monotonic() + 90
    while status is not None and status["state"] == "starting" and time.monotonic() < deadline:
        time.sleep(1)
        status = _fetch_overlay(port, "/broadcast")
    if status is None:
        return 1
    print(_describe_broadcast(status))
    return 0 if status["state"] == "live" else 1


def _logo_progress() -> Callable[[dict[str, Any]], None]:
    """AI Horde 진행: 단계가 바뀌거나 1분이 지날 때 한 줄(대기열 위치, 예상 시간)."""
    last: dict[str, Any] = {"state": None, "at": -60, "elapsed": 0}
    names = {"submitting": "보내는 중", "queued": "대기 중", "processing": "그리는 중", "downloading": "그림 받는 중", "tracing": "벡터로 바꾸는 중"}

    def show(values: dict[str, Any]) -> None:
        state = values.get("state", "")
        elapsed = last["elapsed"] = int(values["elapsed"]) if "elapsed" in values else last["elapsed"]  # 벡터화 단계는 마지막 경과 시간
        if state == last["state"] and elapsed - last["at"] < 60:
            return
        last.update(state=state, at=elapsed)
        parts = [names.get(state, state)]
        if state == "queued" and values.get("queue_position"):
            parts.append(f"대기열 {values['queue_position']}번째")
        if state in ("queued", "processing") and values.get("wait_time"):
            parts.append(f"예상 {max(1, round(values['wait_time'] / 60))}분")
        print(f"  [{elapsed // 60:02d}:{elapsed % 60:02d}] {', '.join(parts)}", flush=True)
    return show


def _logo(args: argparse.Namespace) -> int:
    """방송 로고 만들기(오버레이 없이 실행). 아이콘과 기본 도형은 무료, AI 심볼은 AI Horde(계정 없음) 또는 저장한 본인 키 사용."""
    from . import logo

    studio = logo.LogoStudio()
    command = args.logo_command
    try:
        if command == "key":
            if args.clear:
                studio.set_key(args.provider, None)
                print(f"{logo.PROVIDERS[args.provider].name} 키 삭제")
                return 0
            import getpass

            key = sys.stdin.readline().strip() if args.stdin else getpass.getpass(f"{logo.PROVIDERS[args.provider].name} 키(입력한 글자는 표시하지 않음): ")
            status = studio.set_key(args.provider, key)
            mode = {"file": "암호화해 이 PC에 저장", "keyring": "운영체제 키 보관소에 저장", "memory": "이번 실행 동안만 사용(저장 안 함)"}[status["key_storage"]]
            print(f"{logo.PROVIDERS[args.provider].name} 키 {mode}")
            return 0
        if command == "list":
            print("기본 도형: " + ", ".join(f"{key}({label})" for key, label in studio.status()["templates"].items()))
            recent = studio.status()["recent"]
            print("최근 AI 심볼:" if recent else "최근 AI 심볼 없음")
            for item in recent:
                print(f"  {item['id']}  {item['provider']} {item['model']}  {item['description']}")
            return 0
        if command == "icons":
            from . import logo_icons

            found = logo_icons.search(" ".join(args.words or []), limit=args.limit)
            for icon in found:
                styles = ", ".join(icon["svg"])
                print(f"  {icon['id']:<40} {icon['ko']} ({styles})")
            print(f"{len(found)}개" + ("" if found else ": 다른 검색어(예: 고양이, 마이크, 하트, 동물, 음식)로 다시 찾기"))
            return 0
        colors = [logo.check_color(value) for value in (args.color or [])][:2]
        primary, accent = colors[0] if colors else "#FF4F8B", colors[1] if len(colors) > 1 else "#1E2327"
        symbol: dict[str, Any]
        if args.ai:
            cost = {"aihorde": "무료, 계정 없음", "comfyui": "무료", "huggingface": "무료 한도 사용"}.get(args.ai, "요금 발생")
            wait = "익명은 대기열 때문에 보통 10~30분, Ctrl+C로 취소" if args.ai == "aihorde" else "보통 30초에서 몇 분"
            print(f"{logo.PROVIDERS[args.ai].name}로 심볼 만드는 중({cost}, {wait})", flush=True)
            if args.ai == "aihorde" and not studio.keys.has("aihorde"):
                print("  키 없이(익명) 보냄: 설명과 결과 그림이 LAION 공개 데이터셋에 공유됨(13세 이상 사용 가능)", flush=True)
            made = studio.generate(args.ai, args.quality, args.describe, args.style, colors, args.comfyui, progress=_logo_progress())
            symbol = {"id": made["id"]}
        elif args.icon:
            symbol = {"icon": args.icon, "style": args.icon_style, "colors": args.icon_colors, "primary": primary, "accent": accent}
        else:
            symbol = {"template": args.template, "primary": primary, "accent": accent}
        request = {"name": args.name or "", "font": args.font, "layout": args.layout, "symbol": symbol, "text_color": args.text_color,
                   "background": args.background, "finish": args.finish, "finish_color": accent}
        svg = studio.make(request)
        out = Path(args.out)
        out.write_text(svg, encoding="utf-8")
        entry = studio.record({**request, "file": str(out)})
        print(f"로고 저장: {out}" + (" (AI 생성 표시 포함)" if args.ai else ""))
        about = entry.get("symbol") or {}
        if about.get("kind") == "icon":
            print(f"심볼 출처: {about['set']} '{about['icon']}'({about['license']}, {about['copyright']})")
        if about.get("kind") in ("icon", "template"):
            print(f"안내: {logo.NON_EXCLUSIVE}")
        return 0
    except KeyboardInterrupt:
        print("\n취소함", file=sys.stderr)
        return 130
    except logo.LogoError as error:
        print(f"로고 만들기 실패: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"저장 실패: {error}", file=sys.stderr)
        return 1


def _fetch_overlay(port: int, path: str, timeout: float = 5) -> dict[str, Any] | None:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as response:
            return json.loads(response.read() or b"{}")
    except (urllib.error.URLError, OSError, ValueError) as error:
        print(f"오버레이에 연결하지 못함({port}번 포트): debutkit overlay 또는 설정 마법사의 오버레이 시작 필요 ({error})", file=sys.stderr)
        return None


def _get_overlay(port: int, path: str, describe: Callable[[dict[str, Any]], str], timeout: float = 5) -> int:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as response:
            answer = json.loads(response.read() or b"{}")
    except (urllib.error.URLError, OSError, ValueError) as error:
        print(f"오버레이에 연결하지 못함({port}번 포트): debutkit overlay 또는 설정 마법사의 오버레이 시작 필요 ({error})", file=sys.stderr)
        return 1
    print(describe(answer))
    return 0


def _post_overlay(port: int, path: str, body: dict[str, Any], describe: Callable[[dict[str, Any]], str]) -> int:
    """실행 중인 오버레이에 요청. 오류 응답의 error 안내를 그대로 보여 준다."""
    import urllib.error
    import urllib.request

    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"},
                                     method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            answer = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        try:
            message = json.loads(error.read() or b"{}").get("error") or str(error)
        except ValueError:
            message = str(error)
        print(f"요청 실패: {message}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, OSError, ValueError) as error:
        print(f"오버레이에 연결하지 못함({port}번 포트): debutkit overlay 또는 설정 마법사의 오버레이 시작 필요 ({error})", file=sys.stderr)
        return 1
    print(describe(answer))
    return 0


def _launch_profile_text(profile: Any, active: bool) -> list[str]:
    from .launcher import KINDS

    lines = [f"{'* ' if active else '  '}{profile.name}"]
    for item in profile.start:
        place = " [창 위치 기억]" if item.window else ""
        lines.append(f"    켤 것 {KINDS[item.kind]}: {item.label}  (다음까지 {item.delay:g}초){place}")
    for name in profile.stop:
        lines.append(f"    끌 것: {name}")
    flags = [("이미 켜진 것 건너뛰기", profile.skip_running), ("다시 켜지면 알림", profile.watch), ("다시 끄기", profile.rekill),
             ("방송 끝에 다시 켜기", profile.restore), ("오버레이 시작", profile.overlay), ("OBS 연결 확인", profile.obs_check)]
    lines.append("    " + ", ".join(f"{label} {'켬' if on else '끔'}" for label, on in flags))
    return lines


def _launch(args: argparse.Namespace) -> int:
    """방송 시작 버튼: 세팅 켜기, 방송 끝, 목록, 항목 추가와 삭제, 옵션, 창 위치 기억, 감시, 백업."""
    import time

    from . import launcher

    command = args.launch_command or "run"
    for name, default in (("profile", None), ("overlay", False), ("obs_check", False), ("no_watch", False)):
        if not hasattr(args, name):  # debutkit launch(하위 명령 없음)는 run과 같게
            setattr(args, name, default)
    try:
        config = launcher.load()
        if command == "list":
            for profile in config.profiles:
                print("\n".join(_launch_profile_text(profile, profile.name == config.active)))
            if config.protect:
                print("보호(끄지 않음): " + ", ".join(config.protect))
            print(f"설정 파일: {launcher.settings.data_path(launcher.DATA)}")
            return 0
        if command == "add":
            try:
                profile = config.profile(args.profile)
            except launcher.LauncherError:
                launcher.put_profile(config, {"name": args.profile})
                profile = config.profile(args.profile)
            data = launcher.profile_dict(profile)
            for target in args.targets:
                if args.stop:
                    data["stop"].append(target)
                else:
                    data["start"].append({"target": target, "delay": args.delay, "args": args.args or "", "name": args.name or ""})
            launcher.save(launcher.put_profile(config, data, old_name=profile.name))
            print("\n".join(_launch_profile_text(config.profile(args.profile), args.profile == config.active)))
            return 0
        if command == "remove":
            profile = config.profile(args.profile)
            before = len(profile.start) + len(profile.stop)
            wanted = {target.casefold() for target in args.targets}
            profile.start = [item for item in profile.start if item.target.casefold() not in wanted and item.label.casefold() not in wanted]
            profile.stop = [name for name in profile.stop if name.casefold() not in wanted and launcher.process_key(name) not in
                            {launcher.process_key(target) for target in args.targets}]
            if len(profile.start) + len(profile.stop) == before:
                print(f"지울 항목 없음: {', '.join(args.targets)}", file=sys.stderr)
                return 1
            launcher.save(config)
            print("\n".join(_launch_profile_text(profile, profile.name == config.active)))
            return 0
        if command == "set":
            profile = config.profile(args.profile)
            data = launcher.profile_dict(profile)
            for key in ("skip_running", "place_running", "watch", "rekill", "restore", "overlay", "obs_check"):
                if getattr(args, key) is not None:
                    data[key] = getattr(args, key)
            if args.rename:
                data["name"] = args.rename
            launcher.put_profile(config, data, old_name=profile.name)
            if args.use:
                config.active = data["name"]
            launcher.save(config)
            print("\n".join(_launch_profile_text(config.profile(data["name"]), data["name"] == config.active)))
            return 0
        if command == "copy":
            launcher.save(launcher.copy_profile(config, args.profile, args.new_name))
            print(f"세팅 복제: {args.profile} -> {args.new_name}")
            return 0
        if command == "delete":
            launcher.save(launcher.remove_profile(config, args.profile))
            print(f"세팅 삭제: {args.profile}")
            return 0
        if command == "use":
            config.active = config.profile(args.profile).name
            launcher.save(config)
            print(f"기본 세팅: {config.active}")
            return 0
        if command == "protect":
            if args.remove:
                keys = {launcher.process_key(name) for name in args.names}
                config.protect = [name for name in config.protect if launcher.process_key(name) not in keys]
            else:
                config.protect += [name for name in args.names if launcher.process_key(name) not in {launcher.process_key(p) for p in config.protect}]
            launcher.save(config)
            print("보호(끄지 않음): " + (", ".join(config.protect) or "없음") + ". 운영체제, 보안 프로그램, debutkit은 항상 보호")
            return 0
        if command == "remember":
            steps = launcher.remember_windows(config, args.profile)
            launcher.save(config)
            print(launcher.summary(steps))
            return 0
        if command == "export":
            Path(args.file).write_text(launcher.export_text(config), encoding="utf-8")
            print(f"백업 저장: {args.file}")
            return 0
        if command == "import":
            launcher.save(launcher.import_text(Path(args.file).read_text(encoding="utf-8")))
            print(f"백업 불러옴: {args.file}")
            return 0
        if command == "end":
            steps = launcher.Launcher(config, report=lambda step: print(step.text(), flush=True)).end(args.profile, restore=False if args.no_restore else None)
            if not steps:
                print("다시 켤 프로그램 없음")
            return 0
        if command == "watch":
            profile = config.profile(args.profile)
            if not profile.stop:
                print("끌 것이 없어 감시할 프로그램 없음", file=sys.stderr)
                return 1
            return _launch_watch(profile, config, until_interrupted=True)
        # run
        profile = config.profile(args.profile)
        print(f"방송 시작 버튼: {profile.name}", flush=True)
        steps = launcher.Launcher(config, report=lambda step: print("  " + step.text(), flush=True)).run(profile.name)
        if not steps:
            print("  " + launcher.summary([]))
        if profile.obs_check or args.obs_check:
            print("  OBS 연결 확인 중(최대 60초)", flush=True)
            from .settings import load as load_settings

            port = load_settings().get("obs_port", 4455)
            ok = launcher.wait_for_port("127.0.0.1", port, 60.0)
            print(f"  {'OBS 연결 가능' if ok else 'OBS WebSocket 응답 없음: OBS 도구 메뉴의 WebSocket 서버 설정에서 사용 체크'} (포트 {port})")
        watcher = None
        if profile.watch and profile.stop and not args.no_watch:
            watcher = launcher.Watcher(profile, config, lambda text: print(f"[{time.strftime('%H:%M')}] {text}", flush=True)).start()
        if profile.overlay or args.overlay:
            print("저장한 설정으로 오버레이 시작(debutkit overlay --saved)", flush=True)
            try:
                return main(["overlay", "--saved"])
            finally:
                if watcher:
                    watcher.stop()
        if watcher:
            print("꺼 둔 프로그램이 다시 켜지는지 감시 중. 방송이 끝나면 Ctrl+C 후 debutkit launch end", flush=True)
            return _launch_watch(profile, config, until_interrupted=True, watcher=watcher)
        return 1 if any(step.state == "failed" for step in steps) else 0
    except launcher.LauncherError as error:
        print(str(error), file=sys.stderr)
        return 1
    except OSError as error:
        print(f"설정 파일 읽기, 쓰기 실패: {error}", file=sys.stderr)
        return 1


def _launch_watch(profile: Any, config: Any, *, until_interrupted: bool, watcher: Any = None) -> int:
    import time

    from . import launcher

    watcher = watcher or launcher.Watcher(profile, config, lambda text: print(f"[{time.strftime('%H:%M')}] {text}", flush=True)).start()
    if watcher is not None and until_interrupted:
        print("감시 중: " + ", ".join(profile.stop) + " (끝: Ctrl+C)", flush=True)
    try:
        while until_interrupted:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        watcher.stop()
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
    scenes.add_argument("--avatar", default="vts", choices=["vts", "vseeface", "warudo", "vmagicmirror", "debutkit", "none"],
                        help="아바타 프로그램. debutkit: debutkit 캐릭터 화면(PNGTuber, VRM) (기본 %(default)s)")
    scenes.add_argument("--overlay-port", type=int, default=OVERLAY_PORT, help="debutkit overlay 포트 (기본 %(default)s)")
    scenes.add_argument("--replace", action="store_true", help="같은 이름의 장면을 삭제 후 다시 생성")
    scenes.add_argument("--switch", action="store_true", help="생성 후 대기 화면으로 전환")
    scenes.add_argument("--replay-buffer", type=int, nargs="?", const=60, metavar="초",
                        help="자동 클립용 리플레이 버퍼 켜기 (길이 기본 60초)")
    scenes.add_argument("--dry-run", action="store_true", help="OBS에 연결하지 않고 설계도만 출력")
    scenes.set_defaults(func=_scenes)

    cameras = sub.add_parser("camera", help="휴대폰 카메라 영상: SRT로 받는 OBS 미디어 소스와 휴대폰 앱(Larix Broadcaster 등) 연결 정보")
    cameras_sub = cameras.add_subparsers(dest="camera_command", required=True)
    cameras_sub.add_parser("info", help="휴대폰 앱에 입력할 주소, 암호, Larix 가져오기 주소")
    camera_setup = cameras_sub.add_parser("setup", help="OBS에 휴대폰 카메라 소스 만들기(있으면 포트, 암호 맞춤)")
    camera_setup.add_argument("--scene", action="append", metavar="장면", help="넣을 장면(여러 번 지정 가능, 기본 현재 방송 장면)")
    camera_setup.add_argument("--port", type=int, help="수신 포트(기본 9710, 저장)")
    camera_setup.add_argument("--latency", type=int, metavar="밀리초", help="지연 여유(80에서 2000, 기본 200, 저장)")
    camera_setup.add_argument("--new-passphrase", action="store_true", help="새 암호 만들기(휴대폰 앱에 다시 등록 필요)")
    camera_setup.add_argument("--app", action="store_true", help="debutkit 휴대폰 앱 영상(WebRTC)을 받는 브라우저 소스 만들기(SRT 대신)")
    camera_setup.add_argument("--overlay-port", type=int, default=OVERLAY_PORT, help="debutkit overlay 포트 (기본 %(default)s, --app)")
    camera_status = cameras_sub.add_parser("status", help="OBS 소스 상태(휴대폰 연결 대기, 수신 중 등)")
    for command in (camera_setup, camera_status):
        command.add_argument("--obs-host", default="127.0.0.1")
        command.add_argument("--obs-port", type=int, default=4455, help="OBS WebSocket 포트 (기본 %(default)s)")
        command.add_argument("--obs-password", help="OBS WebSocket 비밀번호 (또는 OBS_WEBSOCKET_PASSWORD)")
    cameras.set_defaults(func=_camera)

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
    clip.add_argument("--clip-gif", action="store_true", default=None, help="클립마다 움짤(GIF, 앞 6초, 폭 480)도 만들기")
    clip.add_argument("--clip-shorts", action="store_true", default=None, help="클립마다 세로 쇼츠(1080x1920, 흐린 배경)도 만들기")
    clip.add_argument("--obs-host", default="127.0.0.1")
    clip.add_argument("--obs-port", type=int, default=4455)
    clip.add_argument("--obs-password", help="OBS WebSocket 비밀번호 (또는 OBS_WEBSOCKET_PASSWORD)")
    voice = overlay.add_argument_group("캐릭터 음성 반응(debutkit 캐릭터 화면)")
    voice.add_argument("--no-voice", action="store_true", help="OBS 마이크 음량으로 캐릭터 입 움직이기 끄기")
    voice.add_argument("--voice-input", metavar="소스", help="음량을 읽을 OBS 오디오 소스 이름 (기본: OBS 설정의 마이크)")
    voice.add_argument("--voice-threshold", type=float, default=-40.0, metavar="dB", help="말하는 것으로 판단할 음량 (기본 %(default)s dBFS)")
    overlay.add_argument("--no-chat-commands", action="store_true",
                         help="스트리머, 매니저 채팅 명령(!동작, !단축키, !모집, !마감, !추첨, !순서) 끄기. 저장 설정 chat_commands로도 끌 수 있음")
    reaction = overlay.add_argument_group("후원 반응(VTube Studio 단축키, 3D 캐릭터 동작)")
    reaction.add_argument("--vts-reaction", action="append", metavar="금액:단축키",
                          help="후원이 금액(원) 이상이면 VTube Studio 단축키 실행. 예: 1000:Heart. 0은 모든 후원. 여러 번 지정 가능 (debutkit vts login 필요)")
    reaction.add_argument("--motion-reaction", action="append", metavar="금액:동작",
                          help="후원이 금액(원) 이상이면 debutkit 캐릭터 화면의 3D 캐릭터 동작 실행. 예: 1000:wave (debutkit motion list 의 동작)")
    saved = overlay.add_argument_group("저장한 설정")
    saved.add_argument("--saved", action="store_true", help="저장한 설정(채널, 포트, 자동 클립 등) 사용. 명령줄에 지정한 항목이 우선")
    saved.add_argument("--save", action="store_true", help="이번 실행의 채널과 옵션을 저장 (API 키, 비밀번호 제외)")
    overlay.set_defaults(func=_overlay, overlay_defaults={dest: overlay.get_default(dest) for dest in OVERLAY_SETTINGS})

    chars = sub.add_parser("character", help="캐릭터 등록, 확인, 방송 사용(PNGTuber, VRM, GLB, FBX, Live2D)")
    chars_sub = chars.add_subparsers(dest="character_command", required=True)
    chars_sub.add_parser("list", help="등록한 캐릭터 목록")
    add = chars_sub.add_parser("add", help="캐릭터 등록: VRM, GLB, FBX(Mixamo 등 사람 모양 뼈), Live2D 폴더나 zip(model3.json), "
                                           "PNG 폴더(idle.png, talk.png), Inochi2D")
    add.add_argument("path", metavar="경로")
    add.add_argument("--name", help="표시할 이름")
    png = chars_sub.add_parser("png", help="상태별 PNG 이미지로 PNGTuber 캐릭터 만들기")
    png.add_argument("--idle", required=True, metavar="PNG", help="입 다문 이미지")
    png.add_argument("--talk", required=True, metavar="PNG", help="입 벌린 이미지")
    png.add_argument("--blink", metavar="PNG", help="눈 감은 이미지(선택)")
    png.add_argument("--talk-blink", metavar="PNG", help="입 벌리고 눈 감은 이미지(선택)")
    png.add_argument("--name", required=True, help="캐릭터 이름")
    for command, text in (("show", "사용 조건, 확인 필요 사항 보기"), ("use", "방송에 사용할 캐릭터로 지정"), ("remove", "등록 삭제")):
        chars_sub.add_parser(command, help=text).add_argument("id", metavar="캐릭터")
    send = chars_sub.add_parser("send", help="방송 프로그램의 모델 폴더로 복사: Live2D는 VTube Studio, VRM은 Warudo")
    send.add_argument("id", metavar="캐릭터")
    send.add_argument("--to", required=True, choices=["vts", "warudo"])
    send.add_argument("--folder", help="모델 폴더(자동으로 찾지 못한 경우)")
    chars.set_defaults(func=_character)

    draws = sub.add_parser("draw", help="후원 추첨 연출: 상품표, 금액별 추첨 횟수, 연출 설정과 시험 추첨")
    draws_sub = draws.add_subparsers(dest="draw_command", required=True)
    draws_sub.add_parser("show", help="저장한 추첨 설정 보기").add_argument("--port", type=int, default=OVERLAY_PORT, help=argparse.SUPPRESS)
    draw_set = draws_sub.add_parser("set", help="추첨 설정 바꾸기(지정한 항목만)")
    switch = draw_set.add_mutually_exclusive_group()
    switch.add_argument("--on", dest="enabled", action="store_const", const=True, help="후원이 오면 추첨")
    switch.add_argument("--off", dest="enabled", action="store_const", const=False, help="추첨 사용 안 함")
    draw_set.add_argument("--prize", action="append", metavar="가중치:이름", help="상품(여러 번 지정, 지정하면 상품표 전체를 바꿈). 예: 50:꽝 --prize 3:소원")
    draw_set.add_argument("--rule", action="append", metavar="금액:횟수", help="추첨 규칙(원 기준, 별풍선 1개 100원). 예: 1000:1 --rule 10000:11")
    mode = draw_set.add_mutually_exclusive_group()
    mode.add_argument("--exact", dest="exact", action="store_const", const=True, help="금액이 정확히 같을 때만 추첨")
    mode.add_argument("--at-least", dest="exact", action="store_const", const=False, help="금액 이상이면 가장 큰 규칙(기본)")
    draw_set.add_argument("--members", action=argparse.BooleanOptionalAction, default=None, help="구독, 멤버십도 1회 추첨")
    draw_set.add_argument("--style", choices=["card", "wheel"], help="연출: card(카드 뒤집기), wheel(룰렛)")
    draw_set.add_argument("--seconds", type=int, metavar="초", help="결과 표시 시간(3에서 60초)")
    draw_set.add_argument("--title", metavar="이름", help="추첨 이름(20자 이내, 하단 띠에 표시). 예: 벌칙 룰렛")
    draw_set.add_argument("--position", choices=["center", "left", "right"], help="표시 위치: center(아래 가운데), left(왼쪽 아래), right(오른쪽 아래)")
    draw_set.add_argument("--scale", type=int, metavar="%", help="표시 크기(60에서 140%%, 1920x1080 기준 100)")
    draw_set.add_argument("--sound", action=argparse.BooleanOptionalAction, default=None, help="효과음(OBS 오디오 제어를 켠 경우 방송에 나감)")
    draw_set.add_argument("--show-percent", action=argparse.BooleanOptionalAction, default=None, help="방송 화면에 확률 표시")
    draw_set.add_argument("--port", type=int, default=OVERLAY_PORT, help=argparse.SUPPRESS)
    draw_test = draws_sub.add_parser("test", help="실행 중인 오버레이에서 시험 추첨(저장한 설정 사용)")
    draw_test.add_argument("--amount", type=int, default=1000, metavar="원", help="시험 금액 (기본 %(default)s원)")
    draw_test.add_argument("--port", type=int, default=OVERLAY_PORT, help="오버레이 포트 (기본 %(default)s)")
    draws.set_defaults(func=_draw)

    raffles = sub.add_parser("raffle", help="시청자 참여 추첨: 채팅 명령으로 참가자 모집, 당첨자 뽑기, 순서 정하기(실행 중인 오버레이)")
    raffles.add_argument("--port", type=int, default=OVERLAY_PORT, help="오버레이 포트 (기본 %(default)s)")
    raffles_sub = raffles.add_subparsers(dest="raffle_command", required=True)
    raffles_sub.add_parser("status", help="모집 상태와 참가자 명단")
    raffle_start = raffles_sub.add_parser("start", help="모집 시작(지난 명단 삭제)")
    raffle_start.add_argument("--keyword", metavar="명령", help="참가 명령(기본 !참가, 지난 설정 유지)")
    raffle_start.add_argument("--title", metavar="이름", help="추첨 이름(20자 이내)")
    raffle_start.add_argument("--donation-min", type=int, metavar="원", help="이 금액 이상 후원한 시청자 자동 참가. -1은 후원 참가 끄기")
    raffles_sub.add_parser("stop", help="모집 마감")
    raffles_sub.add_parser("clear", help="명단 비우기")
    raffle_draw = raffles_sub.add_parser("draw", help="당첨자 뽑기(기본 1명) 또는 --order 로 순서 정하기")
    raffle_draw.add_argument("count", nargs="?", type=int, default=1, metavar="인원", help="당첨 인원(1에서 30)")
    raffle_draw.add_argument("--order", action="store_true", help="참가자 전체 순서 정하기")
    raffles.set_defaults(func=_raffle)

    phone = sub.add_parser("phone", help="휴대폰 얼굴 추적: 아이폰 iFacialMocap, VTube Studio 앱의 ARKit 표정을 캐릭터에 반영(실행 중인 오버레이)")
    phone.add_argument("--port", type=int, default=OVERLAY_PORT, help="오버레이 포트 (기본 %(default)s)")
    phone_sub = phone.add_subparsers(dest="phone_command", required=True)
    phone_sub.add_parser("status", help="연결 상태")
    phone_start = phone_sub.add_parser("start", help="연결 시작(설정 저장, 다음 오버레이 실행에도 시작)")
    phone_start.add_argument("--app", choices=["ifacialmocap", "vts"], help="휴대폰 앱(지난 설정 유지, 처음은 ifacialmocap)")
    phone_start.add_argument("--ip", metavar="주소", help="휴대폰 앱에 표시된 IP 주소(같은 Wi-Fi)")
    phone_start.add_argument("--mirror", action=argparse.BooleanOptionalAction, default=None, help="거울처럼 움직이기(기본 켬)")
    phone_start.add_argument("--flip-pitch", action=argparse.BooleanOptionalAction, default=None, help="위아래 반전")
    phone_cal = phone_sub.add_parser("calibrate", help="정면 맞추기: 지금 머리 각도를 정면으로 저장")
    phone_cal.add_argument("--reset", action="store_true", help="정면 맞추기 되돌리기")
    phone_sub.add_parser("stop", help="연결 끊기(다음 오버레이 실행 때 시작하지 않음)")
    phone.set_defaults(func=_phone)

    vmc_parser = sub.add_parser("vmc", help="VMC 프로토콜 송신: debutkit 얼굴 추적 값(웹캠, 휴대폰)을 Warudo, VSeeFace 등으로 보내기(실행 중인 오버레이)")
    vmc_parser.add_argument("--port", type=int, default=OVERLAY_PORT, help="오버레이 포트 (기본 %(default)s)")
    vmc_sub = vmc_parser.add_subparsers(dest="vmc_command", required=True)
    vmc_sub.add_parser("status", help="송신 상태")
    vmc_start = vmc_sub.add_parser("start", help="송신 시작(설정 저장, 다음 오버레이 실행에도 시작)")
    vmc_start.add_argument("--host", default="127.0.0.1", help="받는 프로그램의 주소(이 PC 127.0.0.1 또는 같은 네트워크 내부 주소, 기본 %(default)s)")
    vmc_start.add_argument("--vmc-port", type=int, default=39539, help="받는 포트(Warudo, VSeeFace의 VMC 수신 포트, 기본 %(default)s)")
    vmc_start.add_argument("--no-perfect-sync", action="store_true", help="ARKit 표정 52개는 보내지 않고 A, Blink, Joy만")
    vmc_start.add_argument("--mirror", action="store_true", help="좌우 반전(받는 프로그램에서 반대로 움직일 때)")
    vmc_start.add_argument("--rate", type=int, default=60, help="초당 최대 송신 횟수 10~120 (기본 %(default)s)")
    vmc_sub.add_parser("stop", help="송신 멈춤(다음 실행 때 시작하지 않음)")
    vmc_parser.set_defaults(func=_vmc)

    remote = sub.add_parser("remote", help="휴대폰 조작 화면: 같은 Wi-Fi의 휴대폰 브라우저로 참여 추첨, 3D 캐릭터 동작 조작(실행 중인 오버레이)")
    remote.add_argument("--port", type=int, default=OVERLAY_PORT, help="오버레이 포트 (기본 %(default)s)")
    remote_sub = remote.add_subparsers(dest="remote_command", required=True)
    remote_sub.add_parser("status", help="켜짐 여부, 주소, 등록 기기")
    remote_start = remote_sub.add_parser("start", help="켜기(설정 저장, 다음 오버레이 실행에도 켬)")
    remote_start.add_argument("--address", help="이 PC의 내부 네트워크 주소(기본 지난 설정, debutkit remote status로 확인)")
    remote_start.add_argument("--listen-port", type=int, help="휴대폰이 접속할 포트(기본 8792)")
    remote_sub.add_parser("stop", help="끄기(다음 실행 때 켜지 않음)")
    remote_sub.add_parser("pair", help="새 휴대폰 등록 주소(5분 유효). 휴대폰 브라우저에서 연 뒤 승인")
    for name, text in (("approve", "승인(휴대폰과 같은 확인 번호인지 확인)"), ("remove", "등록 삭제(즉시 차단)")):
        command_ = remote_sub.add_parser(name, help=text)
        command_.add_argument("id", metavar="기기")
    remote.set_defaults(func=_remote)

    from .broadcast import ENCODERS, PLATFORMS, QUALITIES

    live = sub.add_parser("broadcast", help="OBS 없이 바로 방송(Windows): 캐릭터, 채팅, 알림을 모은 송출 화면을 치지직, SOOP, YouTube, Twitch로 송출(실행 중인 오버레이)")
    live.add_argument("--port", type=int, default=OVERLAY_PORT, help="오버레이 포트 (기본 %(default)s)")
    live_sub = live.add_subparsers(dest="broadcast_command", required=True)
    live_sub.add_parser("status", help="방송 상태와 설정")
    live_sub.add_parser("devices", help="녹음 장치와 이 PC에서 되는 인코더(처음에는 몇 초 걸림)")
    live_set = live_sub.add_parser("set", help="설정 변경(지정한 항목만)")
    live_set.add_argument("--platform", choices=list(PLATFORMS), help="방송 플랫폼")
    live_set.add_argument("--server", help="송출 서버 주소(rtmp://, rtmps://). 치지직, SOOP은 방송 설정 화면에서 복사. 빈 값은 플랫폼 기본")
    live_set.add_argument("--quality", choices=list(QUALITIES), help="화질(기본 720p30)")
    live_set.add_argument("--kbps", type=int, help="영상 비트레이트(0은 자동)")
    live_set.add_argument("--encoder", choices=["auto", *ENCODERS], help="인코더(기본 auto)")
    live_set.add_argument("--mic", help="마이크(debutkit broadcast devices의 이름). 빈 값은 무음")
    live_set.add_argument("--extra-audio", help="함께 보낼 소리 장치(스테레오 믹스 등). 빈 값은 없음")
    live_set.add_argument("--camera", action=argparse.BooleanOptionalAction, default=None, help="휴대폰 앱 카메라 영상을 크게 표시")
    live_set.add_argument("--title", help="송출 화면 왼쪽 위 글자(40자 이하)")
    live_set.add_argument("--background", metavar="RRGGBB", help="송출 화면 배경색(16진수 6자리)")
    live_key = live_sub.add_parser("key", help="스트림 키 저장(입력한 글자는 표시하지 않음, 이 Windows 사용자만 풀 수 있게 암호화)")
    live_key.add_argument("--platform", choices=list(PLATFORMS), help="방송 플랫폼(기본 지금 설정)")
    live_key.add_argument("--stdin", action="store_true", help="표준 입력 첫 줄에서 읽기")
    live_key.add_argument("--clear", action="store_true", help="저장한 키 삭제")
    live_sub.add_parser("window", help="송출 화면 창 열기(방송 화면 미리보기)")
    live_sub.add_parser("start", help="방송 시작(연결될 때까지 기다림)")
    live_stop = live_sub.add_parser("stop", help="방송 끝내기")
    live_stop.add_argument("--close", action="store_true", help="송출 화면 창도 닫기")
    live.set_defaults(func=_broadcast)

    from .clipfx import POSITIONS as MARK_POSITIONS
    from .clipfx import SHORTS_MODES

    clips = sub.add_parser("clip", help="클립 다듬기: 저장한 클립이나 영상으로 움짤(GIF, WebP)과 세로 쇼츠 만들기(ffmpeg 필요). 원본 옆에 저장")
    clips_sub = clips.add_subparsers(dest="clipfx_command", required=True)
    for name, text in (("gif", "움짤 GIF(어디서나 재생)"), ("webp", "움짤 WebP(GIF보다 선명하고 작음, Pillow 필요)"),
                       ("shorts", "세로 쇼츠 MP4(1080x1920, 소리 포함)")):
        command = clips_sub.add_parser(name, help=text)
        command.add_argument("files", nargs="+", metavar="영상")
        command.add_argument("--start", type=float, metavar="초", help="시작 위치")
        command.add_argument("--duration", type=float, metavar="초", help="길이(최대 60초)")
        if name in ("gif", "webp"):
            command.add_argument("--width", type=int, default=480, help="폭 픽셀(기본 %(default)s)")
            command.add_argument("--fps", type=int, default=15, help="초당 장수(기본 %(default)s)")
        if name == "webp":
            command.add_argument("--quality", type=int, default=75, help="화질 10에서 100(기본 %(default)s)")
        if name == "shorts":
            command.add_argument("--mode", choices=list(SHORTS_MODES), default="blur",
                                 help="blur 흐린 배경(기본), crop 자르기, fit 위아래 여백")
            command.add_argument("--focus", type=float, default=0.5, help="crop일 때 가로 위치 0(왼쪽)에서 1(오른쪽). 캐릭터가 오른쪽이면 0.8 등")
        command.add_argument("--watermark", metavar="그림", help="워터마크 그림(투명 PNG 권장, debutkit logo로 만든 로고 등)")
        command.add_argument("--watermark-position", choices=list(MARK_POSITIONS), default="bottom-right", help="워터마크 위치(기본 %(default)s)")
        command.add_argument("--watermark-size", type=float, default=18.0, metavar="%", help="결과 폭에 대한 워터마크 폭(기본 %(default)s%%)")
        command.add_argument("--watermark-opacity", type=float, default=85.0, metavar="%", help="워터마크 불투명도(기본 %(default)s%%)")
        command.set_defaults(func=_clipfx)

    starts = sub.add_parser("launch", help="방송 시작 버튼: 세팅에 넣은 프로그램, 폴더, 사이트를 차례로 켜고 방해되는 프로그램은 끔. 방송 끝에 다시 켬")
    starts_sub = starts.add_subparsers(dest="launch_command")
    launch_run = starts_sub.add_parser("run", help="세팅 켜기(기본): 끌 것을 먼저 끄고 켤 것을 차례로 켬. 꺼 둔 프로그램이 다시 켜지면 알림")
    launch_run.add_argument("profile", nargs="?", metavar="세팅", help="세팅 이름(기본: launch use로 정한 세팅)")
    launch_run.add_argument("--overlay", action="store_true", help="켠 뒤 저장한 설정으로 오버레이 시작(debutkit overlay --saved)")
    launch_run.add_argument("--obs-check", action="store_true", help="켠 뒤 OBS WebSocket 연결 확인")
    launch_run.add_argument("--no-watch", action="store_true", help="켠 뒤 바로 끝내기(다시 켜짐 감시 안 함)")
    launch_end = starts_sub.add_parser("end", help="방송 끝: 이번에 꺼 둔 프로그램 다시 켜기")
    launch_end.add_argument("profile", nargs="?", metavar="세팅")
    launch_end.add_argument("--no-restore", action="store_true", help="다시 켜지 않고 기록만 지우기")
    starts_sub.add_parser("list", help="세팅과 항목 보기(* 기본 세팅)")
    launch_add = starts_sub.add_parser("add", help="켤 것(프로그램, 바로가기, 폴더, 사이트 주소) 또는 --stop 으로 끌 것 추가. 세팅이 없으면 만듦")
    launch_add.add_argument("profile", metavar="세팅")
    launch_add.add_argument("targets", nargs="+", metavar="경로나_주소")
    launch_add.add_argument("--stop", action="store_true", help="끌 것(프로그램 이름 예: Discord.exe, KakaoTalk.exe)으로 추가")
    launch_add.add_argument("--delay", type=float, default=2.0, metavar="초", help="켠 뒤 다음 항목까지 기다리는 시간(기본 %(default)s초, 무거운 프로그램은 넉넉하게)")
    launch_add.add_argument("--args", metavar="옵션", help="프로그램 실행 옵션")
    launch_add.add_argument("--name", metavar="이름", help="표시 이름")
    launch_remove = starts_sub.add_parser("remove", help="켤 것, 끌 것 지우기(경로, 주소, 표시 이름, 프로그램 이름)")
    launch_remove.add_argument("profile", metavar="세팅")
    launch_remove.add_argument("targets", nargs="+", metavar="항목")
    launch_set = starts_sub.add_parser("set", help="세팅 옵션 바꾸기(지정한 항목만)")
    launch_set.add_argument("profile", metavar="세팅")
    launch_set.add_argument("--skip-running", action=argparse.BooleanOptionalAction, default=None, help="이미 켜진 프로그램은 건너뛰기(기본 켬)")
    launch_set.add_argument("--place-running", action=argparse.BooleanOptionalAction, default=None, help="이미 켜진 프로그램 창도 기억한 자리로 옮기기")
    launch_set.add_argument("--watch", action=argparse.BooleanOptionalAction, default=None, help="꺼 둔 프로그램이 다시 켜지면 알림(기본 켬)")
    launch_set.add_argument("--rekill", action=argparse.BooleanOptionalAction, default=None, help="다시 켜지면 다시 끄기")
    launch_set.add_argument("--restore", action=argparse.BooleanOptionalAction, default=None, help="방송 끝에 꺼 둔 프로그램 다시 켜기(기본 켬)")
    launch_set.add_argument("--overlay", action=argparse.BooleanOptionalAction, default=None, help="켠 뒤 오버레이 시작")
    launch_set.add_argument("--obs-check", action=argparse.BooleanOptionalAction, default=None, help="켠 뒤 OBS 연결 확인")
    launch_set.add_argument("--rename", metavar="새_이름", help="세팅 이름 바꾸기")
    launch_set.add_argument("--use", action="store_true", help="기본 세팅으로 정하기")
    launch_copy = starts_sub.add_parser("copy", help="세팅 복제(창 위치 포함)")
    launch_copy.add_argument("profile", metavar="세팅")
    launch_copy.add_argument("new_name", metavar="새_이름")
    starts_sub.add_parser("delete", help="세팅 삭제").add_argument("profile", metavar="세팅")
    starts_sub.add_parser("use", help="기본 세팅 정하기").add_argument("profile", metavar="세팅")
    launch_protect = starts_sub.add_parser("protect", help="끄지 않을 프로그램(보호 목록) 추가, --remove 로 빼기")
    launch_protect.add_argument("names", nargs="*", metavar="프로그램")
    launch_protect.add_argument("--remove", action="store_true")
    starts_sub.add_parser("remember", help="지금 켜진 창의 자리와 크기 기억(Windows, 듀얼 모니터 포함)").add_argument("profile", nargs="?", metavar="세팅")
    starts_sub.add_parser("watch", help="꺼 둔 프로그램이 다시 켜지는지 감시(Ctrl+C까지)").add_argument("profile", nargs="?", metavar="세팅")
    starts_sub.add_parser("export", help="설정 백업 파일 저장(다른 PC로 옮기기)").add_argument("file", metavar="파일")
    starts_sub.add_parser("import", help="백업 파일 불러오기(지금 설정을 바꿈)").add_argument("file", metavar="파일")
    starts.set_defaults(func=_launch)

    from .logo import FONTS, LAYOUTS, STYLES, TEMPLATES
    from .logo import PROVIDERS as LOGO_PROVIDERS
    from .logo import QUALITIES as LOGO_QUALITIES
    from .logo_icons import COLOR_MODES, FINISHES

    PHOSPHOR_WEIGHTS = ("thin", "light", "regular", "bold", "fill", "duotone")

    logos = sub.add_parser("logo", help="방송 로고 만들기: 아이콘, 기본 도형 또는 생성형 AI 심볼과 채널 이름(글꼴 윤곽선)으로 SVG 로고")
    logos_sub = logos.add_subparsers(dest="logo_command", required=True)
    logo_make = logos_sub.add_parser("make", help="로고 SVG 만들기(아이콘과 기본 도형은 무료, --ai aihorde는 계정 없이 무료, 나머지는 본인 키)")
    logo_make.add_argument("--name", help="채널 이름(30자 이하)")
    logo_make.add_argument("--icon", metavar="아이콘", help="함께 배포한 아이콘(예: fluent/cat-face, phosphor/microphone. debutkit logo icons로 검색)")
    logo_make.add_argument("--icon-style", default="auto", choices=["auto", "flat", "mono", *PHOSPHOR_WEIGHTS],
                           help="아이콘 종류: Fluent는 flat(컬러), mono(단색), Phosphor는 굵기. auto는 컬러 또는 글꼴에 맞춘 굵기(기본 %(default)s)")
    logo_make.add_argument("--icon-colors", default="channel", choices=list(COLOR_MODES), help="컬러 아이콘 색: channel(주 색, 보조 색으로 다시 칠함), "
                           "original(원래 색)(기본 %(default)s)")
    logo_make.add_argument("--template", choices=list(TEMPLATES), default="star", help="기본 도형(--icon, --ai가 없을 때, 기본 %(default)s)")
    logo_make.add_argument("--ai", choices=list(LOGO_PROVIDERS),
                           help="생성형 AI로 심볼 만들기(--describe 필요). aihorde는 계정 없이 FLUX.1 schnell, comfyui와 huggingface는 Qwen-Image")
    logo_make.add_argument("--comfyui", metavar="주소", help="--ai comfyui의 ComfyUI 주소(기본 http://127.0.0.1:8188)")
    logo_make.add_argument("--describe", help="AI 심볼 설명(글자 없이 그림으로, 300자 이하)")
    logo_make.add_argument("--style", choices=list(STYLES), default="cute", help="AI 심볼 느낌(기본 %(default)s)")
    logo_make.add_argument("--quality", choices=list(LOGO_QUALITIES), default="fast", help="AI 품질(기본 %(default)s)")
    logo_make.add_argument("--color", action="append", metavar="RRGGBB", help="주 색, 보조 색(2번까지 지정)")
    logo_make.add_argument("--finish", choices=list(FINISHES), default="none",
                           help="심볼 마감: outline(외곽선), bold(굵은 외곽선), sticker(외곽선과 흰 테두리), white(흰 테두리)(기본 %(default)s)")
    logo_make.add_argument("--font", choices=list(FONTS), default="pretendard", help="채널 이름 글꼴(기본 %(default)s)")
    logo_make.add_argument("--layout", choices=list(LAYOUTS), default="horizontal", help="배치(기본 %(default)s)")
    logo_make.add_argument("--text-color", default="#1E2327", help="글자 색(기본 %(default)s)")
    logo_make.add_argument("--background", metavar="RRGGBB", help="배경색(기본 투명)")
    logo_make.add_argument("--out", required=True, metavar="파일", help="저장할 SVG 파일")
    logo_icons = logos_sub.add_parser("icons", help="함께 배포한 아이콘 검색(한국어나 영어 검색어, 없으면 전체)")
    logo_icons.add_argument("words", nargs="*", metavar="검색어")
    logo_icons.add_argument("--limit", type=int, default=60, help="최대 개수(기본 %(default)s)")
    logo_key = logos_sub.add_parser("key", help="생성형 AI API 키, Hugging Face 토큰, AI Horde 등록 키 저장(입력한 글자는 표시하지 않음)")
    logo_key.add_argument("provider", choices=[key for key, item in LOGO_PROVIDERS.items() if item.needs_key or item.optional_key])
    logo_key.add_argument("--stdin", action="store_true", help="표준 입력 첫 줄에서 읽기")
    logo_key.add_argument("--clear", action="store_true", help="저장한 키 삭제")
    logos_sub.add_parser("list", help="기본 도형과 최근 AI 심볼")
    logos.set_defaults(func=_logo)

    motions = sub.add_parser("motion", help="3D 캐릭터 동작 등록, 기본 동작, 실행(VRMA, Mixamo 등의 FBX, GLB)")
    motions_sub = motions.add_subparsers(dest="motion_command", required=True)
    motions_sub.add_parser("list", help="등록한 동작 목록(* 기본 동작)")
    motion_add = motions_sub.add_parser("add", help="동작 등록: VRMA, 사람 모양 뼈가 있는 FBX, GLB 또는 이 파일들을 담은 zip, 폴더")
    motion_add.add_argument("path", metavar="경로")
    motion_add.add_argument("--name", help="표시할 이름(파일 하나일 때)")
    motion_add.add_argument("--clip", metavar="동작 이름", help="파일 안에 동작이 여러 개일 때 사용할 동작(기본: 첫 동작)")
    for command, text in (("show", "사용 조건, 확인 필요 사항 보기"), ("remove", "등록 삭제")):
        motions_sub.add_parser(command, help=text).add_argument("id", metavar="동작")
    motion_idle = motions_sub.add_parser("idle", help="기본 동작(대기 중 반복) 지정. 동작을 생략하면 현재 기본 동작 표시")
    motion_idle.add_argument("id", nargs="?", metavar="동작")
    motion_idle.add_argument("--off", action="store_true", help="기본 동작 해제")
    motion_play = motions_sub.add_parser("play", help="실행 중인 캐릭터 화면에서 동작 한 번 실행")
    motion_play.add_argument("id", nargs="?", metavar="동작")
    motion_play.add_argument("--stop", action="store_true", help="실행 중인 동작 멈춤")
    motion_play.add_argument("--port", type=int, default=OVERLAY_PORT, help="오버레이 포트 (기본 %(default)s)")
    motions.set_defaults(func=_motion)

    vts_parser = sub.add_parser("vts", help="VTube Studio 연동: 연결, 모델 불러오기, 단축키 실행")
    vts_parser.add_argument("--url", default="ws://127.0.0.1:8001", help="VTube Studio API 주소 (기본 %(default)s)")
    vts_sub = vts_parser.add_subparsers(dest="vts_command", required=True)
    vts_sub.add_parser("login", help="연결(VTube Studio 화면에서 허용)")
    vts_sub.add_parser("logout", help="저장한 토큰 삭제")
    vts_sub.add_parser("models", help="모델 목록(* 현재 모델)")
    vts_sub.add_parser("load", help="모델 불러오기(이름 일부 또는 ID)").add_argument("name", metavar="모델")
    vts_sub.add_parser("hotkeys", help="현재 모델의 단축키 목록")
    vts_sub.add_parser("trigger", help="단축키 실행(이름 또는 ID)").add_argument("name", metavar="단축키")
    vts_parser.set_defaults(func=_vts)

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
