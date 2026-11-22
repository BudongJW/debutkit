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


def clear(path: Path | None = None) -> Path | None:
    """저장한 설정 삭제. 지운 파일 경로, 없으면 None."""
    path = path or settings_path()
    if not path.is_file():
        return None
    path.unlink()
    return path
