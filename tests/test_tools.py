import pytest

from debutkit import tools


def test_install_hint_per_system():
    assert "debutkit setup --ffmpeg" in tools.install_hint("win32")
    assert "brew install ffmpeg" in tools.install_hint("darwin")
    assert "apt" in tools.install_hint("linux")
    assert tools.can_download_ffmpeg("win32") and not tools.can_download_ffmpeg("darwin")


def test_progress_printer_writes_every_step():
    lines = []
    progress = tools.progress_printer(100, step=25, write=lines.append)
    for done in range(0, 101, 5):
        progress(done * 1_000_000, 100_000_000)
    assert [line.split("%")[0].strip() for line in lines] == ["0", "25", "50", "75", "100"]


def test_download_refused_off_windows(monkeypatch):
    monkeypatch.setattr(tools.sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="다운로드 미지원"):
        tools.download_ffmpeg()


def test_ffmpeg_path_uses_the_download_folder(monkeypatch, tmp_path):
    pytest.importorskip("stream2clip.ffmpeg")
    for name in ("STREAM2CLIP_FFMPEG", "STREAM2CLIP_FFPROBE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("STREAM2CLIP_TOOLS_DIR", str(tmp_path))
    monkeypatch.setenv("PATH", "")
    assert tools.ffmpeg_path() is None
    suffix = ".exe" if tools.sys.platform == "win32" else ""
    (tmp_path / f"ffmpeg{suffix}").write_bytes(b"")
    assert tools.ffmpeg_path() is None  # ffprobe도 있어야 한다
    (tmp_path / f"ffprobe{suffix}").write_bytes(b"")
    assert tools.ffmpeg_path() == str(tmp_path / f"ffmpeg{suffix}")


class _Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


def test_version_compare():
    assert tools.is_newer("v0.3.1", "0.3.0") and tools.is_newer("0.10.0", "0.9.9")
    assert not tools.is_newer("0.3.0", "0.3.0") and not tools.is_newer("v0.2.0", "0.3.0")


def test_update_message_from_latest_release():
    seen = []

    def opener(request, timeout):
        seen.append(request.full_url)
        return _Response(b'{"tag_name": "v0.4.0"}')

    message = tools.update_message("0.3.0", opener)
    assert message.startswith("새 버전 0.4.0 있음") and tools.RELEASES_PAGE in message
    assert seen == [tools.LATEST_RELEASE_API]
    assert tools.update_message("0.4.0", opener) == "최신 버전 사용 중 (0.4.0)"


def test_update_message_reports_failure():
    def opener(request, timeout):
        raise OSError("연결 거부")

    assert tools.update_message("0.3.0", opener) == "새 버전 확인 실패: 연결 거부"
