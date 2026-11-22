import pytest

from debutkit.cli import build_parser, main


def test_scenes_dry_run_needs_no_obs(capsys):
    assert main(["scenes", "--dry-run", "--avatar", "vseeface", "--overlay-port", "9000"]) == 0
    out = capsys.readouterr().out
    assert "본방송" in out and "아바타 (VSeeFace)" in out and "--dry-run" in out


def test_doctor_json(capsys, monkeypatch):
    from debutkit import doctor

    monkeypatch.setattr(doctor, "run_checks", lambda **kw: [doctor.Check("obs", "OBS Studio", doctor.OK, "found")])
    assert main(["doctor", "--json"]) == 0
    assert '"status": "ok"' in capsys.readouterr().out


def test_doctor_exit_code_on_required(capsys, monkeypatch):
    from debutkit import doctor

    monkeypatch.setattr(doctor, "run_checks", lambda **kw: [doctor.Check("obs", "OBS Studio", doctor.FAIL, "찾지 못함", "설치")])
    assert main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "[필요]" in out and "소속 버튜버 프로그램" in out and "무관" in out
    assert "budongjw.github.io/debutkit/join.html" in out


def test_parser_requires_a_command():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_setup_reports_ffmpeg(capsys, monkeypatch):
    from debutkit import tools

    monkeypatch.setattr(tools, "ffmpeg_path", lambda: r"C:\tools\ffmpeg.exe")
    assert main(["setup"]) == 0
    assert r"ffmpeg: C:\tools\ffmpeg.exe" in capsys.readouterr().out


def test_setup_downloads_when_missing(capsys, monkeypatch):
    from debutkit import tools

    state = {"have": None, "calls": 0}

    def download(**kw):
        state["calls"] += 1
        kw["on_progress"](50, 100)
        kw["on_progress"](100, 100)
        state["have"] = r"C:\tools\ffmpeg.exe"
        return [r"C:\tools\ffmpeg.exe", r"C:\tools\ffprobe.exe"]

    monkeypatch.setattr(tools, "ffmpeg_path", lambda: state["have"])
    monkeypatch.setattr(tools, "ffmpeg_megabytes", lambda: 115)
    monkeypatch.setattr(tools, "download_ffmpeg", download)
    assert main(["setup", "--ffmpeg"]) == 0
    out = capsys.readouterr().out
    assert state["calls"] == 1 and "100%" in out and "저장:" in out


def test_setup_without_ffmpeg_fails(capsys, monkeypatch):
    from debutkit import tools

    monkeypatch.setattr(tools, "ffmpeg_path", lambda: None)
    assert main(["setup"]) == 1
    assert "ffmpeg: 없음" in capsys.readouterr().out


def test_chzzk_logout_without_token(capsys, monkeypatch, tmp_path):
    pytest.importorskip("stream2clip.chzzk_api")
    monkeypatch.setenv("STREAM2CLIP_CHZZK_TOKEN", str(tmp_path / "token.json"))
    assert main(["chzzk", "logout"]) == 0
    assert "로그인 상태 아님" in capsys.readouterr().out


def test_overlay_clip_failure_exits_instead_of_hanging(capsys, monkeypatch):
    from debutkit import clip

    monkeypatch.setattr(clip, "preflight", lambda: "자동 클립에는 ffmpeg 필요")
    assert main(["overlay", "--port", "0", "--clip"]) == 1  # 시작 전 서버를 멈춰도 멈추지 않고 끝난다
    assert "ffmpeg 필요" in capsys.readouterr().err


def test_setup_check_update_only_when_asked(capsys, monkeypatch):
    from debutkit import tools

    calls = []
    monkeypatch.setattr(tools, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(tools, "update_message", lambda current: calls.append(current) or "최신 버전 사용 중")
    main(["setup"])
    assert calls == []  # 지정하지 않으면 연결하지 않는다
    main(["setup", "--check-update"])
    assert len(calls) == 1 and "최신 버전 사용 중" in capsys.readouterr().out
