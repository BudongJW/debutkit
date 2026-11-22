"""치지직 공식 Open API 로그인: 내 채널의 채팅, 후원, 구독을 오버레이로 받기 위한 한 번의 동의.

치지직 개발자 센터에 등록한 애플리케이션의 Client ID와 Client Secret이 필요하다. 둘 다
``CHZZK_CLIENT_ID``, ``CHZZK_CLIENT_SECRET`` 환경 변수로 주거나 함수 인자로 준다. 로그인하면
브라우저에서 치지직 동의 화면이 열리고, 이 PC의 로컬 주소로 돌아온 인증 코드로 토큰을
발급받아 사용자 설정 폴더에 보관한다. 토큰은 만료되면 자동으로 갱신된다.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

DEFAULT_REDIRECT = "http://localhost:8765/callback"

_MESSAGES = {
    "client id and secret": "치지직 애플리케이션 Client ID와 Client Secret 필요: CHZZK_CLIENT_ID, CHZZK_CLIENT_SECRET 환경 변수 또는 입력란 사용",
    "must be a local address": "로그인 돌아올 주소는 이 PC 주소여야 함 (예: http://localhost:8765/callback, 개발자 센터 등록 주소와 동일)",
    "No answer from CHZZK": "제한 시간 안에 치지직 로그인 응답 없음. 다시 시도 필요",
    "gave no access token": "치지직이 접근 토큰을 주지 않음. 애플리케이션 설정 확인",
}


class ChzzkLoginError(RuntimeError):
    pass


def _korean(error: Exception) -> str:
    message = str(error)
    for needle, korean in _MESSAGES.items():
        if needle in message:
            return korean
    return message


def make_api(client_id: str | None, client_secret: str | None) -> Any:
    try:
        from stream2clip.chzzk_api import ChzzkApi, ChzzkApiError
    except ImportError as error:
        raise ChzzkLoginError('치지직 로그인에는 채팅 연결 모듈 필요: pip install "debutkit[live]"') from error
    try:
        return ChzzkApi(client_id or None, client_secret or None)
    except ChzzkApiError as error:
        raise ChzzkLoginError(_korean(error)) from error


def use_credentials(client_id: str, client_secret: str) -> None:
    """이 프로그램이 실행되는 동안만 쓸 Client ID와 Secret. 파일에 저장하지 않는다."""
    if client_id:
        os.environ["CHZZK_CLIENT_ID"] = client_id
    if client_secret:
        os.environ["CHZZK_CLIENT_SECRET"] = client_secret


def login(client_id: str | None = None, client_secret: str | None = None, redirect: str = DEFAULT_REDIRECT, *,
          open_browser: Callable[[str], Any] | None = None, on_url: Callable[[str], None] | None = None, timeout: float = 300.0) -> Path:
    """브라우저 동의로 토큰을 받아 저장하고, 저장한 파일 경로를 돌려준다."""
    api = make_api(client_id, client_secret)
    from stream2clip.chzzk_api import ChzzkApiError
    from stream2clip.chzzk_api import login as api_login

    try:
        api_login(api, redirect, open_browser=open_browser, on_url=on_url, timeout=timeout)
    except ChzzkApiError as error:
        raise ChzzkLoginError(_korean(error)) from error
    except OSError as error:  # 돌아올 주소의 포트를 다른 프로그램이 사용
        raise ChzzkLoginError(f"로그인 응답을 받을 주소를 열지 못함 ({redirect}): {error}") from error
    return Path(api.token_file)


def token_file() -> Path | None:
    try:
        from stream2clip.chzzk_api import token_path
    except ImportError:
        return None
    return token_path()


def signed_in() -> bool:
    path = token_file()
    return bool(path and path.is_file())


def logout() -> Path | None:
    """보관한 토큰을 지운다. 지운 파일 경로, 로그인 상태가 아니면 ``None``."""
    path = token_file()
    if path is None or not path.is_file():
        return None
    path.unlink()
    return path
