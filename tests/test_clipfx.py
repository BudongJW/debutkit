import subprocess
from pathlib import Path

import pytest

from debutkit import clipfx
from debutkit.clipfx import ClipFxError, Info, Watermark


def mark(tmp_path):
    path = tmp_path / "logo.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    return path


def test_gif_command_uses_palette_range_and_watermark(tmp_path):
    info = Info(20.0, 1920, 1080, True)
    command = clipfx.gif_command("ffmpeg", Path("a.mp4"), Path("a.gif"), start=2, duration=4, width=481, fps=12,
                                 watermark=Watermark(mark(tmp_path), "top-left", 0.2, 0.5), info=info)
    assert command[:7] == ["ffmpeg", "-hide_banner", "-y", "-ss", "2.000", "-t", "4.000"] and command.count("-i") == 2
    graph = command[command.index("-filter_complex") + 1]
    assert "fps=12,scale=480:-2" in graph and "palettegen" in graph and "paletteuse" in graph
    assert "scale=96:-1" in graph and "aa=0.50" in graph and "overlay=14:14" in graph
    assert command[-3:] == ["0", "-an", "a.gif"]
    with pytest.raises(ClipFxError, match="폭"):
        clipfx.gif_command("ffmpeg", Path("a"), Path("b"), width=50)
    with pytest.raises(ClipFxError, match="길이"):
        clipfx.gif_command("ffmpeg", Path("a"), Path("b"), duration=120)
    with pytest.raises(ClipFxError, match="영상 길이"):
        clipfx.gif_command("ffmpeg", Path("a"), Path("b"), start=30, info=info)


@pytest.mark.parametrize("mode, marker", [("blur", "gblur"), ("crop", "crop=1080:1920:(iw-1080)*0.800:0"), ("fit", "pad=1080:1920")])
def test_shorts_modes(mode, marker):
    command = clipfx.shorts_command("ffmpeg", Path("a.mp4"), Path("a-shorts.mp4"), mode=mode, focus=0.8, info=Info(10, 1920, 1080, False))
    graph = command[command.index("-filter_complex") + 1]
    assert marker in graph and "0:a?" not in command and "libx264" in command and command[-1] == "a-shorts.mp4"
    with_audio = clipfx.shorts_command("ffmpeg", Path("a.mp4"), Path("b.mp4"), mode=mode)
    assert "0:a?" in with_audio and "aac" in with_audio


def test_shorts_and_watermark_validation(tmp_path):
    with pytest.raises(ClipFxError, match="쇼츠 형태"):
        clipfx.shorts_command("ffmpeg", Path("a"), Path("b"), mode="square")
    with pytest.raises(ClipFxError, match="가로 위치"):
        clipfx.shorts_command("ffmpeg", Path("a"), Path("b"), focus=2)
    with pytest.raises(ClipFxError, match="그림 없음"):
        Watermark(tmp_path / "없음.png").check()
    for kwargs, message in (({"position": "middle"}, "위치"), ({"size": 0.9}, "크기"), ({"opacity": 0}, "투명도")):
        with pytest.raises(ClipFxError, match=message):
            Watermark(mark(tmp_path), **kwargs).check()
    graph = clipfx.shorts_command("ffmpeg", Path("a"), Path("b"), watermark=Watermark(mark(tmp_path), "bottom", 0.3))[8]
    assert "overlay=(main_w-overlay_w)/2:main_h-overlay_h-32" in graph


def test_output_path_never_overwrites(tmp_path):
    source = tmp_path / "클립.mp4"
    assert clipfx.output_path(source, "-shorts", ".mp4") == tmp_path / "클립-shorts.mp4"
    (tmp_path / "클립-shorts.mp4").write_bytes(b"x")
    (tmp_path / "클립-shorts-2.mp4").write_bytes(b"x")
    assert clipfx.output_path(source, "-shorts", ".mp4") == tmp_path / "클립-shorts-3.mp4"
    assert clipfx.output_path(source, "", ".gif", tmp_path / "out") == tmp_path / "out" / "클립.gif"


def test_missing_source_and_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(clipfx, "find_ffmpeg", lambda: "ffmpeg")
    with pytest.raises(ClipFxError, match="영상 파일 없음"):
        clipfx.make_gif(tmp_path / "없음.mp4")
    monkeypatch.undo()
    monkeypatch.setattr("debutkit.tools.ffmpeg_path", lambda: None)
    monkeypatch.setattr(clipfx.shutil, "which", lambda name: None)
    with pytest.raises(ClipFxError, match="ffmpeg 없음"):
        clipfx.find_ffmpeg()


def test_post_processor_reports_each_result(tmp_path):
    notes, calls = [], []

    def gif(clip, **options):
        calls.append(("gif", clip.name, options))
        return clip.with_suffix(".gif")

    def shorts(clip, **options):
        raise ClipFxError("ffmpeg 오류: 디스크 가득 참")

    post = clipfx.PostProcessor(True, True, notes.append, make={"gif": gif, "shorts": shorts})
    try:
        made = post.process(tmp_path / "a.mp4")
    finally:
        post.stop()
    assert made == [tmp_path / "a.gif"] and calls == [("gif", "a.mp4", {"duration": 6.0})]
    assert notes == ["움짤 저장: a.gif", "세로 쇼츠 만들기 실패(a.mp4): ffmpeg 오류: 디스크 가득 참"]


def test_autoclipper_hands_saved_clip_to_post(monkeypatch):
    pytest.importorskip("stream2clip.live")
    from debutkit.clip import AutoClipper
    from debutkit.overlay.server import Hub

    hub, received = Hub(), []

    class Saved:
        clip = "C:/clips/a.mp4"
        note = ""

    class Trigger:
        reasons = ["!clip"]
        score = 1.0

    clipper = AutoClipper(hub, lambda trigger: Saved(), post=received.append)
    clipper._on_trigger(Trigger())
    assert received == [Path("C:/clips/a.mp4")] and "클립 저장: a.mp4" in hub.history[-1].text


ffmpeg = None
try:
    ffmpeg = clipfx.find_ffmpeg()
except ClipFxError:
    pass


@pytest.mark.skipif(ffmpeg is None, reason="ffmpeg 없음")
def test_real_ffmpeg_gif_webp_and_shorts(tmp_path, capsys):
    from debutkit.cli import main

    source = tmp_path / "clip.mp4"
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24:duration=3",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(source)],
                   check=True, timeout=120)
    assert clipfx.probe(source).audio
    assert main(["clip", "gif", str(source), "--duration", "1", "--width", "320", "--fps", "10"]) == 0
    assert main(["clip", "shorts", str(source), "--mode", "crop", "--focus", "0.2", "--duration", "1"]) == 0
    out = capsys.readouterr().out
    assert "clip.gif" in out and "clip-shorts.mp4" in out
    shorts = clipfx.probe(tmp_path / "clip-shorts.mp4")
    assert (shorts.width, shorts.height, shorts.audio) == (1080, 1920, True)
    pytest.importorskip("PIL")
    from PIL import Image

    webp = clipfx.make_webp(source, duration=1, width=320, fps=10)
    with Image.open(webp) as image:
        assert image.size == (320, 180) and getattr(image, "n_frames", 1) == 10
    assert main(["clip", "gif", str(tmp_path / "없음.mp4")]) == 1
