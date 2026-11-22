"""오류 기록: 문제 제보에 첨부할 수 있도록 이 PC에만 기록한다(외부 전송 없음).

- 위치: 저장 설정과 같은 폴더의 ``logs`` (예: Windows ``%APPDATA%\\debutkit\\logs``)
- 기록 내용: 처리되지 않은 오류, 연결 상태와 클립 저장 같은 상태 안내. 채팅 내용, API 키, 비밀번호는 기록하지 않는다
- 파일당 최대 1 MB, 최근 3개 파일만 보관
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
from pathlib import Path
from typing import Any

from . import __version__, settings

LOGGER = "debutkit"
MAX_BYTES = 1024 * 1024
BACKUPS = 2


def log_dir() -> Path:
    return settings.settings_path().parent / "logs"


def setup(name: str) -> logging.Handler | None:
    """``logs/이름.log`` 에 기록 시작. 폴더를 만들 수 없으면 기록하지 않는다(프로그램은 계속 실행)."""
    try:
        folder = log_dir()
        folder.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.handlers.RotatingFileHandler(folder / f"{name}.log", maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
    except OSError:
        return None
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger = logging.getLogger(LOGGER)
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.info("debutkit %s 시작(%s, Python %s)", __version__, sys.platform, sys.version.split()[0])
    _install_hooks()
    return handler


def close(handler: logging.Handler | None) -> None:
    if handler is not None:
        logging.getLogger(LOGGER).removeHandler(handler)
        handler.close()


_previous_hook = sys.excepthook
_previous_thread_hook = threading.excepthook


def _excepthook(kind: type[BaseException], value: BaseException, trace: Any) -> None:
    if not issubclass(kind, KeyboardInterrupt):
        logging.getLogger(LOGGER).error("처리되지 않은 오류", exc_info=(kind, value, trace))
    _previous_hook(kind, value, trace)


def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
    if args.exc_type is not SystemExit:
        name = args.thread.name if args.thread else "?"
        logging.getLogger(LOGGER).error("작업 스레드(%s)의 처리되지 않은 오류", name, exc_info=(args.exc_type, args.exc_value, args.exc_traceback))  # type: ignore[arg-type]
    _previous_thread_hook(args)


def _install_hooks() -> None:
    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook


def status(event: Any) -> None:
    """오버레이 허브에 붙이는 수신기: 상태 안내(system)만 기록하고 채팅, 후원 내용은 기록하지 않는다."""
    if getattr(event, "kind", "") == "system":
        logging.getLogger(LOGGER).info("상태: %s", getattr(event, "text", ""))
