"""오류 기록: 이 PC의 기록 폴더에만, 상태 안내만, 처리되지 않은 오류 포함."""

import logging
import logging.handlers
import sys
import threading

import pytest

from debutkit import logs
from debutkit.overlay.events import OverlayEvent, system_event


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")  # 일부러 낸 작업 스레드 오류
def test_status_and_uncaught_errors_are_written_locally(tmp_path, monkeypatch):
    monkeypatch.setenv("DEBUTKIT_SETTINGS", str(tmp_path / "settings.json"))
    previous = sys.excepthook, threading.excepthook
    handler = logs.setup("test")
    try:
        assert handler is not None and logs.log_dir() == tmp_path / "logs"
        logs.status(system_event("클립 저장: live_1.mp4"))
        logs.status(OverlayEvent(platform="chzzk", kind="chat", name="시청자", parts=(("text", "비밀 채팅 내용"),)))
        thread = threading.Thread(target=lambda: 1 / 0, name="worker")
        thread.start()
        thread.join()
    finally:
        logs.close(handler)
        sys.excepthook, threading.excepthook = previous
    text = (tmp_path / "logs" / "test.log").read_text(encoding="utf-8")
    assert "시작(" in text and "상태: 클립 저장: live_1.mp4" in text
    assert "비밀 채팅 내용" not in text and "시청자" not in text  # 채팅은 기록하지 않음
    assert "작업 스레드(worker)의 처리되지 않은 오류" in text and "ZeroDivisionError" in text
    assert not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in logging.getLogger(logs.LOGGER).handlers)


def test_unwritable_folder_does_not_stop_the_program(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("DEBUTKIT_SETTINGS", str(blocker / "settings.json"))  # 폴더 자리에 파일이 있어 만들 수 없음
    assert logs.setup("test") is None
