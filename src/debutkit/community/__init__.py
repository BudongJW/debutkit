"""debutkit 커뮤니티: 스트리머마다 자기 팬 커뮤니티(트게더처럼 공지, 방송 일정, 게시판, 출석과 포인트)를 갖게 한다.

- 커뮤니티 사이트는 ``worker/worker.js`` (Cloudflare Worker 하나)이며 스트리머 본인의 Cloudflare 무료 계정에 올린다(D1, KV).
  debutkit 팀은 서버를 운영하지 않는다. 운영자(개인정보 처리, 게시물 신고 처리)는 스트리머
- 올리기와 고치기는 Cloudflare REST API(``cloudflare.py``), 커뮤니티와 debutkit 사이는 API 토큰(``client.py``)
- 설정은 설정 폴더의 ``community.json`` (주소, 계정, 자동 연동), 토큰과 비밀값은 ``community-keys.json`` (Windows DPAPI 등, secret.KeyBox)
- 방송 중 연동(overlay/community.py): 채팅 ``!인증 숫자`` 로 가입과 계정 연결, ``!출석`` 포인트, 방송 중 표시, 참여 추첨 참가, 방송에 띄우기
"""

from __future__ import annotations

from typing import Any

from .. import settings
from ..secret import KeyBox

DATA = "community.json"
KEYS = "community-keys.json"
AUTO = {"verify": True, "attend": True, "live": True, "raffle": True, "stage": True}
DEFAULTS: dict[str, Any] = {"url": "", "account": "", "script": "", "database": "", "kv": "", "subdomain": "", "name": "", "providers": [],
                            "live_url": "", "stage_seconds": 12, "auto": dict(AUTO), "deployed_at": 0, "provider_ids": {}, "sync": False,
                            "schedule": []}
#: 플랫폼 로그인(선택). 각 서비스 개발자 화면에서 앱을 만들고 돌아올 주소를 ``커뮤니티 주소/auth/이름/callback`` 으로 등록
PROVIDERS = {"chzzk": "치지직", "discord": "디스코드", "google": "구글(YouTube)"}


def keys() -> KeyBox:
    return KeyBox(settings.data_path(KEYS), b"debutkit-community", "debutkit-community")


def load() -> dict[str, Any]:
    saved = settings.load_data(DATA)
    config = {**DEFAULTS, **{key: value for key, value in saved.items() if key in DEFAULTS}}
    config["auto"] = {**AUTO, **{key: bool(value) for key, value in (saved.get("auto") or {}).items() if key in AUTO}}
    config["providers"] = [key for key in saved.get("providers") or [] if key in PROVIDERS]
    ids = saved.get("provider_ids") if isinstance(saved.get("provider_ids"), dict) else {}
    config["provider_ids"] = {key: str(value) for key, value in ids.items() if key in PROVIDERS and value}  # 로그인 앱 Client ID(비밀 아님)
    config["sync"] = bool(saved.get("sync"))
    config["schedule"] = [item for item in saved.get("schedule") or [] if isinstance(item, dict)][:60]  # 마지막으로 올린 일정(편집 화면용)
    try:
        config["stage_seconds"] = max(4, min(60, int(config["stage_seconds"])))
    except (TypeError, ValueError):
        config["stage_seconds"] = DEFAULTS["stage_seconds"]
    return config


def save(config: dict[str, Any]) -> None:
    settings.save_data(DATA, {key: config[key] for key in DEFAULTS})


def connect(config: dict[str, Any] | None = None, box: KeyBox | None = None) -> Any:
    """올린 커뮤니티의 API(없으면 None)."""
    from .client import Community

    config = config or load()
    token = (box or keys()).load("admin_token")
    return Community(config["url"], token) if config["url"] and token else None
