"""커뮤니티 올리기와 고치기: 토큰과 비밀값을 준비해 Cloudflare에 올리고, 설정(이름, 방송 색, 로그인 방법)을 커뮤니티에 보낸다."""

from __future__ import annotations

import hashlib
import secrets
import time
from typing import Any, Callable

from . import PROVIDERS, connect, keys, load, save
from .cloudflare import Cloudflare, CloudflareError, check_script, deploy


def redirect_uris(url: str) -> dict[str, str]:
    """플랫폼 로그인 앱에 등록할 돌아올 주소."""
    return {key: f"{url.rstrip('/')}/auth/{key}/callback" for key in PROVIDERS} if url else {}


def publish(script: str, *, cloudflare_token: str = "", account: str = "", name: str = "", owner_name: str = "",
            providers: dict[str, dict[str, str]] | None = None, box: Any = None, make_cloudflare: Callable[[str], Any] = Cloudflare) -> dict[str, Any]:
    """처음 올리기와 다시 올리기. ``providers`` 는 {"discord": {"id": ..., "secret": ...}} (비우면 저장한 값, id를 ""로 주면 끔)."""
    box = box or keys()
    config = load()
    token = (cloudflare_token or "").strip() or box.load("cloudflare_token") or ""
    if not token:
        raise CloudflareError("Cloudflare API 토큰 필요: Cloudflare 대시보드에서 만든 토큰을 붙여 넣기")
    script = check_script(script or config["script"])
    admin = box.load("admin_token") or secrets.token_urlsafe(32)
    session = box.load("session_key") or secrets.token_urlsafe(32)
    values = {"ADMIN_TOKEN_HASH": hashlib.sha256(admin.encode("utf-8")).hexdigest(), "SESSION_KEY": session}
    enabled = []
    saved_ids = dict(config.get("provider_ids") or {}) if isinstance(config.get("provider_ids"), dict) else {}
    for key in PROVIDERS:
        given = (providers or {}).get(key)
        client_id = (given or {}).get("id", None)
        client_id = saved_ids.get(key, "") if client_id is None else str(client_id).strip()
        secret = str((given or {}).get("secret") or "").strip() or (box.load(f"{key}_secret") or "")
        if client_id and secret:
            values[f"{key.upper()}_CLIENT_ID"] = client_id
            values[f"{key.upper()}_CLIENT_SECRET"] = secret
            saved_ids[key] = client_id
            box.save(f"{key}_secret", secret)
            enabled.append(key)
        else:
            saved_ids.pop(key, None)
    deployed = deploy(make_cloudflare(token), script, account=account.strip() or config["account"], secrets_=values,
                      subdomain_hint=config["subdomain"] or script)
    box.save("cloudflare_token", token)
    box.save("admin_token", admin)
    box.save("session_key", session)
    config.update(url=deployed.url, account=deployed.account, script=deployed.script, database=deployed.database, kv=deployed.kv,
                  subdomain=deployed.subdomain, providers=enabled, deployed_at=int(time.time()), name=name.strip() or config["name"])
    config["provider_ids"] = saved_ids
    config["sync"] = True
    save(config)
    note = sync_settings(config, owner_name=owner_name, box=box)
    return {**load(), "note": note}


def sync_settings(config: dict[str, Any] | None = None, *, owner_name: str = "", box: Any = None) -> str:
    """이름, 방송 색, 로그인 방법을 커뮤니티에 보낸다. 막 올린 주소가 아직 열리지 않았으면 다음에 다시(방송 중 연동이 보냄)."""
    from ..overlay import theme
    from .client import CommunityError

    config = config or load()
    api = connect(config, box)
    if api is None:
        return "커뮤니티를 아직 올리지 않음"
    current = theme.load()
    values: dict[str, Any] = {"theme": {"primary": current["primary"], "highlight": current["highlight"]}, "providers": ",".join(config["providers"])}
    if config["name"]:
        values["name"] = config["name"]
    if owner_name.strip():
        values["owner_name"] = owner_name.strip()
    try:
        api.settings(**values)
    except CommunityError as error:
        return f"올렸지만 아직 연결되지 않음(새 주소는 열리기까지 몇 분 걸릴 수 있음): {error}"
    config["sync"] = False
    save(config)
    return ""
