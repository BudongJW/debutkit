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
    with pytest.raises(RuntimeError, match="내려받기 미지원"):
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
