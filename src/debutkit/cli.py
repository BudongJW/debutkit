"""명령줄: debutkit gui | doctor | scenes | overlay | draw | raffle | character | motion | vts | settings | setup | chzzk"""

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


#: overlay 옵션과 저장 설정 항목의 대응(API 키, 비밀번호는 저장하지 않음)
OVERLAY_SETTINGS = {"chzzk": "chzzk", "chzzk_api": "chzzk_api", "soop": "soop", "twitch": "twitch", "youtube": "youtube",
                    "youtube_mode": "youtube_mode", "youtube_interval": "youtube_interval", "demo": "demo", "port": "overlay_port",
                    "clip": "clip", "clip_dir": "clip_dir", "obs_port": "obs_port", "voice_input": "voice_input", "voice_threshold": "voice_threshold",
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


def _get_overlay(port: int, path: str, describe: Callable[[dict[str, Any]], str]) -> int:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
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
