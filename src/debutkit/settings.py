"""설정 저장: 방송마다 같은 값을 다시 입력하지 않도록 이 PC에 보관한다.

- 위치: Windows ``%APPDATA%\\debutkit\\settings.json``, macOS ``~/Library/Application Support/debutkit/settings.json``,
  Linux ``$XDG_CONFIG_HOME/debutkit/settings.json``(기본 ``~/.config``). 환경 변수 ``DEBUTKIT_SETTINGS`` 로 변경
- 저장 항목: 채널 주소, 수신 방식, 포트, 선택 항목. API 키, 비밀번호, Client Secret, 토큰은 저장하지 않는다
- 파일이 손상되었거나 모르는 항목, 형식이 다른 값은 무시하고 기본값으로 시작한다
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

VERSION = 1

#: 저장하는 항목과 형식. list는 문자열 목록
FIELDS: dict[str, type] = {
    "chzzk": list,
    "soop": list,
    "twitch": list,
    "youtube": list,
    "chzzk_api": bool,
    "chzzk_client_id": str,
    "youtube_mode": str,
    "youtube_interval": float,
    "demo": bool,
    "clip": bool,
    "clip_dir": str,
    "overlay_port": int,
    "obs_port": int,
    "avatar_app": str,
    "replay_buffer": int,
    "avatar_path": str,
    "agency": bool,
    "character": str,
    "voice_input": str,
    "voice_threshold": float,
    "vts_reactions": list,  # VTube Studio 후원 반응 "최소 금액:단축키" (토큰은 따로 보관)
    "idle_motion": str,  # 3D 캐릭터의 기본 동작(대기 중 반복)
    "motion_reactions": list,  # 후원 반응 동작 "최소 금액:동작"
    "draw_enabled": bool,  # 후원 추첨 연출(draw.py)
    "draw_prizes": list,  # "가중치:상품"
    "draw_rules": list,  # "최소 금액:횟수"
    "draw_exact": bool,
    "draw_members": bool,
    "draw_style": str,
    "draw_seconds": int,
    "draw_title": str,
    "draw_position": str,
    "draw_scale": int,
    "draw_sound": bool,
    "draw_show_percent": bool,
    "draw_design": str,  # 연출별 모양
    "draw_effect": str,  # 결과 뒤 효과
    "draw_name_font": str,  # 상품 이름 글꼴, 크기
    "draw_name_size": str,
    "draw_caption_font": str,  # 안내 글(하단 띠, 한마디) 글꼴, 크기
    "draw_caption_size": str,
    "draw_advice": bool,  # 타로 오늘의 한마디
    "draw_advice_lines": list,
    "chat_commands": bool,  # 스트리머, 매니저 채팅 명령(commands.py)
    "raffle_command": str,  # 시청자 참여 추첨 참가 명령
    "raffle_title": str,
    "raffle_donation_min": int,
    "phone_enabled": bool,  # 휴대폰 얼굴 추적 수신(overlay/phone.py): 오버레이 시작 때 함께 시작
    "phone_app": str,  # ifacialmocap, vts
    "phone_ip": str,  # 같은 Wi-Fi의 휴대폰 주소
    "phone_mirror": bool,
    "phone_flip_pitch": bool,
    "phone_center_yaw": float,  # 정면 맞추기(라디안)
    "phone_center_pitch": float,
    "phone_center_roll": float,
    "remote_enabled": bool,  # 휴대폰 조작 화면(overlay/remote.py): 오버레이 시작 때 함께 켬. 기기 비밀값은 remote-devices.json
    "remote_address": str,  # 이 PC의 내부 네트워크 주소(휴대폰이 접속하는 곳)
    "remote_port": int,
}

#: 이 단어가 들어간 항목은 저장하지 않는다(실수로 FIELDS에 추가해도 막음)
SECRET_WORDS = ("key", "password", "secret", "token")


def settings_path() -> Path:
    override = os.environ.get("DEBUTKIT_SETTINGS")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "debutkit" / "settings.json"


def _valid(name: str, value: Any) -> Any:
    """형식이 맞으면 정리한 값, 아니면 None."""
    kind = FIELDS.get(name)
    if kind is None or any(word in name for word in SECRET_WORDS):
        return None
    if kind is list:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return None
        items = [str(item).strip() for item in value if isinstance(item, str) and str(item).strip()]
        return items
    if kind is bool:
        return value if isinstance(value, bool) else None
    if kind is int:
        return value if isinstance(value, int) and not isinstance(value, bool) else None
    if kind is float:
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    return value.strip() if isinstance(value, str) else None


def clean(values: dict[str, Any]) -> dict[str, Any]:
    """저장 가능한 항목만 남긴다. 빈 문자열, 빈 목록은 뺀다."""
    found = {}
    for name, value in values.items():
        checked = _valid(name, value)
        if checked is not None and checked != "" and checked != []:
            found[name] = checked
    return found


def load(path: Path | None = None) -> dict[str, Any]:
    path = path or settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or not isinstance(data.get("settings"), dict):
        return {}
    return clean(data["settings"])


def save(values: dict[str, Any], path: Path | None = None) -> Path:
    """저장 가능한 항목만 기록. 다른 프로그램이 읽는 도중에도 깨지지 않도록 임시 파일에 쓴 뒤 바꾼다."""
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps({"version": VERSION, "settings": clean(values)}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
    return path


def data_path(name: str) -> Path:
    """설정 파일과 같은 폴더의 기능별 파일(예: ``pick.json``). 뽑기판, 후원 벽처럼 구조가 있는 설정과 기록."""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(f"잘못된 파일 이름: {name}")
    return settings_path().parent / name


def load_data(name: str) -> dict[str, Any]:
    """기능별 파일 읽기. 없거나 손상되었으면 빈 값(기능이 기본값으로 시작)."""
    try:
        data = json.loads(data_path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_data(name: str, values: dict[str, Any]) -> Path:
    """기능별 파일 쓰기(임시 파일에 쓴 뒤 바꿔 중간에 깨지지 않게). API 키, 비밀번호는 넣지 않는다."""
    path = data_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
    return path


def clear(path: Path | None = None) -> Path | None:
    """저장한 설정 삭제. 지운 파일 경로, 없으면 None."""
    path = path or settings_path()
    if not path.is_file():
        return None
    path.unlink()
    return path
